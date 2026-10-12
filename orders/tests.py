from decimal import Decimal
import threading

from django.db import connections
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from catalogue.models import Product
from dealers.models import Dealer
from .models import Order


class OrdersAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.dealer = Dealer.objects.create(
            dealer_code="DLR-007",
            name="Wheels & Deals",
            credit_limit=Decimal("100000.00"),
        )
        self.p1 = Product.objects.create(
            sku="BRK-1044",
            name="Brake Pad Set - Bajaj Pulsar 150",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Bajaj Pulsar 150",
            price=Decimal("1459.50"),
            stock=10,
        )
        self.p2 = Product.objects.create(
            sku="OIL-1001",
            name="Coolant 1L - Universal",
            category="Engine & Oils",
            brand="Motul",
            vehicle_fitment="Universal",
            price=Decimal("100.25"),
            stock=5,
        )

    def test_create_draft_gst_and_pricing_lock(self):
        r = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [{"sku": "BRK-1044", "quantity": 3}],
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["status"], "DRAFT")
        self.assertEqual(body["subtotal"], "4378.50")
        self.assertEqual(body["tax_total"], "788.13")
        self.assertEqual(body["grand_total"], "5166.63")
        order_no = body["order_number"]

        # Product price change while DRAFT updates draft order price
        self.p1.price = Decimal("1500.00")
        self.p1.save()
        r_draft = self.client.get(f"/api/orders/{order_no}/")
        self.assertEqual(r_draft.json()["subtotal"], "4500.00")

        # Confirm locks price and deducts stock
        r_conf = self.client.post(f"/api/orders/{order_no}/confirm/")
        self.assertEqual(r_conf.status_code, 200)
        self.assertEqual(r_conf.json()["status"], "CONFIRMED")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 7)

        # Product price change after CONFIRM does not change confirmed order
        self.p1.price = Decimal("2000.00")
        self.p1.save()
        r_after = self.client.get(f"/api/orders/{order_no}/")
        self.assertEqual(r_after.json()["subtotal"], "4500.00")

    def test_validation_and_idempotency(self):
        # Empty items -> 400
        r = self.client.post(
            "/api/orders/", {"dealer_id": self.dealer.id, "items": []}, format="json"
        )
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], "VALIDATION_ERROR")

        # Duplicate SKU in same order -> 400
        r_dup = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [
                    {"sku": "BRK-1044", "quantity": 1},
                    {"sku": "BRK-1044", "quantity": 2},
                ],
            },
            format="json",
        )
        self.assertEqual(r_dup.status_code, 400)

        # Idempotency-Key
        payload = {
            "dealer_id": self.dealer.id,
            "items": [{"sku": "BRK-1044", "quantity": 2}],
        }
        r1 = self.client.post(
            "/api/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY="key-123"
        )
        self.assertEqual(r1.status_code, 201)
        r2 = self.client.post(
            "/api/orders/", payload, format="json", HTTP_IDEMPOTENCY_KEY="key-123"
        )
        self.assertEqual(r2.status_code, 200)
        self.assertEqual(r1.json()["order_number"], r2.json()["order_number"])

        # Same key, different body -> 409 IDEMPOTENCY_CONFLICT
        r3 = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [{"sku": "BRK-1044", "quantity": 5}],
            },
            format="json",
            HTTP_IDEMPOTENCY_KEY="key-123",
        )
        self.assertEqual(r3.status_code, 409)
        self.assertEqual(r3.json()["error"]["code"], "IDEMPOTENCY_CONFLICT")

    def test_insufficient_stock_and_lifecycle_transitions(self):
        r = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [
                    {"sku": "BRK-1044", "quantity": 15},
                    {"sku": "OIL-1001", "quantity": 2},
                ],
            },
            format="json",
        )
        order_no = r.json()["order_number"]

        # Confirm fails all-or-nothing
        r_conf = self.client.post(f"/api/orders/{order_no}/confirm/")
        self.assertEqual(r_conf.status_code, 409)
        err = r_conf.json()["error"]
        self.assertEqual(err["code"], "INSUFFICIENT_STOCK")
        self.assertEqual(
            err["details"],
            [{"sku": "BRK-1044", "requested": 15, "available": 10}],
        )
        self.p2.refresh_from_db()
        self.assertEqual(self.p2.stock, 5)

        # Edit while DRAFT works
        r_put = self.client.put(
            f"/api/orders/{order_no}/",
            {"items": [{"sku": "BRK-1044", "quantity": 4}]},
            format="json",
        )
        self.assertEqual(r_put.status_code, 200)

        # Confirm -> Cancel restores stock
        self.client.post(f"/api/orders/{order_no}/confirm/")
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 6)

        # Edit while CONFIRMED -> 409 ORDER_LOCKED
        r_locked = self.client.put(
            f"/api/orders/{order_no}/",
            {"items": [{"sku": "BRK-1044", "quantity": 1}]},
            format="json",
        )
        self.assertEqual(r_locked.status_code, 409)
        self.assertEqual(r_locked.json()["error"]["code"], "ORDER_LOCKED")

        # Cancel confirmed restores stock
        r_can = self.client.post(f"/api/orders/{order_no}/cancel/")
        self.assertEqual(r_can.status_code, 200)
        self.p1.refresh_from_db()
        self.assertEqual(self.p1.stock, 10)

        # Cancel again -> 409 INVALID_TRANSITION
        r_can2 = self.client.post(f"/api/orders/{order_no}/cancel/")
        self.assertEqual(r_can2.status_code, 409)
        self.assertEqual(r_can2.json()["error"]["code"], "INVALID_TRANSITION")

    def test_daily_sequence_boundary_and_extreme_inputs(self):
        from django.utils import timezone
        from .models import DailySequence

        today = timezone.localdate()
        DailySequence.objects.update_or_create(
            date=today, defaults={"last_seq": 9998}
        )

        # 9999th order succeeds with 4-digit -9999
        r_9999 = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [{"sku": "BRK-1044", "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(r_9999.status_code, 201)
        self.assertTrue(r_9999.json()["order_number"].endswith("-9999"))

        # 10000th order is rejected with 400 VALIDATION_ERROR and rolls back sequence
        r_10000 = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [{"sku": "BRK-1044", "quantity": 1}],
            },
            format="json",
        )
        self.assertEqual(r_10000.status_code, 400)
        self.assertEqual(r_10000.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertEqual(DailySequence.objects.get(date=today).last_seq, 9999)

        # Extreme quantity -> 400 VALIDATION_ERROR
        r_huge = self.client.post(
            "/api/orders/",
            {
                "dealer_id": self.dealer.id,
                "items": [{"sku": "BRK-1044", "quantity": 10_000_000}],
            },
            format="json",
        )
        self.assertEqual(r_huge.status_code, 400)
        self.assertEqual(r_huge.json()["error"]["code"], "VALIDATION_ERROR")


class OrdersConcurrencyTest(TransactionTestCase):
    def test_concurrent_confirm_never_oversells(self):
        dealer = Dealer.objects.create(
            dealer_code="DLR-CONC", name="Concurrency Dealer"
        )
        product = Product.objects.create(
            sku="BRK-CONC",
            name="Concurrent Brake Pad",
            category="Brakes",
            brand="Endurance",
            vehicle_fitment="Universal",
            price=Decimal("500.00"),
            stock=5,
        )
        client = APIClient()
        orders = []
        for _ in range(4):
            r = client.post(
                "/api/orders/",
                {
                    "dealer_id": dealer.id,
                    "items": [{"sku": "BRK-CONC", "quantity": 3}],
                },
                format="json",
            )
            orders.append(r.json()["order_number"])

        statuses = []

        def confirm_worker(ord_no):
            try:
                c = APIClient()
                resp = c.post(f"/api/orders/{ord_no}/confirm/")
                statuses.append(resp.status_code)
            finally:
                connections.close_all()

        threads = [
            threading.Thread(target=confirm_worker, args=(o,)) for o in orders
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Only 1 order of 3 units can succeed from stock=5; 3 must fail with 409
        self.assertEqual(sorted(statuses), [200, 409, 409, 409])
        product.refresh_from_db()
        self.assertEqual(product.stock, 2)
