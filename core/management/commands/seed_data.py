import csv
from decimal import Decimal
from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from catalogue.models import Product


class Command(BaseCommand):
    help = "Load the files in data/ into the database. Must be safe to run more than once."

    def handle(self, *args, **options):
        data_dir = settings.DATA_DIR
        self._seed_catalogue(data_dir / "catalogue.csv")

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
