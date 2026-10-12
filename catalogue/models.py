from decimal import Decimal
from django.core.validators import MinValueValidator
from django.db import models


class Product(models.Model):
    sku = models.CharField(max_length=64, primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=128, db_index=True)
    brand = models.CharField(max_length=128, db_index=True)
    vehicle_fitment = models.CharField(max_length=255)
    price = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    stock = models.IntegerField(
        default=0,
        validators=[MinValueValidator(0)],
    )
    description = models.TextField(blank=True, default="")

    class Meta:
        ordering = ["sku"]

    def __str__(self) -> str:
        return f"{self.sku} - {self.name}"
