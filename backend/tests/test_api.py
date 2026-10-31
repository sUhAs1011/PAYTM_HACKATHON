import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.main import app
from fastapi.testclient import TestClient
from app.credit.schema.schema import SweepDayPreview, SweepPreviewResponse


class ApiWiringTests(unittest.TestCase):
    def test_module_four_compatible_routes_are_registered(self):
        # FastAPI 0.162 keeps included routers lazy, so app.routes also has
        # internal wrapper entries without `.path`. OpenAPI enumerates HTTP
        # routes; direct mounts add static paths, and the WS path is verified
        # with an actual TestClient websocket connection below.
        paths = set(app.openapi()["paths"])
        paths.update(route.path for route in app.routes if getattr(route, "path", None))
        self.assertIn("/api/parcha/scan", paths)
        self.assertIn("/api/parcha/{invoice_id}/resolve", paths)
        self.assertIn("/api/parcha/{invoice_id}/export", paths)
        self.assertIn("/api/demo/load-sample", paths)
        self.assertIn("/static", paths)
        self.assertIn("/api/parcha/{invoice_id}/validate", paths)
        self.assertIn("/api/parcha/{invoice_id}/alerts", paths)
        self.assertIn("/api/parcha/{invoice_id}/price-analysis", paths)
        self.assertIn("/api/credit/{invoice_id}/recommendation", paths)
        self.assertIn("/api/credit/{invoice_id}/sweep-preview", paths)
        self.assertIn("/api/credit/loans/{loan_id}/schedule", paths)
        self.assertIn("/api/credit/loans/{loan_id}/alerts", paths)
        self.assertNotIn("/api/credit/{invoice_id}/accept", paths)
        self.assertNotIn("/api/credit/loans/{loan_id}/simulate-week", paths)
        with TestClient(app) as client:
            with client.websocket_connect("/ws/counter"):
                pass

    def test_invalid_uuid_is_rejected_without_database_access(self):
        response = TestClient(app).get("/api/parcha/not-a-uuid/validate")
        self.assertEqual(response.status_code, 422)
        self.assertTrue(response.headers.get("X-Request-ID"))

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

    def test_demo_fixture_resolves_without_database_writes(self):
        with patch("app.api.resolve_router.get_client", new=AsyncMock()) as get_client:
            with TestClient(app) as client:
                response = client.post(
                    "/api/parcha/demo-golden-fixture-001/resolve",
                    json={"action": "APPROVE_SPLIT", "tenure_days": 7},
                )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["invoice_id"], "demo-golden-fixture-001")
        self.assertEqual(payload["loan_schedule"]["principal"], 13860.0)
        self.assertEqual(payload["loan_schedule"]["daily_deduction"], 1980.0)
        self.assertEqual(payload["loan_schedule"]["remaining_balance"], 11880.0)
        get_client.assert_not_awaited()

    def test_sweep_preview_rejects_invalid_invoice_uuid_without_database_access(self):
        response = TestClient(app).get("/api/credit/not-a-uuid/sweep-preview")
        self.assertEqual(response.status_code, 422)

    def test_sweep_preview_returns_read_only_projection_shape(self):
        preview = SweepPreviewResponse(
            invoice_id="00000000-0000-0000-0000-000000000001",
            loan_id="00000000-0000-0000-0000-000000000002",
            forecast_source="RECENT_7D_QR_REPLAY",
            starting_paytm_balance=Decimal("25.00"),
            daily_deduction=Decimal("50.00"),
            autopay_mandate_active=True,
            days=[
                SweepDayPreview(
                    day=2,
                    forecast_qr_inflow=Decimal("10.00"),
                    due=Decimal("50.00"),
                    paytm_balance_before=Decimal("35.00"),
                    qr_deduction=Decimal("35.00"),
                    bank_mandate_deduction=Decimal("15.00"),
                    missed=Decimal("0.00"),
                    paytm_balance_after=Decimal("0.00"),
                    projected_loan_balance=Decimal("300.00"),
                    mandate_triggered=True,
                )
            ],
        )
        with patch(
            "app.credit.routes.controller.get_sweep_preview",
            new=AsyncMock(return_value=preview),
        ):
            response = TestClient(app).get(
                "/api/credit/00000000-0000-0000-0000-000000000001/sweep-preview"
            )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["simulation_only"])
        self.assertEqual(payload["days"][0]["bank_mandate_deduction"], 15.0)
        self.assertIsInstance(payload["starting_paytm_balance"], float)


if __name__ == "__main__":
    unittest.main()
