from decimal import Decimal
from urllib.parse import urlencode
from django.conf import settings
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from catalogue.models import Product
from supplier_mock.mock_supplier import SupplierMock, build_public_feed
from .services import run_supplier_sync


class FakeResponse:
    def __init__(self, status_code: int, body: dict, headers: dict):
        self.status_code = status_code
        self._body = body
        self.headers = headers

    def json(self):
        return self._body


class MockSupplierSession:
    def __init__(self, mock: SupplierMock):
        self.mock = mock

    def get(self, url, params=None, headers=None, timeout=15):
        query_str = urlencode(params or {})
        path = f"/v1/products?{query_str}" if query_str else "/v1/products"
        status, body, extra = self.mock.handle(path, None, headers or {})
        return FakeResponse(status, body, extra)


@override_settings(
    SUPPLIER_API_URL="http://127.0.0.1:8099",
    SUPPLIER_API_KEY="dev-supplier-key",
)
class SupplierSyncTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.cat_path = settings.DATA_DIR / "catalogue.csv"
        self.feed = build_public_feed(str(self.cat_path))

    def test_sync_with_rate_limits_transient_duplicates_and_idempotency(self):
        # Seed one existing product with stock=77 to verify stock is untouched
        first_valid = next(it for it in self.feed if it.get("sku") == "BRK-1001" or it.get("sku"))
        Product.objects.create(
            sku=first_valid["sku"],
            name="Old Name",
            category=first_valid["category"],
            brand=first_valid["brand"],
            vehicle_fitment=first_valid["vehicle_fitment"],
            price=Decimal("100.00"),
            stock=77,
            description="Old desc",
        )

        mock = SupplierMock(
            self.feed,
            key="dev-supplier-key",
            throttle_every=4,
            retry_after=0,
            transient={2: [500]},
        )
        session = MockSupplierSession(mock)

        res1 = run_supplier_sync(session=session, sleep_fn=lambda _: None)
        self.assertEqual(len(res1["rejected"]), 3)
        self.assertEqual(res1["pages_fetched"], 4)
        self.assertGreater(res1["requests_made"], 4)
        # 57 picked from catalogue + 12 new supplier special = 69 unique valid SKUs
        self.assertEqual(
            res1["created"] + res1["updated"] + res1["unchanged"], 69
        )

        # Stock of existing product must remain 77
        prod = Product.objects.get(sku=first_valid["sku"])
        self.assertEqual(prod.stock, 77)

        # Second run on unchanged feed is idempotent
        mock2 = SupplierMock(self.feed, key="dev-supplier-key")
        res2 = run_supplier_sync(
            session=MockSupplierSession(mock2), sleep_fn=lambda _: None
        )
        self.assertEqual(res2["created"], 0)
        self.assertEqual(res2["updated"], 0)
        self.assertEqual(res2["unchanged"], 69)

    def test_outage_all_or_nothing_returns_502(self):
        initial_count = Product.objects.count()
        mock = SupplierMock(
            self.feed,
            key="dev-supplier-key",
            outage_pages=[1],
        )
        from unittest.mock import patch

        with patch(
            "supplier_sync.services.requests.Session",
            return_value=MockSupplierSession(mock),
        ), patch("supplier_sync.services.time.sleep", return_value=None):
            r = self.client.post("/api/sync/supplier/")
            self.assertEqual(r.status_code, 502)
            self.assertEqual(r.json()["error"]["code"], "SUPPLIER_UNAVAILABLE")
            self.assertEqual(Product.objects.count(), initial_count)
