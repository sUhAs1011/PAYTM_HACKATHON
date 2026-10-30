import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.services.credit_rules import LiveCreditRules


class LiveCreditRulesTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_30_day_successful_qr_volume_and_enforces_daily_cap(self):
        merchant = {
            "id": "merchant-1",
            "upi_vpa": "shop@paytm",
            "avg_daily_qr_volume": "1000.00",
        }
        transactions = [
            {"amount": "3000.00", "txn_status": "SUCCESS"},
            {"amount": "9000.00", "txn_status": "FAILED"},
        ]
        with patch(
            "app.credit.db.query.get_transactions",
            new=AsyncMock(return_value=transactions),
        ):
            eligible = await LiveCreditRules().plan(merchant, Decimal("200.00"), 7)
            ineligible = await LiveCreditRules().plan(merchant, Decimal("300.00"), 7)

        self.assertEqual(eligible.average_daily_qr_volume, Decimal("100.00"))
        self.assertEqual(eligible.daily_cap, Decimal("35.00"))
        self.assertEqual(eligible.max_credit_limit, Decimal("245.00"))
        self.assertTrue(eligible.is_eligible)
        self.assertEqual(eligible.daily_deduction, Decimal("28.57"))
        self.assertFalse(ineligible.is_eligible)
        self.assertEqual(ineligible.daily_deduction, Decimal("35.00"))

    async def test_falls_back_to_seeded_average_when_no_successful_qr(self):
        merchant = {
            "id": "merchant-1",
            "upi_vpa": "shop@paytm",
            "avg_daily_qr_volume": "1000.00",
        }
        with patch(
            "app.credit.db.query.get_transactions",
            new=AsyncMock(return_value=[]),
        ):
            plan = await LiveCreditRules().plan(merchant, Decimal("2000.00"), 7)
        self.assertEqual(plan.average_daily_qr_volume, Decimal("1000.00"))
        self.assertEqual(plan.max_credit_limit, Decimal("2450.00"))
        self.assertTrue(plan.is_eligible)


if __name__ == "__main__":
    unittest.main()
