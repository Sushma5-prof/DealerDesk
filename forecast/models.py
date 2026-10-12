from django.db import models


class ForecastRow(models.Model):
    sku = models.CharField(max_length=64, db_index=True)
    week_start = models.CharField(max_length=16)
    forecast_units = models.FloatField()

    class Meta:
        ordering = ["sku", "week_start"]
        unique_together = [("sku", "week_start")]

    def __str__(self) -> str:
        return f"{self.sku} @ {self.week_start}: {self.forecast_units}"
