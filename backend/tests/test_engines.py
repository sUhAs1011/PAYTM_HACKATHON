import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.engine.credit_engine import (
    average_weekly_qr_earnings,
    successful_qr_amount,
    simulate_weekly_payment,
    weekly_repayment_plan,
)
from app.engine.math_engine import calculate_line, validate_invoice
from app.engine.waterfall_engine import analyze_price


class MathEngineTests(unittest.TestCase):
    def setUp(self):
        self.item = {
            "id": "line-1",
            "raw_item_name": "Oil 1L",
            "billed_qty": 2,
            "free_qty": 1,
            "billed_rate": "100.00",
            "tax_percent": "5",
            "true_landed_cost": "70.00",
            "ocr_confidence": "0.95",
        }

    def test_calculates_gst_and_landed_cost(self):
        result = calculate_line(self.item)
        self.assertEqual(result.net_amount, Decimal("200.00"))
        self.assertEqual(result.gst_amount, Decimal("10.00"))
        self.assertEqual(result.expected_line_total, Decimal("210.00"))
        self.assertEqual(result.true_landed_cost, Decimal("70.00"))

    def test_invoice_checksum_and_low_confidence_alert(self):
        item = {**self.item, "ocr_confidence": "0.79"}
        result = validate_invoice(
            {"id": "invoice-1", "billed_total": "210.00"}, [item]
        )
        self.assertTrue(result["is_valid"])
        self.assertEqual(
            [alert["code"] for alert in result["alerts"]],
            ["LOW_OCR_CONFIDENCE"],
        )

    def test_invoice_mismatch_is_invalid_and_alerted(self):
        result = validate_invoice(
            {"id": "invoice-1", "billed_total": "212.00"}, [self.item]
        )
        self.assertFalse(result["is_valid"])
        self.assertEqual(result["alerts"][0]["code"], "TOTAL_MISMATCH")
        self.assertEqual(result["delta"], Decimal("-2.00"))

    def test_empty_invoice_lines_raise_alert(self):
        result = validate_invoice({"id": "invoice-1", "billed_total": "0"}, [])
        self.assertFalse(result["is_valid"])
        self.assertEqual(result["alerts"][0]["code"], "NO_LINE_ITEMS")


class WaterfallEngineTests(unittest.TestCase):
    def test_supplier_average_and_anonymized_peer_average(self):
        peers = [
            ("store-1", "120.00"),
            ("store-1", "130.00"),
            ("store-2", "120.00"),
            ("store-3", "120.00"),
            ("store-4", "120.00"),
            ("store-5", "120.00"),
        ]
        result = analyze_price("130", ["100", "111", "120"], peers)
        self.assertEqual(
            result["supplier_history"]["median_rate"], Decimal("111.00")
        )
        self.assertEqual(
            result["pincode_benchmark"]["average_rate"], Decimal("121.00")
        )
        self.assertEqual(
            result["pincode_benchmark"]["median_rate"], Decimal("120.00")
        )
        self.assertEqual(result["pincode_benchmark"]["peer_store_count"], 5)
        self.assertTrue(result["pincode_benchmark"]["gate_active"])
        self.assertEqual(result["rate_status"], "FLAGGED_HIGH")
        self.assertNotIn("store-1", str(result))

    def test_pincode_benchmark_is_skipped_below_five_stores(self):
        result = analyze_price(
            "130",
            ["100", "110", "120"],
            [(f"store-{index}", "120") for index in range(4)],
        )
        self.assertFalse(result["pincode_benchmark"]["gate_active"])
        self.assertIsNone(result["pincode_benchmark"]["average_rate"])
        self.assertIsNone(result["pincode_benchmark"]["median_rate"])


class CreditEngineTests(unittest.TestCase):
    def test_weekly_plan_respects_cap_and_reconciles_principal(self):
        plan = weekly_repayment_plan("100.00", "100.00")
        amounts = [row["emi"] for row in plan["schedule"]]
        self.assertEqual(plan["weekly_cap_limit"], Decimal("35.00"))
        self.assertEqual(plan["tenure_weeks"], 3)
        self.assertEqual(sum(amounts, Decimal("0")), Decimal("100.00"))
        self.assertTrue(all(value <= plan["weekly_cap_limit"] for value in amounts))
        self.assertEqual(amounts[-1], Decimal("33.34"))

    def test_no_qr_history_is_not_eligible(self):
        plan = weekly_repayment_plan("100", "0")
        self.assertFalse(plan["is_eligible"])
        self.assertEqual(plan["ineligibility_reason"], "INSUFFICIENT_QR_HISTORY")

    def test_successful_receipts_and_thirty_day_average(self):
        now = datetime(2026, 10, 30, tzinfo=timezone.utc)
        transactions = [
            {
                "amount": "300",
                "txn_status": "SUCCESS",
                "created_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "amount": "90",
                "txn_status": "FAILED",
                "created_at": (now - timedelta(days=1)).isoformat(),
            },
            {
                "amount": "100",
                "txn_status": "SUCCESS",
                "created_at": (now - timedelta(days=31)).isoformat(),
            },
        ]
        self.assertEqual(successful_qr_amount(transactions[:2]), Decimal("300.00"))
        self.assertEqual(
            average_weekly_qr_earnings(transactions, now), Decimal("70.00")
        )

    def test_insufficient_weekly_qr_amount_returns_missed_balance(self):
        result = simulate_weekly_payment("30", "20", "100")
        self.assertEqual(result["paid"], Decimal("20.00"))
        self.assertEqual(result["missed"], Decimal("10.00"))
        self.assertEqual(result["remaining_balance"], Decimal("80.00"))
        self.assertTrue(result["is_missed"])


if __name__ == "__main__":
    unittest.main()
