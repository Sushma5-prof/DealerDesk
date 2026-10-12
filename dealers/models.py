from decimal import Decimal
from django.db import models


class Dealer(models.Model):
    dealer_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    city = models.CharField(max_length=128, blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.CharField(max_length=255, blank=True, default="")
    gstin = models.CharField(max_length=64, blank=True, default="")
    credit_limit = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
    )

    class Meta:
        ordering = ["id"]

    def __str__(self) -> str:
        return f"{self.dealer_code} - {self.name}"
