from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Dealer


class DealersAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.d1 = Dealer.objects.create(
            dealer_code="DLR-007",
            name="Wheels & Deals",
            city="Hyderabad",
            phone="9214159864",
            email="orders@wheelsdeals.in",
            gstin="29AABH2853G1Z8",
            credit_limit=Decimal("250000.00"),
        )

    def test_list_and_detail_dealer(self):
        r = self.client.get("/api/dealers/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["count"], 1)
        self.assertEqual(r.json()["results"][0]["credit_limit"], "250000.00")

        r_det = self.client.get(f"/api/dealers/{self.d1.id}/")
        self.assertEqual(r_det.status_code, 200)
        self.assertEqual(r_det.json()["dealer_code"], "DLR-007")

        r_404 = self.client.get("/api/dealers/99999/")
        self.assertEqual(r_404.status_code, 404)
        self.assertEqual(r_404.json()["error"]["code"], "NOT_FOUND")

    def test_create_dealer_and_duplicate_and_validation(self):
        r = self.client.post(
            "/api/dealers/",
            {"dealer_code": "DLR-100", "name": "New Dealer"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.json()["credit_limit"], "0.00")

        # Duplicate dealer_code -> 409 DUPLICATE
        r_dup = self.client.post(
            "/api/dealers/",
            {"dealer_code": "DLR-100", "name": "Another Name"},
            format="json",
        )
        self.assertEqual(r_dup.status_code, 409)
        self.assertEqual(r_dup.json()["error"]["code"], "DUPLICATE")

        # Missing required fields -> 400 VALIDATION_ERROR
        r_bad = self.client.post(
            "/api/dealers/",
            {"dealer_code": "DLR-101"},
            format="json",
        )
        self.assertEqual(r_bad.status_code, 400)
        self.assertEqual(r_bad.json()["error"]["code"], "VALIDATION_ERROR")
