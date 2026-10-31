import unittest

from app.main import app
from fastapi.testclient import TestClient


class ApiWiringTests(unittest.TestCase):
    def test_module_four_compatible_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/parcha/scan", paths)
        self.assertIn("/api/parcha/pending-review", paths)
        self.assertIn("/api/parcha/{invoice_id}/review", paths)
        self.assertIn("/api/parcha/{invoice_id}/confirm", paths)
        self.assertIn("/api/parcha/{invoice_id}/resolve", paths)
        self.assertIn("/api/parcha/{invoice_id}/export", paths)
        self.assertIn("/api/demo/load-sample", paths)
        self.assertIn("/ws/counter", paths)
        self.assertIn("/static", paths)
        self.assertIn("/api/parcha/{invoice_id}/validate", paths)
        self.assertIn("/api/parcha/{invoice_id}/alerts", paths)
        self.assertIn("/api/parcha/{invoice_id}/price-analysis", paths)
        self.assertIn("/api/credit/{invoice_id}/recommendation", paths)
        self.assertIn("/api/credit/loans/{loan_id}/schedule", paths)
        self.assertIn("/api/credit/loans/{loan_id}/alerts", paths)
        self.assertNotIn("/api/credit/{invoice_id}/accept", paths)
        self.assertNotIn("/api/credit/loans/{loan_id}/simulate-week", paths)

    def test_invalid_uuid_is_rejected_without_database_access(self):
        response = TestClient(app).get("/api/parcha/not-a-uuid/validate")
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.headers.get("X-Request-ID"))

    def test_review_routes_reject_invalid_uuids_before_database_access(self):
        client = TestClient(app)
        merchant_id = "a0000000-0000-0000-0000-000000000001"
        detail = client.get(
            f"/api/parcha/not-a-uuid/review?merchant_id={merchant_id}"
        )
        pending = client.get("/api/parcha/pending-review?merchant_id=not-a-uuid")
        self.assertEqual(detail.status_code, 422)
        self.assertEqual(pending.status_code, 422)

    def test_confirm_requires_merchant_scope(self):
        response = TestClient(app).post(
            "/api/parcha/00000000-0000-0000-0000-000000000001/confirm",
            json={"corrections": []},
        )
        self.assertEqual(response.status_code, 422)

    def test_weekly_credit_write_routes_are_not_exposed(self):
        client = TestClient(app)
        accept = client.post(
            "/api/credit/00000000-0000-0000-0000-000000000001/accept",
            json={"mandate_accepted": True},
        )
        simulate = client.post(
            "/api/credit/loans/00000000-0000-0000-0000-000000000001/simulate-week"
        )
        self.assertEqual(accept.status_code, 404)
        self.assertEqual(simulate.status_code, 404)


if __name__ == "__main__":
    unittest.main()
