"""
Centralised error handling for DealerDesk.

Contract §3 error shape (exact):
  {"error": {"code": "SOME_CODE", "message": "Human readable text", "details": []}}

All views raise DealerDeskError subclasses; the custom_exception_handler
converts them (and DRF's built-in exceptions) to that shape.
"""
from rest_framework import status
from rest_framework.exceptions import APIException
from rest_framework.views import exception_handler as drf_exception_handler


# ---------------------------------------------------------------------------
# Base exception
# ---------------------------------------------------------------------------

class DealerDeskError(APIException):
    """Base for all domain errors.  Subclasses set status_code and default_code."""

    default_code = "ERROR"
    default_detail = "An error occurred."

    def __init__(self, message: str = "", details: list | None = None, **kwargs):
        self.message = message or self.default_detail
        self.details = details or []
        super().__init__(detail=self.message)


# ---------------------------------------------------------------------------
# Concrete error types
# ---------------------------------------------------------------------------

class ValidationError(DealerDeskError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "VALIDATION_ERROR"
    default_detail = "Validation failed."


class NotFoundError(DealerDeskError):
    status_code = status.HTTP_404_NOT_FOUND
    default_code = "NOT_FOUND"
    default_detail = "Resource not found."


class DuplicateError(DealerDeskError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "DUPLICATE"
    default_detail = "A resource with that identifier already exists."


class InsufficientStockError(DealerDeskError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "INSUFFICIENT_STOCK"
    default_detail = "Insufficient stock."


class InvalidTransitionError(DealerDeskError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "INVALID_TRANSITION"
    default_detail = "Status change not allowed from the current status."


class OrderLockedError(DealerDeskError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "ORDER_LOCKED"
    default_detail = "Order cannot be edited in its current status."


class IdempotencyConflictError(DealerDeskError):
    status_code = status.HTTP_409_CONFLICT
    default_code = "IDEMPOTENCY_CONFLICT"
    default_detail = "Idempotency key reused with a different request body."


class SupplierUnavailableError(DealerDeskError):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "SUPPLIER_UNAVAILABLE"
    default_detail = "Supplier sync could not fetch the full feed."


# ---------------------------------------------------------------------------
# Custom exception handler (registered in settings via EXCEPTION_HANDLER)
# ---------------------------------------------------------------------------

def custom_exception_handler(exc, context):
    """
    Wraps all exceptions into the contract error shape:
      {"error": {"code": "...", "message": "...", "details": [...]}}
    """
    if isinstance(exc, DealerDeskError):
        from rest_framework.response import Response

        return Response(
            {
                "error": {
                    "code": exc.default_code,
                    "message": exc.message,
                    "details": exc.details,
                }
            },
            status=exc.status_code,
        )

    # Let DRF handle its own validation errors, then reformat.
    response = drf_exception_handler(exc, context)
    if response is not None:
        from rest_framework import exceptions as drf_exc

        if isinstance(exc, (drf_exc.ValidationError, drf_exc.ParseError)):
            code = "VALIDATION_ERROR"
        elif isinstance(exc, drf_exc.NotFound):
            code = "NOT_FOUND"
        elif isinstance(exc, drf_exc.MethodNotAllowed):
            code = "METHOD_NOT_ALLOWED"
        else:
            code = "ERROR"

        # Flatten DRF's detail into a plain string.
        detail = exc.detail if hasattr(exc, "detail") else str(exc)
        if isinstance(detail, dict):
            message = "; ".join(f"{k}: {v}" for k, v in detail.items())
        elif isinstance(detail, list):
            message = "; ".join(str(d) for d in detail)
        else:
            message = str(detail)

        response.data = {
            "error": {
                "code": code,
                "message": message,
                "details": [],
            }
        }

    return response
