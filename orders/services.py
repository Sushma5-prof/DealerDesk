"""
Service layer for Orders (§7.1–§7.5).
Pure functions for GST math + transactional services with row-level locking
for concurrency-safe order numbering, stock deduction, and idempotency.
"""
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import struct

from django.db import connection, transaction
from django.db.models import QuerySet
from django.utils import timezone

from catalogue.models import Product
from core.exceptions import (
    IdempotencyConflictError,
    InsufficientStockError,
    InvalidTransitionError,
    NotFoundError,
    OrderLockedError,
    ValidationError,
)
from dealers.models import Dealer
from .models import Order, OrderItem

GST_RATE = Decimal("0.18")
TWO_PLACES = Decimal("0.01")


def compute_line_amounts(
    unit_price: Decimal, quantity: int
) -> tuple[Decimal, Decimal, Decimal]:
    """
    Contract §7.4 pure function:
    - line_subtotal = unit_price * quantity
    - line_tax = line_subtotal * 0.18, rounded to 2 decimals using ROUND_HALF_UP
    - line_total = line_subtotal + line_tax
    """
    line_subtotal = (unit_price * Decimal(quantity)).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    line_tax = (line_subtotal * GST_RATE).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    line_total = line_subtotal + line_tax
    return line_subtotal, line_tax, line_total


def _next_order_number() -> str:
    """
    Contract §7.5: ORD-YYYYMMDD-NNNN in Asia/Kolkata.
    Uses atomic PostgreSQL upsert on orders_dailysequence so concurrent
    creations never collide or deadlock.
    """
    today = timezone.localdate()
    with connection.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO orders_dailysequence (date, last_seq)
            VALUES (%s, 1)
            ON CONFLICT (date)
            DO UPDATE SET last_seq = orders_dailysequence.last_seq + 1
            RETURNING last_seq
            """,
            [today],
        )
        seq = cursor.fetchone()[0]
    return f"ORD-{today.strftime('%Y%m%d')}-{seq:04d}"


def _canonical_body_hash(dealer_id, items) -> str:
    payload = json.dumps(
        {"dealer_id": dealer_id, "items": items},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _advisory_lock_id(key: str) -> int:
    digest = hashlib.sha256(key.encode("utf-8")).digest()[:8]
    return struct.unpack("<q", digest)[0]


def _validate_items_payload(raw_items) -> list[tuple[Product, int]]:
    if not isinstance(raw_items, list) or len(raw_items) == 0:
        raise ValidationError("Order must contain at least one item.")

    seen_skus: set[str] = set()
    parsed: list[tuple[str, int]] = []

    for entry in raw_items:
        if not isinstance(entry, dict):
            raise ValidationError("Each item must be an object with 'sku' and 'quantity'.")
        sku = str(entry.get("sku") or "").strip()
        qty = entry.get("quantity")
        if not sku:
            raise ValidationError("Item 'sku' is required.")
        if sku in seen_skus:
            raise ValidationError(f"Duplicate SKU '{sku}' in order items.")
        seen_skus.add(sku)

        if qty is None or isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise ValidationError(f"Quantity for SKU '{sku}' must be an integer >= 1.")
        parsed.append((sku, qty))

    products_by_sku = {
        p.sku: p for p in Product.objects.filter(sku__in=seen_skus)
    }
    if len(products_by_sku) != len(seen_skus):
        missing = sorted(seen_skus - set(products_by_sku.keys()))
        raise ValidationError(f"Unknown SKU(s): {', '.join(missing)}")

    return [(products_by_sku[sku], qty) for sku, qty in parsed]


def sync_draft_prices(order: Order) -> Order:
    """
    Contract §7.4: While an order is DRAFT, unit_price is the product's current price.
    Updates OrderItem and Order totals if any product price changed while in DRAFT.
    """
    if order.status != Order.STATUS_DRAFT:
        return order

    items = list(order.items.select_related("product").all())
    if not items:
        return order

    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    changed = False

    for item in items:
        current_price = item.product.price
        current_name = item.product.name
        line_sub, line_tax, line_tot = compute_line_amounts(current_price, item.quantity)
        if (
            item.unit_price != current_price
            or item.name != current_name
            or item.line_subtotal != line_sub
            or item.line_tax != line_tax
            or item.line_total != line_tot
        ):
            item.unit_price = current_price
            item.name = current_name
            item.line_subtotal = line_sub
            item.line_tax = line_tax
            item.line_total = line_tot
            item.save(
                update_fields=[
                    "unit_price",
                    "name",
                    "line_subtotal",
                    "line_tax",
                    "line_total",
                ]
            )
            changed = True
        subtotal += line_sub
        tax_total += line_tax

    grand_total = subtotal + tax_total
    if (
        changed
        or order.subtotal != subtotal
        or order.tax_total != tax_total
        or order.grand_total != grand_total
    ):
        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = grand_total
        order.save(update_fields=["subtotal", "tax_total", "grand_total"])

    return order


def create_order(
    dealer_id,
    items,
    idempotency_key: str | None = None,
) -> tuple[Order, bool]:
    """
    Create a DRAFT order.
    Returns (order, created_bool).
    """
    clean_key = (idempotency_key or "").strip() or None
    body_hash = _canonical_body_hash(dealer_id, items) if clean_key else None

    with transaction.atomic():
        if clean_key:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s)",
                    [_advisory_lock_id(clean_key)],
                )
            existing = (
                Order.objects.filter(idempotency_key=clean_key)
                .prefetch_related("items__product")
                .first()
            )
            if existing is not None:
                if existing.idempotency_body_hash != body_hash:
                    raise IdempotencyConflictError(
                        "Idempotency-Key reused with a different request body."
                    )
                return sync_draft_prices(existing), False

        if dealer_id is None or isinstance(dealer_id, bool) or not isinstance(dealer_id, int):
            raise ValidationError("Valid 'dealer_id' is required.")
        try:
            dealer = Dealer.objects.get(pk=dealer_id)
        except Dealer.DoesNotExist:
            raise ValidationError(f"Dealer with id '{dealer_id}' does not exist.")

        validated_items = _validate_items_payload(items)
        order_number = _next_order_number()

        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        order_items: list[OrderItem] = []

        order = Order.objects.create(
            order_number=order_number,
            dealer=dealer,
            status=Order.STATUS_DRAFT,
            idempotency_key=clean_key,
            idempotency_body_hash=body_hash,
        )

        for product, qty in validated_items:
            line_sub, line_tax, line_tot = compute_line_amounts(product.price, qty)
            subtotal += line_sub
            tax_total += line_tax
            order_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    sku=product.sku,
                    name=product.name,
                    quantity=qty,
                    unit_price=product.price,
                    line_subtotal=line_sub,
                    line_tax=line_tax,
                    line_total=line_tot,
                )
            )

        OrderItem.objects.bulk_create(order_items)
        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = subtotal + tax_total
        order.save(update_fields=["subtotal", "tax_total", "grand_total"])
        return order, True


def list_orders(
    dealer_id: str | None = None,
    status_filter: str | None = None,
) -> QuerySet[Order]:
    qs = Order.objects.prefetch_related("items__product").all()
    if dealer_id is not None and dealer_id != "":
        try:
            qs = qs.filter(dealer_id=int(dealer_id))
        except ValueError:
            qs = qs.none()
    if status_filter is not None and status_filter != "":
        qs = qs.filter(status=status_filter)
    return qs


def get_order(order_number: str) -> Order:
    try:
        order = Order.objects.prefetch_related("items__product").get(
            order_number=order_number
        )
    except Order.DoesNotExist:
        raise NotFoundError(f"Order '{order_number}' not found.")
    return sync_draft_prices(order)


def update_order_items(order_number: str, raw_items) -> Order:
    """
    PUT /api/orders/{order_number}/
    Replaces all items. Only allowed while DRAFT, else 409 ORDER_LOCKED.
    """
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order '{order_number}' not found.")

        if order.status != Order.STATUS_DRAFT:
            raise OrderLockedError("Only DRAFT orders can be edited.")

        validated_items = _validate_items_payload(raw_items)
        order.items.all().delete()

        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")
        new_items: list[OrderItem] = []

        for product, qty in validated_items:
            line_sub, line_tax, line_tot = compute_line_amounts(product.price, qty)
            subtotal += line_sub
            tax_total += line_tax
            new_items.append(
                OrderItem(
                    order=order,
                    product=product,
                    sku=product.sku,
                    name=product.name,
                    quantity=qty,
                    unit_price=product.price,
                    line_subtotal=line_sub,
                    line_tax=line_tax,
                    line_total=line_tot,
                )
            )

        OrderItem.objects.bulk_create(new_items)
        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = subtotal + tax_total
        order.save(update_fields=["subtotal", "tax_total", "grand_total", "updated_at"])
        return order


def confirm_order(order_number: str) -> Order:
    """
    POST /api/orders/{order_number}/confirm/
    DRAFT -> CONFIRMED. Locks unit_price and deducts stock all-or-nothing.
    """
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order '{order_number}' not found.")

        if order.status != Order.STATUS_DRAFT:
            raise InvalidTransitionError(
                f"Cannot confirm order in status '{order.status}'."
            )

        items = list(order.items.all())
        skus = sorted({item.sku for item in items})
        locked_products = {
            p.sku: p
            for p in Product.objects.select_for_update()
            .filter(sku__in=skus)
            .order_by("sku")
        }

        short_details = []
        short_messages = []
        for item in items:
            prod = locked_products[item.sku]
            if item.quantity > prod.stock:
                short_details.append(
                    {
                        "sku": item.sku,
                        "requested": item.quantity,
                        "available": prod.stock,
                    }
                )
                short_messages.append(
                    f"Insufficient stock for {prod.name}. Available: {prod.stock}, Requested: {item.quantity}"
                )

        if short_details:
            raise InsufficientStockError(
                message=". ".join(short_messages),
                details=short_details,
            )

        subtotal = Decimal("0.00")
        tax_total = Decimal("0.00")

        for item in items:
            prod = locked_products[item.sku]
            prod.stock -= item.quantity
            prod.save(update_fields=["stock"])

            # Lock current product price and name upon confirmation
            line_sub, line_tax, line_tot = compute_line_amounts(
                prod.price, item.quantity
            )
            item.unit_price = prod.price
            item.name = prod.name
            item.line_subtotal = line_sub
            item.line_tax = line_tax
            item.line_total = line_tot
            item.save(
                update_fields=[
                    "unit_price",
                    "name",
                    "line_subtotal",
                    "line_tax",
                    "line_total",
                ]
            )
            subtotal += line_sub
            tax_total += line_tax

        order.subtotal = subtotal
        order.tax_total = tax_total
        order.grand_total = subtotal + tax_total
        order.status = Order.STATUS_CONFIRMED
        order.save(
            update_fields=[
                "subtotal",
                "tax_total",
                "grand_total",
                "status",
                "updated_at",
            ]
        )
        return order


def dispatch_order(order_number: str) -> Order:
    """CONFIRMED -> DISPATCHED."""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order '{order_number}' not found.")

        if order.status != Order.STATUS_CONFIRMED:
            raise InvalidTransitionError(
                f"Cannot dispatch order in status '{order.status}'."
            )

        order.status = Order.STATUS_DISPATCHED
        order.save(update_fields=["status", "updated_at"])
        return order


def deliver_order(order_number: str) -> Order:
    """DISPATCHED -> DELIVERED."""
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order '{order_number}' not found.")

        if order.status != Order.STATUS_DISPATCHED:
            raise InvalidTransitionError(
                f"Cannot deliver order in status '{order.status}'."
            )

        order.status = Order.STATUS_DELIVERED
        order.save(update_fields=["status", "updated_at"])
        return order


def cancel_order(order_number: str) -> Order:
    """
    DRAFT -> CANCELLED (no stock change)
    CONFIRMED -> CANCELLED (restores stock once)
    """
    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(order_number=order_number)
        except Order.DoesNotExist:
            raise NotFoundError(f"Order '{order_number}' not found.")

        if order.status == Order.STATUS_DRAFT:
            order.status = Order.STATUS_CANCELLED
            order.save(update_fields=["status", "updated_at"])
            return order

        if order.status == Order.STATUS_CONFIRMED:
            items = list(order.items.all())
            skus = sorted({item.sku for item in items})
            locked_products = {
                p.sku: p
                for p in Product.objects.select_for_update()
                .filter(sku__in=skus)
                .order_by("sku")
            }
            for item in items:
                prod = locked_products[item.sku]
                prod.stock += item.quantity
                prod.save(update_fields=["stock"])

            order.status = Order.STATUS_CANCELLED
            order.save(update_fields=["status", "updated_at"])
            return order

        raise InvalidTransitionError(
            f"Cannot cancel order in status '{order.status}'."
        )
