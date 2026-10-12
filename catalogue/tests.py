from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Product


class CatalogueAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.p1 = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            stock=136,
            description="Endurance brake pad set.",
        )
        self.p2 = Product.objects.create(
            sku="OIL-1001",
            name="Coolant 1L - Universal",
            category="Engine & Oils",
            brand="Motul",
            vehicle_fitment="Universal",
            price=Decimal("604.25"),
            stock=198,
            description="Motul coolant.",
        )

    def test_list_products_and_filters(self):
        r = self.client.get("/api/products/")
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data["count"], 2)
        self.assertEqual(data["results"][0]["price"], "1459.50")

        # Search filter (case-insensitive on sku, name, brand)
        r = self.client.get("/api/products/?search=motul")
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["results"][0]["sku"], "OIL-1001")

        # Category filter (exact)
        r = self.client.get("/api/products/?category=Brakes")
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["results"][0]["sku"], "BRK-1044")

        # Vehicle filter (icontains)
        r = self.client.get("/api/products/?vehicle=pulsar")
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["results"][0]["sku"], "BRK-1044")

    def test_create_product_and_duplicate_and_validation(self):
        payload = {
            "sku": "FIL-9999",
            "name": "Air Filter - KTM Duke 390",
            "category": "Filters",
            "brand": "Mahle",
            "vehicle_fitment": "KTM Duke 390",
            "price": "850.00",
            "description": "High flow air filter",
        }
        r = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["stock"], 0)
        self.assertEqual(r.json()["price"], "850.00")

        # Duplicate SKU -> 409 DUPLICATE
        r_dup = self.client.post("/api/products/", payload, format="json")
        self.assertEqual(r_dup.status_code, 409)
        self.assertEqual(r_dup.json()["error"]["code"], "DUPLICATE")

        # Invalid price (<= 0 or >2 decimals) -> 400 VALIDATION_ERROR
        bad_payload = dict(payload, sku="FIL-9998", price="-10.00")
        r_bad = self.client.post("/api/products/", bad_payload, format="json")
        self.assertEqual(r_bad.status_code, 400)
        self.assertEqual(r_bad.json()["error"]["code"], "VALIDATION_ERROR")

        bad_dec = dict(payload, sku="FIL-9997", price="10.999")
        r_bad2 = self.client.post("/api/products/", bad_dec, format="json")
        self.assertEqual(r_bad2.status_code, 400)
        self.assertEqual(r_bad2.json()["error"]["code"], "VALIDATION_ERROR")

    def test_detail_and_patch_product(self):
        r = self.client.get("/api/products/BRK-1044/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["sku"], "BRK-1044")

        r_404 = self.client.get("/api/products/NOPE-000/")
        self.assertEqual(r_404.status_code, 404)
        self.assertEqual(r_404.json()["error"]["code"], "NOT_FOUND")

        r_patch = self.client.patch(
            "/api/products/BRK-1044/", {"price": "1500.00"}, format="json"
        )
        self.assertEqual(r_patch.status_code, 200)
        self.assertEqual(r_patch.json()["price"], "1500.00")

        # Cannot change SKU
        r_sku = self.client.patch(
            "/api/products/BRK-1044/", {"sku": "NEW-SKU"}, format="json"
        )
        self.assertEqual(r_sku.status_code, 400)
        self.assertEqual(r_sku.json()["error"]["code"], "VALIDATION_ERROR")

    def test_inventory_put(self):
        r = self.client.put(
            "/api/inventory/BRK-1044/",
            {"quantity": 25, "reason": "stock count correction"},
            format="json",
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json(), {"sku": "BRK-1044", "quantity": 25})

        # Verify GET product reflects updated stock
        r_get = self.client.get("/api/products/BRK-1044/")
        self.assertEqual(r_get.json()["stock"], 25)

        # Negative quantity -> 400
        r_neg = self.client.put(
            "/api/inventory/BRK-1044/", {"quantity": -1}, format="json"
        )
        self.assertEqual(r_neg.status_code, 400)
        self.assertEqual(r_neg.json()["error"]["code"], "VALIDATION_ERROR")

        # Unknown SKU -> 404
        r_404 = self.client.put(
            "/api/inventory/UNKNOWN-1/", {"quantity": 10}, format="json"
        )
        self.assertEqual(r_404.status_code, 404)
        self.assertEqual(r_404.json()["error"]["code"], "NOT_FOUND")
