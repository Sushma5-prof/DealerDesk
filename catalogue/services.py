"""
Service layer for Catalogue (Products & Inventory).
All business logic lives here so both REST views and Assistant tools reuse it.
"""
from decimal import Decimal, InvalidOperation
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet

from core.exceptions import DuplicateError, NotFoundError, ValidationError
from .models import Inventory, Product


MAX_PRICE = Decimal("9999999999.99")
MAX_INT32 = 2_147_483_647


def parse_positive_price(raw_price) -> Decimal:
    """Validate that price is > 0, fits Decimal(12, 2), and has at most 2 decimal places."""
    if raw_price is None or isinstance(raw_price, bool):
        raise ValidationError("Price is required and must be a valid number.")
    try:
        raw_str = str(raw_price).strip()
        dec = Decimal(raw_str)
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Invalid price format.")

    if not dec.is_finite() or dec <= Decimal("0"):
        raise ValidationError("Price must be greater than 0.")
    if dec > MAX_PRICE:
        raise ValidationError("Price exceeds maximum allowed value.")

    # Check at most 2 decimal places
    exponent = dec.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationError("Price must have at most 2 decimal places.")

    return dec.quantize(Decimal("0.01"))


def _validate_field_lengths(
    sku: str | None = None,
    name: str | None = None,
    category: str | None = None,
    brand: str | None = None,
    vehicle_fitment: str | None = None,
    description: str | None = None,
) -> None:
    if sku is not None and len(sku) > 64:
        raise ValidationError("Field 'sku' must be at most 64 characters.")
    if name is not None and len(name) > 255:
        raise ValidationError("Field 'name' must be at most 255 characters.")
    if category is not None and len(category) > 128:
        raise ValidationError("Field 'category' must be at most 128 characters.")
    if brand is not None and len(brand) > 128:
        raise ValidationError("Field 'brand' must be at most 128 characters.")
    if vehicle_fitment is not None and len(vehicle_fitment) > 255:
        raise ValidationError("Field 'vehicle_fitment' must be at most 255 characters.")
    if description is not None and len(description) > 10000:
        raise ValidationError("Field 'description' must be at most 10000 characters.")


def list_products(
    search: str | None = None,
    category: str | None = None,
    vehicle: str | None = None,
) -> QuerySet[Product]:
    """
    Filter products according to Contract §4:
    - search: case-insensitive substring on sku, name, or brand
    - category: exact match
    - vehicle: case-insensitive substring on vehicle_fitment
    """
    qs = Product.objects.all()
    if search:
        s = search.strip()[:255]
        if s:
            qs = qs.filter(
                Q(sku__icontains=s) | Q(name__icontains=s) | Q(brand__icontains=s)
            )
    if category is not None and category != "":
        qs = qs.filter(category=category[:128])
    if vehicle:
        v = vehicle.strip()[:255]
        if v:
            qs = qs.filter(vehicle_fitment__icontains=v)
    return qs


def search_parts(
    query: str | None = None,
    vehicle: str | None = None,
    category: str | None = None,
    limit: int = 10,
) -> list[Product]:
    """
    Search parts for the Dealer Assistant tool `search_parts`.
    First delegates to `list_products`; if a plural or multi-word query (e.g. 'brake pads')
    returns no exact substring match, falls back to token-level stem matching.
    """
    safe_query = (query or "").strip()[:255]
    safe_vehicle = (vehicle or "").strip()[:255]
    safe_category = (category or "").strip()[:128]

    qs = list_products(
        search=safe_query or None,
        category=safe_category or None,
        vehicle=safe_vehicle or None,
    )
    results = list(qs[:limit])
    if results or not safe_query:
        return results

    qs_fallback = Product.objects.all()
    if safe_category:
        qs_fallback = qs_fallback.filter(category__iexact=safe_category)
    if safe_vehicle:
        for v_tok in safe_vehicle.split()[:6]:
            if len(v_tok) >= 2:
                qs_fallback = qs_fallback.filter(vehicle_fitment__icontains=v_tok)

    tokens = [
        t.lower().rstrip("s") if len(t) > 3 and t.lower().endswith("s") else t.lower()
        for t in safe_query.split()[:8]
        if len(t) >= 2
    ]
    for tok in tokens:
        qs_fallback = qs_fallback.filter(
            Q(sku__icontains=tok)
            | Q(name__icontains=tok)
            | Q(brand__icontains=tok)
            | Q(category__icontains=tok)
            | Q(vehicle_fitment__icontains=tok)
        )
    return list(qs_fallback[:limit])


def get_product(sku: str) -> Product:
    """Fetch a single product by SKU or raise 404 NOT_FOUND."""
    try:
        return Product.objects.get(sku=sku)
    except Product.DoesNotExist:
        raise NotFoundError(f"Product with SKU '{sku}' not found.")


def create_product(data: dict) -> Product:
    """
    Create a new Product with stock=0.
    Duplicate SKU raises 409 DUPLICATE.
    Invalid fields or price <= 0 raises 400 VALIDATION_ERROR.
    """
    sku = str(data.get("sku") or "").strip()
    if not sku:
        raise ValidationError("Field 'sku' is required.")

    name = str(data.get("name") or "").strip()
    category = str(data.get("category") or "").strip()
    brand = str(data.get("brand") or "").strip()
    vehicle_fitment = str(data.get("vehicle_fitment") or "").strip()
    description = str(data.get("description") or "")

    if not name or not category or not brand or not vehicle_fitment:
        raise ValidationError(
            "Fields 'name', 'category', 'brand', and 'vehicle_fitment' are required."
        )

    _validate_field_lengths(
        sku=sku,
        name=name,
        category=category,
        brand=brand,
        vehicle_fitment=vehicle_fitment,
        description=description,
    )

    if Product.objects.filter(sku=sku).exists():
        raise DuplicateError(f"Product with SKU '{sku}' already exists.")

    price = parse_positive_price(data.get("price"))

    try:
        with transaction.atomic():
            return Product.objects.create(
                sku=sku,
                name=name,
                category=category,
                brand=brand,
                vehicle_fitment=vehicle_fitment,
                price=price,
                stock=0,
                description=description,
            )
    except IntegrityError:
        raise DuplicateError(f"Product with SKU '{sku}' already exists.")


def update_product(sku: str, data: dict) -> Product:
    """
    Partial update (PATCH) of a product. SKU cannot change.
    """
    product = get_product(sku)

    if "sku" in data and data["sku"] != sku:
        raise ValidationError("SKU cannot be changed.")

    if "price" in data:
        product.price = parse_positive_price(data["price"])

    for field in ("name", "category", "brand", "vehicle_fitment"):
        if field in data:
            val = str(data[field] or "").strip()
            if not val:
                raise ValidationError(f"Field '{field}' cannot be empty.")
            _validate_field_lengths(**{field: val})
            setattr(product, field, val)

    if "description" in data:
        if data["description"] is None:
            raise ValidationError("Field 'description' cannot be null.")
        desc = str(data["description"])
        _validate_field_lengths(description=desc)
        product.description = desc

    product.save()
    return product


def set_inventory(sku: str, quantity, reason: str = "") -> Product:
    """
    Contract §5: Set available stock to exact integer >= 0.
    """
    if quantity is None or isinstance(quantity, bool) or not isinstance(quantity, int):
        raise ValidationError("Quantity must be an integer >= 0.")
    if quantity < 0 or quantity > MAX_INT32:
        raise ValidationError(f"Quantity must be between 0 and {MAX_INT32}.")
    clean_reason = str(reason or "")[:255]

    with transaction.atomic():
        try:
            product = Product.objects.select_for_update().get(sku=sku)
        except Product.DoesNotExist:
            raise NotFoundError(f"Product with SKU '{sku}' not found.")

        product.stock = quantity
        product.save(update_fields=["stock"])
        Inventory.objects.create(product=product, quantity=quantity, reason=clean_reason)
        return product
