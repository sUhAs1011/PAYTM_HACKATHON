from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING
from typing import Any, Iterable

from .math_engine import ZERO, as_decimal, money

DAILY_VELOCITY_RATE = Decimal("0.35")
DAYS_IN_WEEK = 7
HISTORY_DAYS = 30
SUCCESS_STATUSES = {"SUCCESS", "SUCCESSFUL", "COMPLETED", "SETTLED"}


def successful_qr_amount(transactions: Iterable[dict[str, Any]]) -> Decimal:
    total = ZERO
    for transaction in transactions:
        status = str(transaction.get("txn_status") or "").strip().upper()
        if status in SUCCESS_STATUSES:
            total += as_decimal(transaction.get("amount"), "transaction amount")
    return money(total)


def average_weekly_qr_earnings(
    transactions: Iterable[dict[str, Any]], now: datetime | None = None
) -> Decimal:
    end = now or datetime.now(timezone.utc)
    start = end - timedelta(days=HISTORY_DAYS)
    valid_transactions = []
    for transaction in transactions:
        status = str(transaction.get("txn_status") or "").strip().upper()
        created_at = transaction.get("created_at")
        if status not in SUCCESS_STATUSES or not created_at:
            continue
        timestamp = datetime.fromisoformat(str(created_at).replace("Z", "+00:00"))
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=timezone.utc)
        if start <= timestamp <= end:
            valid_transactions.append(transaction)
    total = successful_qr_amount(valid_transactions)
    return money(total * Decimal(DAYS_IN_WEEK) / Decimal(HISTORY_DAYS))


def weekly_repayment_plan(
    principal: Any,
    average_weekly_earnings: Any,
    cap_ratio: Decimal = DAILY_VELOCITY_RATE,
) -> dict[str, Any]:
    principal_amount = money(as_decimal(principal, "principal"))
    weekly_earnings = money(
        as_decimal(average_weekly_earnings, "average_weekly_earnings")
    )
    weekly_cap = money(weekly_earnings * cap_ratio)
    if principal_amount <= ZERO:
        raise ValueError("principal must be greater than zero")
    if weekly_cap <= ZERO:
        return {
            "is_eligible": False,
            "ineligibility_reason": "INSUFFICIENT_QR_HISTORY",
            "principal": principal_amount,
            "average_weekly_earnings": weekly_earnings,
            "weekly_cap_limit": weekly_cap,
            "tenure_weeks": 0,
            "weekly_emi": ZERO,
            "schedule": [],
        }

    weeks = int(
        (principal_amount / weekly_cap).to_integral_value(rounding=ROUND_CEILING)
    )
    while True:
        regular_emi = money(principal_amount / Decimal(weeks))
        schedule = [regular_emi] * (weeks - 1)
        final_emi = money(principal_amount - sum(schedule, ZERO))
        schedule.append(final_emi)
        if all(emi <= weekly_cap for emi in schedule):
            break
        weeks += 1

    return {
        "is_eligible": True,
        "ineligibility_reason": None,
        "principal": principal_amount,
        "average_weekly_earnings": weekly_earnings,
        "weekly_cap_limit": weekly_cap,
        "tenure_weeks": weeks,
        "weekly_emi": regular_emi,
        "schedule": [
            {"week": index + 1, "emi": amount}
            for index, amount in enumerate(schedule)
        ],
    }


def simulate_weekly_payment(
    due: Any, available_qr: Any, remaining_balance: Any
) -> dict[str, Any]:
    due_amount = money(as_decimal(due, "due"))
    available_amount = max(ZERO, money(as_decimal(available_qr, "available_qr")))
    balance = money(as_decimal(remaining_balance, "remaining_balance"))
    paid = min(due_amount, available_amount, balance)
    missed = money(max(ZERO, due_amount - paid))
    return {
        "due": due_amount,
        "paid": paid,
        "missed": missed,
        "remaining_balance": money(max(ZERO, balance - paid)),
        "is_missed": missed > ZERO,
    }