import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.credit.service.sweep_preview import get_sweep_preview
from app.engine.math_engine import ZERO


def _recent_week_transactions():
    return [
        {
            "amount": "10.00",
            "txn_status": "SUCCESS",
            "created_at": (datetime.now(timezone.utc) - timedelta(days=offset)).isoformat(),
        }
        for offset in range(1, 8)
    ]


class SweepPreviewTests(unittest.IsolatedAsyncioTestCase):
    async def _preview(self, mandate_active=True):
        loan = {
            "id": "loan-1",
            "merchant_id": "merchant-1",
            "remaining_balance": "350.00",
            "daily_deduction_rate": "50.00",
            "daily_cap_limit": "50.00",
            "tenure_days": 7,
            "autopay_mandate_active": mandate_active,
        }
        transactions = _recent_week_transactions()
        ledger = [{"amount": "-45.00", "entry_ts": datetime.now(timezone.utc).isoformat()}]
        with (
            patch("app.credit.service.sweep_preview.get_active_loan", new=AsyncMock(return_value=loan)),
            patch(
                "app.credit.service.sweep_preview.get_merchant",
                new=AsyncMock(return_value={"id": "merchant-1", "upi_vpa": "shop@paytm", "avg_daily_qr_volume": "100.00"}),
            ),
            patch("app.credit.service.sweep_preview.get_transactions", new=AsyncMock(return_value=transactions)) as tx_query,
            patch("app.credit.service.sweep_preview.get_merchant_ledger", new=AsyncMock(return_value=ledger)),
        ):
            preview = await get_sweep_preview("invoice-1")

        tx_query.assert_awaited_once()
        self.assertIsNone(tx_query.await_args.kwargs["start"])
        self.assertEqual(preview.starting_paytm_balance, Decimal("25.00"))
        self.assertTrue(preview.simulation_only)
        return preview

    async def test_qr_balance_covers_due_then_bank_simulates_shortfall(self):
        preview = await self._preview(mandate_active=True)
        self.assertEqual(len(preview.days), 6)
        first, second = preview.days[0], preview.days[1]
        self.assertEqual(first.forecast_qr_inflow, Decimal("10.00"))
        self.assertEqual(first.qr_deduction, Decimal("35.00"))
        self.assertEqual(first.bank_mandate_deduction, Decimal("15.00"))
        self.assertEqual(first.missed, ZERO)
        self.assertTrue(first.mandate_triggered)
        self.assertEqual(second.qr_deduction, Decimal("10.00"))
        self.assertEqual(second.bank_mandate_deduction, Decimal("40.00"))
        self.assertEqual(first.projected_loan_balance, Decimal("300.00"))

    async def test_inactive_mandate_shows_missed_amount_without_bank_debit(self):
        preview = await self._preview(mandate_active=False)
        first = preview.days[0]
        self.assertEqual(first.qr_deduction, Decimal("35.00"))
        self.assertEqual(first.bank_mandate_deduction, ZERO)
        self.assertEqual(first.missed, Decimal("15.00"))
        self.assertFalse(first.mandate_triggered)


if __name__ == "__main__":
    unittest.main()
