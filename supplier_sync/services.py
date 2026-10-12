"""
Service layer for Supplier Sync (§8).
Fetches all paginated pages with retry/backoff, validates items, deduplicates by
latest updated_at, and applies all catalogue updates atomically without touching stock.
"""
from datetime import datetime
from decimal import Decimal, InvalidOperation
import time
import requests

from django.conf import settings
from django.db import transaction

from catalogue.models import Product
from core.exceptions import SupplierUnavailableError

MAX_ATTEMPTS_PER_PAGE = 5
PAGE_LIMIT = 20
MAX_PAGES = 500
MAX_SYNC_DURATION_SECONDS = 110.0
MAX_RETRY_WAIT_SECONDS = 15.0
MAX_PRICE = Decimal("9999999999.99")


def _validate_supplier_item(item: dict) -> tuple[bool, Decimal | None, str]:
    """
    Contract §8.3 rule 4:
    Invalid if missing/empty sku, or price is not a positive amount with at most 2 decimals.
    Returns (is_valid, parsed_price, reason).
    """
    if not isinstance(item, dict):
        return False, None, "malformed item object"

    sku = str(item.get("sku") or "").strip()
    if not sku or len(sku) > 64:
        return False, None, "missing or invalid sku"

    raw_price = item.get("price")
    if raw_price is None or isinstance(raw_price, bool):
        return False, None, "invalid price"

    try:
        dec = Decimal(str(raw_price).strip())
    except (InvalidOperation, ValueError, TypeError):
        return False, None, "invalid price"

    if not dec.is_finite() or dec <= Decimal("0") or dec > MAX_PRICE:
        return False, None, "invalid price"

    exp = dec.as_tuple().exponent
    if isinstance(exp, int) and exp < -2:
        return False, None, "invalid price"

    return True, dec.quantize(Decimal("0.01")), ""


def _parse_updated_at(ts_str: str) -> datetime:
    try:
        return datetime.fromisoformat(str(ts_str).replace("Z", "+00:00"))
    except Exception:
        return datetime.min


def run_supplier_sync(
    session: requests.Session | None = None,
    sleep_fn=time.sleep,
    max_pages: int = MAX_PAGES,
    max_duration_seconds: float = MAX_SYNC_DURATION_SECONDS,
) -> dict:
    """
    Execute one full supplier sync according to Contract §8.1–§8.3.
    Guards against cursor loops, page floods, and deadline overruns (< 120s).
    """
    base_url = (getattr(settings, "SUPPLIER_API_URL", "") or "").rstrip("/")
    api_key = getattr(settings, "SUPPLIER_API_KEY", "") or ""
    if not base_url or not api_key:
        raise SupplierUnavailableError("Supplier API URL or key is not configured.")

    http = session or requests.Session()
    url = f"{base_url}/v1/products"
    headers = {"X-Api-Key": api_key}

    cursor: str | None = None
    seen_cursors: set[str] = set()
    pages_fetched = 0
    requests_made = 0
    all_raw_items: list[dict] = []
    started_at = time.monotonic()

    while True:
        if time.monotonic() - started_at > max_duration_seconds:
            raise SupplierUnavailableError(
                "Supplier sync exceeded the maximum allowed duration."
            )
        if pages_fetched >= max_pages:
            raise SupplierUnavailableError(
                f"Supplier feed exceeded maximum page limit ({max_pages})."
            )

        params: dict[str, str | int] = {"limit": PAGE_LIMIT}
        if cursor is not None:
            params["cursor"] = cursor

        page_data = None
        for attempt in range(1, MAX_ATTEMPTS_PER_PAGE + 1):
            remaining = max_duration_seconds - (time.monotonic() - started_at)
            if remaining <= 0:
                raise SupplierUnavailableError(
                    "Supplier sync timed out before completing all pages."
                )

            requests_made += 1
            try:
                resp = http.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=min(15.0, max(1.0, remaining)),
                )
            except requests.RequestException:
                if attempt == MAX_ATTEMPTS_PER_PAGE:
                    raise SupplierUnavailableError(
                        "Supplier API connection failed after 5 attempts."
                    )
                sleep_fn(0.2 * (2 ** (attempt - 1)))
                continue

            if resp.status_code == 200:
                try:
                    page_data = resp.json()
                except Exception:
                    raise SupplierUnavailableError("Invalid JSON from supplier API.")
                if not isinstance(page_data, dict):
                    raise SupplierUnavailableError("Malformed JSON object from supplier API.")
                pages_fetched += 1
                break

            if resp.status_code == 429:
                if attempt == MAX_ATTEMPTS_PER_PAGE:
                    raise SupplierUnavailableError(
                        "Rate limited by supplier API after 5 attempts."
                    )
                retry_header = resp.headers.get("Retry-After", "1")
                try:
                    wait_seconds = max(0.0, float(retry_header))
                except ValueError:
                    wait_seconds = 1.0
                if wait_seconds > MAX_RETRY_WAIT_SECONDS:
                    raise SupplierUnavailableError(
                        f"Supplier Retry-After ({wait_seconds}s) exceeds safe threshold."
                    )
                sleep_fn(wait_seconds)
                continue

            if resp.status_code >= 500:
                if attempt == MAX_ATTEMPTS_PER_PAGE:
                    raise SupplierUnavailableError(
                        f"Supplier API returned {resp.status_code} after 5 attempts."
                    )
                sleep_fn(0.2 * (2 ** (attempt - 1)))
                continue

            # 401, 403, 400, 404 -> non-retryable failure
            raise SupplierUnavailableError(
                f"Supplier API rejected request with HTTP {resp.status_code}."
            )

        items = page_data.get("items")
        if not isinstance(items, list):
            raise SupplierUnavailableError("Malformed items list in supplier feed.")
        all_raw_items.extend(items)

        next_cursor = page_data.get("next_cursor")
        if not next_cursor:
            break
        next_cursor_str = str(next_cursor).strip()
        if not next_cursor_str:
            break
        if next_cursor_str == cursor or next_cursor_str in seen_cursors:
            raise SupplierUnavailableError(
                f"Supplier API returned a repeated pagination cursor '{next_cursor_str}'."
            )
        seen_cursors.add(next_cursor_str)
        cursor = next_cursor_str

    # Step 4: Validate items and record rejected ones
    rejected: list[dict] = []
    valid_items: list[tuple[dict, Decimal]] = []
    for raw in all_raw_items:
        ok, price_dec, reason = _validate_supplier_item(raw)
        if not ok or price_dec is None:
            supplier_sku = (
                str(raw.get("supplier_sku") or "")[:64]
                if isinstance(raw, dict)
                else ""
            )
            rejected.append(
                {
                    "supplier_sku": supplier_sku,
                    "reason": reason,
                }
            )
        else:
            valid_items.append((raw, price_dec))

    # Step 5: Deduplicate by SKU keeping the version with the latest updated_at
    deduped: dict[str, tuple[dict, Decimal, datetime]] = {}
    for raw, price_dec in valid_items:
        sku = str(raw["sku"]).strip()
        ts = _parse_updated_at(raw.get("updated_at", ""))
        if sku not in deduped or ts > deduped[sku][2]:
            deduped[sku] = (raw, price_dec, ts)

    # Step 6 & 7: Apply atomically without changing stock
    created_count = 0
    updated_count = 0
    unchanged_count = 0

    with transaction.atomic():
        existing_map = {
            p.sku: p
            for p in Product.objects.select_for_update().filter(
                sku__in=deduped.keys()
            )
        }

        to_create: list[Product] = []
        to_update: list[Product] = []

        for sku, (raw, price_dec, _) in deduped.items():
            name = str(raw.get("name") or "").strip()[:255]
            category = str(raw.get("category") or "").strip()[:128]
            brand = str(raw.get("brand") or "").strip()[:128]
            vehicle_fitment = str(raw.get("vehicle_fitment") or "").strip()[:255]
            description = str(raw.get("description") or "")[:10000]

            if sku not in existing_map:
                to_create.append(
                    Product(
                        sku=sku,
                        name=name,
                        category=category,
                        brand=brand,
                        vehicle_fitment=vehicle_fitment,
                        description=description,
                        price=price_dec,
                        stock=0,
                    )
                )
                created_count += 1
            else:
                prod = existing_map[sku]
                if (
                    prod.name != name
                    or prod.category != category
                    or prod.brand != brand
                    or prod.vehicle_fitment != vehicle_fitment
                    or prod.description != description
                    or prod.price != price_dec
                ):
                    prod.name = name
                    prod.category = category
                    prod.brand = brand
                    prod.vehicle_fitment = vehicle_fitment
                    prod.description = description
                    prod.price = price_dec
                    to_update.append(prod)
                    updated_count += 1
                else:
                    unchanged_count += 1

        if to_create:
            Product.objects.bulk_create(to_create)
        if to_update:
            Product.objects.bulk_update(
                to_update,
                [
                    "name",
                    "category",
                    "brand",
                    "vehicle_fitment",
                    "description",
                    "price",
                ],
            )

    return {
        "created": created_count,
        "updated": updated_count,
        "unchanged": unchanged_count,
        "rejected": rejected,
        "pages_fetched": pages_fetched,
        "requests_made": requests_made,
    }
