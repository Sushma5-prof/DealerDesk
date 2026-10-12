import math
from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient

from catalogue.models import Product
from .services import compute_reorder_metrics, compute_sample_sigma


class ForecastAndReorderTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.p1 = Product.objects.create(
            sku="FIL-1016",
            name="Oil Filter - Test",
            category="Filters",
            brand="Mahle",
            vehicle_fitment="Universal",
            price=Decimal("300.00"),
            stock=10,
        )

    def test_pure_reorder_formula_and_sigma(self):
        # Test sample standard deviation (n-1)
        series = [10.0, 20.0, 30.0]
        self.assertAlmostEqual(compute_sample_sigma(series), 10.0)

        # Test exact contract formula
        res = compute_reorder_metrics(
            sku="FIL-1012",
            current_stock=40,
            lead_time_weeks=2,
            forecast_units=[31.4, 30.3, 25.0, 25.0],
            sigma=3.8,
        )
        self.assertEqual(res["lead_time_demand"], 61.7)
        expected_ss = math.ceil(1.65 * 3.8 * math.sqrt(2))
        self.assertEqual(res["safety_stock"], expected_ss)
        self.assertEqual(res["reorder_point"], round(61.7 + expected_ss, 4))
        self.assertEqual(
            res["reorder_qty"], max(0, math.ceil(res["reorder_point"] - 40))
        )

    def test_forecast_endpoint_and_404(self):
        r = self.client.get("/api/forecast/FIL-1016/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["sku"], "FIL-1016")
        self.assertEqual(
            [w["week_start"] for w in body["forecast"]],
            ["2026-09-28", "2026-10-05", "2026-10-12", "2026-10-19"],
        )

        # Non-forecast SKU -> 404
        r_404 = self.client.get("/api/forecast/NOT-A-FORECAST-SKU/")
        self.assertEqual(r_404.status_code, 404)
        self.assertEqual(r_404.json()["error"]["code"], "NOT_FOUND")

    def test_reorder_suggestions_live_stock(self):
        r1 = self.client.get("/api/reorder-suggestions/")
        self.assertEqual(r1.status_code, 200)
        results1 = r1.json()["results"]
        self.assertEqual(len(results1), 40)
        fil_entry1 = next(x for x in results1 if x["sku"] == "FIL-1016")
        self.assertEqual(fil_entry1["current_stock"], 10)

        # Update stock in DB to 5000 -> reorder_qty becomes 0
        self.p1.stock = 5000
        self.p1.save(update_fields=["stock"])

        r2 = self.client.get("/api/reorder-suggestions/")
        fil_entry2 = next(x for x in r2.json()["results"] if x["sku"] == "FIL-1016")
        self.assertEqual(fil_entry2["current_stock"], 5000)
        self.assertEqual(fil_entry2["reorder_qty"], 0)
