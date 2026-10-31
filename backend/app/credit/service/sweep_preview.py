"""Read-only projection for the CIS daily QR split drawer.

No previewed QR or bank amounts are written to `transactions`,
`merchant_account_ledger`, or `split_credit_loans`.
"""

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo

from app.credit.db.query import (
    get_active_loan,
    get_merchant,
    get_merchant_ledger,
    get_transactions,
)
from app.credit.schema.schema import SweepDayPreview, SweepPreviewResponse
from app.engine.credit_engine import successful_qr_amount
from app.engine.math_engine import ZERO, as_decimal, money

logger = logging.getLogger(__name__)
IST = ZoneInfo("Asia/Kolkata")
FORECAST_DAYS = 7


async def get_sweep_preview(invoice_id: str) -> SweepPreviewResponse:
    loan = await get_active_loan(invoice_id)
    if loan is None:
        raise LookupError("Active loan not found for invoice")
    merchant = await get_merchant(str(loan["merchant_id"]))
    if merchant is None:
        raise LookupError("Merchant not found")

    now = datetime.now(timezone.utc)
    transactions = await get_transactions(
        str(merchant["id"]), str(merchant["upi_vpa"]), start=None, end=now
    )
    ledger = await get_merchant_ledger(str(merchant["id"]))

    # Transactions are the single source for successful incoming QR funds;
    # never mirror these credits into merchant_account_ledger.
    qr_balance = successful_qr_amount(transactions)
    ledger_balance = ZERO
    for row in ledger:
        entry_ts = row.get("entry_ts")
        if entry_ts:
            parsed = datetime.fromisoformat(str(entry_ts).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            if parsed > now:
                continue
        ledger_balance += money(as_decimal(row.get("amount", 0), "ledger amount"))
    ledger_balance = money(ledger_balance)
    starting_paytm_balance = money(qr_balance + ledger_balance)

    forecast, forecast_source = _forecast_profile(transactions, merchant, now)
    remaining = money(as_decimal(loan["remaining_balance"], "remaining_balance"))
    daily_due = money(as_decimal(loan["daily_deduction_rate"], "daily_deduction_rate"))
    daily_cap = money(as_decimal(loan["daily_cap_limit"], "daily_cap_limit"))
    tenure_days = max(1, int(loan.get("tenure_days") or 7))
    autopay_active = bool(loan.get("autopay_mandate_active"))
    paytm_balance = starting_paytm_balance
    days: list[SweepDayPreview] = []

    for day in range(2, min(tenure_days, 7) + 1):
        if remaining <= ZERO:
            break
        inflow = forecast[(day - 2) % len(forecast)] if forecast else ZERO
        balance_before = money(paytm_balance + inflow)
        due = min(daily_due, daily_cap, remaining)
        qr_deduction = min(due, max(ZERO, balance_before))
        shortfall = money(max(ZERO, due - qr_deduction))
        bank_deduction = shortfall if autopay_active else ZERO
        missed = money(max(ZERO, shortfall - bank_deduction))
        paytm_balance = money(balance_before - qr_deduction)
        remaining = money(max(ZERO, remaining - qr_deduction - bank_deduction))
        days.append(
            SweepDayPreview(
                day=day,
                forecast_qr_inflow=float(inflow),
                due=float(due),
                paytm_balance_before=float(balance_before),
                qr_deduction=float(qr_deduction),
                bank_mandate_deduction=float(bank_deduction),
                missed=float(missed),
                paytm_balance_after=float(paytm_balance),
                projected_loan_balance=float(remaining),
                mandate_triggered=bank_deduction > ZERO,
            )
        )

    logger.info(
        "credit_sweep_preview_ready invoice_id=%s loan_id=%s forecast_source=%s day_count=%s",
        invoice_id,
        loan["id"],
        forecast_source,
        len(days),
    )
    return SweepPreviewResponse(
        invoice_id=invoice_id,
        loan_id=str(loan["id"]),
        forecast_source=forecast_source,
        starting_paytm_balance=float(starting_paytm_balance),
        daily_deduction=float(daily_due),
        autopay_mandate_active=autopay_active,
        days=days,
    )


def _forecast_profile(
    transactions: list[dict], merchant: dict, now: datetime
) -> tuple[list[Decimal], str]:
    """Use the last seven complete IST days as a projected daily QR pattern."""
    now_ist = now.astimezone(IST)
    last_complete_day = now_ist.date() - timedelta(days=1)
    dates = [last_complete_day - timedelta(days=index) for index in reversed(range(FORECAST_DAYS))]
    daily: dict[date, list[dict]] = defaultdict(list)
    for transaction in transactions:
        if str(transaction.get("txn_status") or "").upper() not in {
            "SUCCESS", "SUCCESSFUL", "COMPLETED", "SETTLED"
        }:
            continue
        created_at = transaction.get("created_at")
        if not created_at:
            continue
        timestamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        local_date = timestamp.astimezone(IST).date()
        if local_date in dates:
            daily[local_date].append(transaction)

    profile = [successful_qr_amount(daily[day]) for day in dates]
    if any(amount > ZERO for amount in profile):
        return profile, "RECENT_7D_QR_REPLAY"

    fallback = money(as_decimal(merchant.get("avg_daily_qr_volume", 0), "avg_daily_qr_volume"))
    return [fallback] * FORECAST_DAYS, "MERCHANT_AVG_DAILY_QR_FALLBACK"
