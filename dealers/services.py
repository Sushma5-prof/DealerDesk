"""Service layer for Dealers (§6)."""
from decimal import Decimal, InvalidOperation
from django.db import IntegrityError, transaction
from django.db.models import QuerySet

from core.exceptions import DuplicateError, NotFoundError, ValidationError
from .models import Dealer


MAX_CREDIT_LIMIT = Decimal("9999999999.99")
MAX_INT32 = 2_147_483_647


def list_dealers() -> QuerySet[Dealer]:
    return Dealer.objects.all()


def get_dealer(dealer_id: int) -> Dealer:
    if isinstance(dealer_id, bool) or not isinstance(dealer_id, int):
        raise NotFoundError(f"Dealer with id '{dealer_id}' not found.")
    if dealer_id < 1 or dealer_id > MAX_INT32:
        raise NotFoundError(f"Dealer with id '{dealer_id}' not found.")
    try:
        return Dealer.objects.get(pk=dealer_id)
    except (Dealer.DoesNotExist, ValueError, TypeError, OverflowError):
        raise NotFoundError(f"Dealer with id '{dealer_id}' not found.")


def create_dealer(data: dict) -> Dealer:
    dealer_code = str(data.get("dealer_code") or "").strip()
    name = str(data.get("name") or "").strip()
    if not dealer_code or not name:
        raise ValidationError("Fields 'dealer_code' and 'name' are required.")

    city = str(data.get("city") or "").strip()
    phone = str(data.get("phone") or "").strip()
    email = str(data.get("email") or "").strip()
    gstin = str(data.get("gstin") or "").strip()

    if len(dealer_code) > 64:
        raise ValidationError("Field 'dealer_code' must be at most 64 characters.")
    if len(name) > 255:
        raise ValidationError("Field 'name' must be at most 255 characters.")
    if len(city) > 128:
        raise ValidationError("Field 'city' must be at most 128 characters.")
    if len(phone) > 64:
        raise ValidationError("Field 'phone' must be at most 64 characters.")
    if len(email) > 255:
        raise ValidationError("Field 'email' must be at most 255 characters.")
    if len(gstin) > 64:
        raise ValidationError("Field 'gstin' must be at most 64 characters.")

    if Dealer.objects.filter(dealer_code=dealer_code).exists():
        raise DuplicateError(f"Dealer with code '{dealer_code}' already exists.")

    raw_credit = data.get("credit_limit", "0.00")
    if raw_credit in (None, ""):
        raw_credit = "0.00"
    if isinstance(raw_credit, bool):
        raise ValidationError("Invalid credit_limit.")
    try:
        credit_limit = Decimal(str(raw_credit).strip())
        if not credit_limit.is_finite() or credit_limit < Decimal("0"):
            raise ValidationError("credit_limit must be >= 0.")
        if credit_limit > MAX_CREDIT_LIMIT:
            raise ValidationError("credit_limit exceeds maximum allowed value.")
        exp = credit_limit.as_tuple().exponent
        if isinstance(exp, int) and exp < -2:
            raise ValidationError("credit_limit must have at most 2 decimal places.")
        credit_limit = credit_limit.quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError("Invalid credit_limit format.")

    try:
        with transaction.atomic():
            return Dealer.objects.create(
                dealer_code=dealer_code,
                name=name,
                city=city,
                phone=phone,
                email=email,
                gstin=gstin,
                credit_limit=credit_limit,
            )
    except IntegrityError:
        raise DuplicateError(f"Dealer with code '{dealer_code}' already exists.")
