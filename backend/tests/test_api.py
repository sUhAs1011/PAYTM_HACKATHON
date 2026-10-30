import unittest

from app.main import app
from fastapi.testclient import TestClient


class ApiWiringTests(unittest.TestCase):
    def test_module_four_routes_are_registered(self):
        paths = {route.path for route in app.routes}
        self.assertIn("/api/parcha/{invoice_id}/validate", paths)
        self.assertIn("/api/parcha/{invoice_id}/alerts", paths)
        self.assertIn("/api/parcha/{invoice_id}/price-analysis", paths)
        self.assertIn("/api/credit/{invoice_id}/recommendation", paths)
        self.assertIn("/api/credit/{invoice_id}/accept", paths)
        self.assertIn("/api/credit/loans/{loan_id}/simulate-week", paths)

    def test_invalid_uuid_is_rejected_without_database_access(self):
        response = TestClient(app).get("/api/parcha/not-a-uuid/validate")
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.headers.get("X-Request-ID"))


if __name__ == "__main__":
    unittest.main()
