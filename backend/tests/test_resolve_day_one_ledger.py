import unittest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from app.api.resolve_router import _write_day_one_ledger
from app.api.resolve_router import resolve_parcha
from app.contracts import ResolveRequest
from app.services.credit_rules import CreditPlan


class ResolveDayOneLedgerTests(unittest.IsolatedAsyncioTestCase):
    async def test_resolve_persists_day_one_ledger_and_keeps_response_contract(self):
        plan = CreditPlan(
            daily_cap=Decimal("100.00"),
            max_credit_limit=Decimal("700.00"),
            is_eligible=True,
            principal=Decimal("100.00"),
            daily_deduction=Decimal("30.00"),
            remaining_balance=Decimal("70.00"),
            average_daily_qr_volume=Decimal("285.71"),
        )
        rules = type("Rules", (), {"plan": AsyncMock(return_value=plan)})()
        with (
            patch("app.api.resolve_router.get_client", new=AsyncMock(return_value=object())),
            patch(
                "app.api.resolve_router.repo.get_invoice_bundle",
                new=AsyncMock(return_value={
                    "id": "invoice-1",
                    "merchant_id": "merchant-1",
                    "invoice_number": "INV-1",
                    "approved_total": "100.00",
                    "invoice_date": None,
                    "suppliers": {"name": "Supplier", "gstin": "GSTIN", "phone": "123"},
                }),
            ),
            patch("app.api.resolve_router.repo.get_merchant", new=AsyncMock(return_value={"id": "merchant-1", "upi_vpa": "shop@paytm"})),
            patch("app.api.resolve_router.repo.get_loan_for_invoice", new=AsyncMock(return_value=None)),
            patch("app.api.resolve_router.get_credit_rules", return_value=rules),
            patch("app.api.resolve_router.repo.insert_loan", new=AsyncMock(return_value={"id": "loan-1"})) as insert_loan,
            patch("app.api.resolve_router.create_ledger_entry", new=AsyncMock()) as create_ledger,
            patch("app.api.resolve_router.repo.get_ims_record_for_invoice", new=AsyncMock(return_value={"id": "ims-1"})),
            patch("app.api.resolve_router.repo.update_ims_status", new=AsyncMock()),
            patch("app.api.resolve_router.repo.update_invoice_status", new=AsyncMock()),
        ):
            response = await resolve_parcha(
                "invoice-1", ResolveRequest(action="APPROVE_SPLIT", tenure_days=7)
            )

        self.assertEqual(response.loan_schedule.principal, 100.0)
        self.assertEqual(response.loan_schedule.daily_deduction, 30.0)
        self.assertEqual(response.loan_schedule.remaining_balance, 70.0)
        self.assertTrue(response.loan_schedule.day_1_deducted)
        self.assertNotIn("loan_id", response.model_dump())
        self.assertEqual(insert_loan.await_args.args[1]["remaining_balance"], "70.00")
        entry = create_ledger.await_args.args[0]
        self.assertEqual(entry["loan_id"], "loan-1")
        self.assertEqual(entry["amount"], "-30.00")

    async def test_writes_signed_loan_deduction_with_loan_link(self):
        with patch(
            "app.api.resolve_router.create_ledger_entry", new=AsyncMock()
        ) as create_entry:
            await _write_day_one_ledger(
                object(), {"id": "loan-1"}, "merchant-1", Decimal("30.00")
            )
        payload = create_entry.await_args.args[0]
        self.assertEqual(payload["kind"], "LOAN_DEDUCT")
        self.assertEqual(payload["amount"], "-30.00")
        self.assertEqual(payload["merchant_id"], "merchant-1")
        self.assertEqual(payload["loan_id"], "loan-1")

    async def test_ambiguous_insert_recognizes_existing_same_day_debit(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        with (
            patch(
                "app.api.resolve_router.create_ledger_entry",
                new=AsyncMock(side_effect=RuntimeError("connection dropped after insert")),
            ),
            patch(
                "app.api.resolve_router.get_loan_ledger",
                new=AsyncMock(return_value=[{"entry_ts": timestamp, "kind": "LOAN_DEDUCT", "amount": "-30.00"}]),
            ),
            patch("app.api.resolve_router.repo.delete_loan", new=AsyncMock()) as delete_loan,
        ):
            await _write_day_one_ledger(
                object(), {"id": "loan-1"}, "merchant-1", Decimal("30.00")
            )
        delete_loan.assert_not_awaited()

    async def test_removes_new_loan_when_ledger_write_failed_without_commit(self):
        with (
            patch(
                "app.api.resolve_router.create_ledger_entry",
                new=AsyncMock(side_effect=RuntimeError("write failed")),
            ),
            patch("app.api.resolve_router.get_loan_ledger", new=AsyncMock(return_value=[])),
            patch("app.api.resolve_router.repo.delete_loan", new=AsyncMock()) as delete_loan,
        ):
            with self.assertRaisesRegex(RuntimeError, "newly created loan was removed"):
                await _write_day_one_ledger(
                    object(), {"id": "loan-1"}, "merchant-1", Decimal("30.00")
                )
        delete_loan.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
