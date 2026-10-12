import csv
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from catalogue.models import Product
from dealers.models import Dealer
from forecast.models import ForecastRow


class Command(BaseCommand):
    help = "Load the files in data/ into the database. Must be safe to run more than once."

    def handle(self, *args, **options):
        data_dir = settings.DATA_DIR
        self._seed_catalogue(data_dir / "catalogue.csv")
        self._seed_dealers(data_dir / "dealers.csv")
        self._seed_forecast(settings.ML_DIR / "forecast.csv")

    def _seed_catalogue(self, csv_path):
        if not csv_path.exists():
            self.stdout.write(self.style.WARNING(f"{csv_path} not found"))
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            products = [
                Product(
                    sku=row["sku"].strip(),
                    name=row["name"].strip(),
                    category=row["category"].strip(),
                    brand=row["brand"].strip(),
                    vehicle_fitment=row["vehicle_fitment"].strip(),
                    price=Decimal(row["price"].strip()),
                    stock=int(row["stock"].strip()),
                    description=row.get("description") or "",
                )
                for row in reader
            ]

        with transaction.atomic():
            Product.objects.bulk_create(
                products,
                update_conflicts=True,
                unique_fields=["sku"],
                update_fields=[
                    "name",
                    "category",
                    "brand",
                    "vehicle_fitment",
                    "price",
                    "stock",
                    "description",
                ],
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Product.objects.count()} products from {csv_path.name}"
            )
        )

    def _seed_dealers(self, csv_path):
        if not csv_path.exists():
            self.stdout.write(self.style.WARNING(f"{csv_path} not found"))
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            dealers = [
                Dealer(
                    dealer_code=row["dealer_code"].strip(),
                    name=row["name"].strip(),
                    city=row.get("city", "").strip(),
                    phone=row.get("phone", "").strip(),
                    email=row.get("email", "").strip(),
                    gstin=row.get("gstin", "").strip(),
                    credit_limit=Decimal(row.get("credit_limit", "0.00").strip()),
                )
                for row in reader
            ]

        with transaction.atomic():
            Dealer.objects.bulk_create(
                dealers,
                update_conflicts=True,
                unique_fields=["dealer_code"],
                update_fields=[
                    "name",
                    "city",
                    "phone",
                    "email",
                    "gstin",
                    "credit_limit",
                ],
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {Dealer.objects.count()} dealers from {csv_path.name}"
            )
        )

    def _seed_forecast(self, csv_path):
        if not csv_path.exists():
            return

        with open(csv_path, encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = [
                ForecastRow(
                    sku=row["sku"].strip(),
                    week_start=row["week_start"].strip(),
                    forecast_units=float(row["forecast_units"].strip()),
                )
                for row in reader
            ]

        with transaction.atomic():
            ForecastRow.objects.bulk_create(
                rows,
                update_conflicts=True,
                unique_fields=["sku", "week_start"],
                update_fields=["forecast_units"],
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {ForecastRow.objects.count()} forecast rows from {csv_path.name}"
            )
        )
