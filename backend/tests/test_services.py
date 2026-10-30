import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.bill_validation.service.service import validate_bill
from app.credit.service.service import (
    get_credit_alerts,
    get_credit_recommendation,
    simulate_credit_week,
)
from app.price_analysis.service.service import analyze_invoice_prices


class BillValidationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_service_fetches_and_validates_invoice_lines(self):
        invoice = {"id": "invoice-1", "billed_total": "105.00"}
        line = {
            "id": "line-1",
            "raw_item_name": "Tea",
            "billed_qty": 1,
            "free_qty": 0,
            "billed_rate": "100.00",
            "tax_percent": "5.00",
            "true_landed_cost": "105.00",
            "ocr_confidence": "0.95",
        }
        with (
            patch(
                "app.bill_validation.service.service.get_invoice",
                new=AsyncMock(return_value=invoice),
            ),
            patch(
                "app.bill_validation.service.service.get_invoice_line_items",
                new=AsyncMock(return_value=[line]),
            ),
        ):
            result = await validate_bill("invoice-1")
        self.assertTrue(result["is_valid"])
        self.assertEqual(result["recomputed_total"], Decimal("105.00"))
        self.assertEqual(result["alerts"], [])


class PriceAnalysisServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_peer_analysis_does_not_expose_peer_ids(self):
        invoice = {
            "id": "invoice-1",
            "merchant_id": "merchant-current",
            "supplier_id": "supplier-1",
        }
        line = {
            "id": "line-1",
            "canonical_sku_id": "sku-1",
            "raw_item_name": "Oil",
            "billed_rate": "150.00",
        }
        peers = [(f"peer-{index}", "100.00") for index in range(5)]
        with (
            patch(
                "app.price_analysis.service.service.get_invoice",
                new=AsyncMock(return_value=invoice),
            ),
            patch(
                "app.price_analysis.service.service.get_merchant",
                new=AsyncMock(return_value={"id": "merchant-current", "pincode": "560103"}),
            ),
            patch(
                "app.price_analysis.service.service.get_supplier",
                new=AsyncMock(return_value={"id": "supplier-1"}),
            ),
            patch(
                "app.price_analysis.service.service.get_invoice_line_items",
                new=AsyncMock(return_value=[line]),
            ),
            patch(
                "app.price_analysis.service.service.get_supplier_history",
                new=AsyncMock(return_value=[{"billed_rate": "120.00"}]),
            ),
            patch(
                "app.price_analysis.service.service.get_pincode_peer_rates",
                new=AsyncMock(return_value=peers),
            ),
        ):
            result = await analyze_invoice_prices("invoice-1")
        self.assertTrue(result["items"][0]["analysis"]["pincode_benchmark"]["gate_active"])
        self.assertEqual(
            result["items"][0]["analysis"]["pincode_benchmark"]["average_rate"],
            Decimal("100.00"),
        )
        self.assertNotIn("peer-0", str(result))


class CreditRecommendationServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_incoming_qr_history_for_weekly_cap(self):
        now = datetime.now(timezone.utc)
        with (
            patch(
                "app.credit.service.service.get_invoice",
                new=AsyncMock(
                    return_value={
                        "id": "invoice-1",
                        "merchant_id": "merchant-1",
                        "billed_total": "100.00",
                    }
                ),
            ),
            patch(
                "app.credit.service.service.get_merchant",
                new=AsyncMock(
                    return_value={
                        "id": "merchant-1",
                        "upi_vpa": "shop@paytm",
                        "avg_daily_qr_volume": "1000.00",
                    }
                ),
            ),
            patch(
                "app.credit.service.service.get_transactions",
                new=AsyncMock(
                    return_value=[
                        {
                            "amount": "3000.00",
                            "txn_status": "SUCCESS",
                            "created_at": (now - timedelta(days=1)).isoformat(),
                        }
                    ]
                ),
            ),
        ):
            result = await get_credit_recommendation("invoice-1")
        self.assertEqual(result["history_basis"], "TRANSACTIONS_30D")
        self.assertEqual(result["average_weekly_earnings"], Decimal("700.00"))
        self.assertEqual(result["weekly_cap_limit"], Decimal("245.00"))
        self.assertEqual(result["principal"], Decimal("100.00"))

    async def test_week_simulation_deducts_qr_and_updates_loan(self):
        now = datetime.now(timezone.utc)
        loan = {
            "id": "loan-1",
            "invoice_id": "invoice-1",
            "merchant_id": "merchant-1",
            "principal_amount": "100.00",
            "remaining_balance": "100.00",
            "tenure_days": 21,
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=8)).isoformat(),
        }
        ledger = [
            {
                "kind": "LOAN_DISBURSEMENT_SIMULATED",
                "entry_ts": (now - timedelta(days=7)).isoformat(),
            }
        ]
        with (
            patch(
                "app.credit.service.service.get_loan",
                new=AsyncMock(return_value=loan),
            ),
            patch(
                "app.credit.service.service.get_loan_ledger",
                new=AsyncMock(return_value=ledger),
            ),
            patch(
                "app.credit.service.service.get_merchant",
                new=AsyncMock(return_value={"upi_vpa": "shop@paytm"}),
            ),
            patch(
                "app.credit.service.service.get_transactions",
                new=AsyncMock(
                    return_value=[
                        {"amount": "100.00", "txn_status": "SUCCESS"}
                    ]
                ),
            ),
            patch(
                "app.credit.service.service.create_ledger_entry",
                new=AsyncMock(),
            ),
            patch(
                "app.credit.service.service.update_loan",
                new=AsyncMock(),
            ) as update_loan,
        ):
            result = await simulate_credit_week("loan-1")
        self.assertEqual(result["week"], 1)
        self.assertEqual(result["paid"], Decimal("33.33"))
        self.assertEqual(result["remaining_balance"], Decimal("66.67"))
        self.assertEqual(result["status"], "ACTIVE")
        update_loan.assert_awaited_once()

    async def test_week_simulation_alerts_when_qr_receipts_are_missing(self):
        now = datetime.now(timezone.utc)
        loan = {
            "id": "loan-1",
            "merchant_id": "merchant-1",
            "principal_amount": "100.00",
            "remaining_balance": "100.00",
            "tenure_days": 21,
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=8)).isoformat(),
        }
        ledger = [
            {
                "kind": "LOAN_DISBURSEMENT_SIMULATED",
                "entry_ts": (now - timedelta(days=7)).isoformat(),
            }
        ]
        with (
            patch(
                "app.credit.service.service.get_loan",
                new=AsyncMock(return_value=loan),
            ),
            patch(
                "app.credit.service.service.get_loan_ledger",
                new=AsyncMock(return_value=ledger),
            ),
            patch(
                "app.credit.service.service.get_merchant",
                new=AsyncMock(return_value={"upi_vpa": "shop@paytm"}),
            ),
            patch(
                "app.credit.service.service.get_transactions",
                new=AsyncMock(return_value=[]),
            ),
            patch(
                "app.credit.service.service.create_ledger_entry",
                new=AsyncMock(),
            ) as create_entry,
            patch(
                "app.credit.service.service.update_loan",
                new=AsyncMock(),
            ),
        ):
            result = await simulate_credit_week("loan-1")
        self.assertEqual(result["paid"], Decimal("0.00"))
        self.assertEqual(result["missed"], Decimal("33.33"))
        self.assertEqual(result["alerts"][0]["code"], "WEEKLY_EMI_MISSED")
        self.assertEqual(create_entry.await_count, 1)

    async def test_partial_week_uses_one_ledger_entry_for_daily_unique_constraint(self):
        now = datetime.now(timezone.utc)
        loan = {
            "id": "loan-1",
            "merchant_id": "merchant-1",
            "principal_amount": "100.00",
            "remaining_balance": "100.00",
            "tenure_days": 21,
            "status": "ACTIVE",
            "created_at": (now - timedelta(days=8)).isoformat(),
        }
        ledger = [
            {
                "kind": "LOAN_DISBURSEMENT_SIMULATED",
                "entry_ts": (now - timedelta(days=7)).isoformat(),
            }
        ]
        with (
            patch(
                "app.credit.service.service.get_loan",
                new=AsyncMock(return_value=loan),
            ),
            patch(
                "app.credit.service.service.get_loan_ledger",
                new=AsyncMock(return_value=ledger),
            ),
            patch(
                "app.credit.service.service.get_merchant",
                new=AsyncMock(return_value={"upi_vpa": "shop@paytm"}),
            ),
            patch(
                "app.credit.service.service.get_transactions",
                new=AsyncMock(
                    return_value=[{"amount": "20.00", "txn_status": "SUCCESS"}]
                ),
            ),
            patch(
                "app.credit.service.service.create_ledger_entry",
                new=AsyncMock(),
            ) as create_entry,
            patch(
                "app.credit.service.service.update_loan",
                new=AsyncMock(),
            ),
        ):
            result = await simulate_credit_week("loan-1")
        self.assertTrue(result["alerts"])
        self.assertEqual(result["missed"], Decimal("13.33"))
        create_entry.assert_awaited_once()
        ledger_event = create_entry.await_args.args[0]
        self.assertTrue(ledger_event["kind"].startswith("WEEKLY_EMI_PARTIAL:1:"))
        self.assertIn("entry_ts", ledger_event)

    async def test_partial_cycle_alert_reads_missed_amount_from_ledger_kind(self):
        loan = {"id": "loan-1", "status": "ACTIVE"}
        ledger = [
            {"kind": "LOAN_DISBURSEMENT_SIMULATED", "amount": "100.00"},
            {
                "kind": "WEEKLY_EMI_PARTIAL:1:13.33",
                "amount": "20.00",
                "entry_ts": "2026-11-07T10:00:00+00:00",
            },
        ]
        with (
            patch(
                "app.credit.service.service.get_loan",
                new=AsyncMock(return_value=loan),
            ),
            patch(
                "app.credit.service.service.get_loan_ledger",
                new=AsyncMock(return_value=ledger),
            ),
        ):
            result = await get_credit_alerts("loan-1")
        self.assertEqual(len(result["alerts"]), 1)
        self.assertEqual(result["alerts"][0]["week"], 1)
        self.assertEqual(result["alerts"][0]["missed"], Decimal("13.33"))


if __name__ == "__main__":
    unittest.main()
