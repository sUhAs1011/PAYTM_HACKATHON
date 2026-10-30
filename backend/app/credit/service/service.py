import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from app.credit.db.query import (
    create_ledger_entry,
    create_loan,
    get_active_loan,
    get_invoice,
    get_loan,
    get_loan_ledger,
    get_merchant,
    get_transactions,
    update_loan,
)
from app.engine.credit_engine import (
    average_weekly_qr_earnings,
    successful_qr_amount,
    simulate_weekly_payment,
    weekly_repayment_plan,
)
from app.engine.math_engine import ZERO, as_decimal, money

logger = logging.getLogger(__name__)


def _history_basis(transactions: list[dict[str, Any]]) -> str:
    return "TRANSACTIONS_30D" if transactions else "NO_SUCCESSFUL_QR_HISTORY"


async def get_credit_recommendation(invoice_id: str) -> dict[str, Any]:
    logger.info("credit_recommendation_started invoice_id=%s", invoice_id)
    invoice = await get_invoice(invoice_id)
    if invoice is None:
        logger.warning("credit_recommendation_invoice_missing invoice_id=%s", invoice_id)
        raise LookupError("Invoice not found")
    merchant_id = str(invoice["merchant_id"])
    merchant = await get_merchant(merchant_id)
    if merchant is None:
        logger.warning("credit_recommendation_merchant_missing invoice_id=%s", invoice_id)
        raise LookupError("Merchant not found")
    now = datetime.now(timezone.utc)
    transactions = await get_transactions(
        merchant_id,
        str(merchant["upi_vpa"]),
        now - timedelta(days=30),
        now,
    )
    average_weekly = average_weekly_qr_earnings(transactions, now)
    logger.debug(
        "credit_history_loaded invoice_id=%s transaction_count=%s",
        invoice_id,
        len(transactions),
    )
    principal = as_decimal(invoice["billed_total"], "billed_total")
    plan = weekly_repayment_plan(principal, average_weekly)

    if average_weekly <= ZERO and merchant and merchant.get("avg_daily_qr_volume") is not None:
        fallback_weekly = money(
            as_decimal(merchant["avg_daily_qr_volume"], "avg_daily_qr_volume")
            * Decimal("7")
        )
        plan = weekly_repayment_plan(principal, fallback_weekly)
        history_basis = "MERCHANT_AVG_DAILY_QR_VOLUME_FALLBACK"
    else:
        history_basis = _history_basis(transactions)

    result = {
        "invoice_id": str(invoice["id"]),
        "merchant_id": merchant_id,
        **plan,
        "history_basis": history_basis,
    }
    logger.info(
        "credit_recommendation_completed invoice_id=%s eligible=%s tenure_weeks=%s history_basis=%s",
        invoice_id,
        result["is_eligible"],
        result["tenure_weeks"],
        history_basis,
    )
    return result


async def accept_credit(invoice_id: str) -> dict[str, Any]:
    logger.info("credit_acceptance_started invoice_id=%s", invoice_id)
    recommendation = await get_credit_recommendation(invoice_id)
    if not recommendation["is_eligible"]:
        logger.warning(
            "credit_acceptance_rejected invoice_id=%s reason=ineligible",
            invoice_id,
        )
        raise PermissionError(recommendation["ineligibility_reason"])
    if await get_active_loan(invoice_id):
        logger.warning(
            "credit_acceptance_rejected invoice_id=%s reason=active_loan_exists",
            invoice_id,
        )
        raise FileExistsError("An active loan already exists for this invoice")

    schedule = recommendation["schedule"]
    principal = recommendation["principal"]
    tenure_weeks = recommendation["tenure_weeks"]
    weekly_emi = recommendation["weekly_emi"]
    daily_cap = money(recommendation["weekly_cap_limit"] / Decimal("7"))
    daily_projection = money(weekly_emi / Decimal("7"))
    loan = await create_loan(
        {
            "invoice_id": invoice_id,
            "merchant_id": recommendation["merchant_id"],
            "principal_amount": str(principal),
            "daily_deduction_rate": str(daily_projection),
            "tenure_days": tenure_weeks * 7,
            "daily_cap_limit": str(daily_cap),
            "autopay_mandate_active": True,
            "remaining_balance": str(principal),
            "status": "ACTIVE",
        }
    )
    await create_ledger_entry(
        {
            "merchant_id": recommendation["merchant_id"],
            "loan_id": loan["id"],
            "kind": "LOAN_DISBURSEMENT_SIMULATED",
            "amount": str(principal),
        }
    )
    logger.info(
        "credit_acceptance_completed invoice_id=%s loan_id=%s tenure_weeks=%s",
        invoice_id,
        loan["id"],
        tenure_weeks,
    )
    return {
        "loan_id": str(loan["id"]),
        "invoice_id": invoice_id,
        "status": loan["status"],
        "principal_amount": principal,
        "tenure_weeks": tenure_weeks,
        "weekly_emi_schedule": schedule,
        "autopay_mandate_active": loan["autopay_mandate_active"],
    }


def _schedule_from_loan(loan: dict[str, Any]) -> list[dict[str, Any]]:
    principal = money(as_decimal(loan["principal_amount"], "principal_amount"))
    weeks = max(1, (int(loan["tenure_days"]) + 6) // 7)
    base = money(principal / Decimal(weeks))
    schedule = [base] * (weeks - 1)
    schedule.append(money(principal - sum(schedule, ZERO)))
    return [{"week": index + 1, "emi": amount} for index, amount in enumerate(schedule)]


def _ensure_module4_loan(loan: dict[str, Any], ledger: list[dict[str, Any]]) -> None:
    if not any(
        entry.get("kind") == "LOAN_DISBURSEMENT_SIMULATED" for entry in ledger
    ):
        raise ValueError("Loan was not created by the Module 4 weekly-credit flow")


async def get_credit_schedule(loan_id: str) -> dict[str, Any]:
    logger.info("credit_schedule_requested loan_id=%s", loan_id)
    loan = await get_loan(loan_id)
    if loan is None:
        logger.warning("credit_loan_missing loan_id=%s", loan_id)
        raise LookupError("Loan not found")
    ledger = await get_loan_ledger(loan_id)
    _ensure_module4_loan(loan, ledger)
    return {
        "loan_id": str(loan["id"]),
        "status": loan["status"],
        "principal_amount": money(as_decimal(loan["principal_amount"], "principal_amount")),
        "remaining_balance": money(as_decimal(loan["remaining_balance"], "remaining_balance")),
        "tenure_weeks": max(1, (int(loan["tenure_days"]) + 6) // 7),
        "schedule": _schedule_from_loan(loan),
        "ledger_entries": ledger,
    }


async def simulate_credit_week(loan_id: str) -> dict[str, Any]:
    logger.info("credit_week_simulation_started loan_id=%s", loan_id)
    loan = await get_loan(loan_id)
    if loan is None:
        logger.warning("credit_loan_missing loan_id=%s", loan_id)
        raise LookupError("Loan not found")
    if loan["status"] != "ACTIVE":
        logger.warning(
            "credit_week_simulation_rejected loan_id=%s reason=loan_not_active",
            loan_id,
        )
        raise ValueError("Loan is not active")

    ledger = await get_loan_ledger(loan_id)
    _ensure_module4_loan(loan, ledger)
    cycle_kinds = (
        "WEEKLY_EMI_PAID:",
        "WEEKLY_EMI_MISSED:",
        "WEEKLY_EMI_PARTIAL:",
    )
    completed_weeks = {
        str(entry["kind"]).split(":")[1]
        for entry in ledger
        if str(entry.get("kind", "")).startswith(cycle_kinds)
    }
    week_number = len(completed_weeks) + 1
    schedule = _schedule_from_loan(loan)
    remaining = money(as_decimal(loan["remaining_balance"], "remaining_balance"))
    due = (
        schedule[week_number - 1]["emi"]
        if week_number <= len(schedule)
        else schedule[-1]["emi"]
    )
    due = min(due, remaining)

    loan_created = datetime.fromisoformat(
        str(loan["created_at"]).replace("Z", "+00:00")
    )
    if loan_created.tzinfo is None:
        loan_created = loan_created.replace(tzinfo=timezone.utc)
    period_end = loan_created - timedelta(days=(week_number - 1) * 7)
    period_start = period_end - timedelta(days=7)
    merchant = await get_merchant(str(loan["merchant_id"]))
    if merchant is None:
        raise LookupError("Merchant not found")
    transactions = await get_transactions(
        str(loan["merchant_id"]),
        str(merchant["upi_vpa"]),
        period_start,
        period_end,
    )
    qr_available = successful_qr_amount(transactions)
    payment = simulate_weekly_payment(
        due, qr_available, loan["remaining_balance"]
    )
    cycle = str(week_number)
    if payment["is_missed"] and payment["paid"] > ZERO:
        ledger_kind = f"WEEKLY_EMI_PARTIAL:{cycle}:{payment['missed']}"
        ledger_amount = payment["paid"]
    elif payment["is_missed"]:
        ledger_kind = f"WEEKLY_EMI_MISSED:{cycle}"
        ledger_amount = payment["missed"]
    else:
        ledger_kind = f"WEEKLY_EMI_PAID:{cycle}"
        ledger_amount = payment["paid"]

    ledger_entry_at = loan_created + timedelta(days=week_number * 7)
    await create_ledger_entry(
        {
            "merchant_id": loan["merchant_id"],
            "loan_id": loan_id,
            "kind": ledger_kind,
            "amount": str(ledger_amount),
            "entry_ts": ledger_entry_at.isoformat(),
        }
    )

    alerts = []
    if payment["is_missed"]:
        logger.warning(
            "credit_week_payment_missed loan_id=%s week=%s",
            loan_id,
            week_number,
        )
        alert = {
            "code": "WEEKLY_EMI_MISSED",
            "severity": "HIGH",
            "week": week_number,
            "due": payment["due"],
            "paid": payment["paid"],
            "missed": payment["missed"],
        }
        alerts.append(alert)

    status = "COMPLETED" if payment["remaining_balance"] == ZERO else "ACTIVE"
    await update_loan(
        loan_id,
        {
            "remaining_balance": str(payment["remaining_balance"]),
            "status": status,
        },
    )
    logger.info(
        "credit_week_simulation_completed loan_id=%s week=%s paid=%s missed=%s status=%s",
        loan_id,
        week_number,
        payment["paid"] > ZERO,
        payment["is_missed"],
        status,
    )
    return {
        "loan_id": loan_id,
        "week": week_number,
        "due": payment["due"],
        "qr_available": qr_available,
        "paid": payment["paid"],
        "missed": payment["missed"],
        "remaining_balance": payment["remaining_balance"],
        "status": status,
        "alerts": alerts,
    }


async def get_credit_alerts(loan_id: str) -> dict[str, Any]:
    logger.debug("credit_alerts_requested loan_id=%s", loan_id)
    loan = await get_loan(loan_id)
    if loan is None:
        logger.warning("credit_loan_missing loan_id=%s", loan_id)
        raise LookupError("Loan not found")
    ledger = await get_loan_ledger(loan_id)
    _ensure_module4_loan(loan, ledger)
    alerts = []
    for entry in ledger:
        kind = str(entry.get("kind", ""))
        if kind.startswith("WEEKLY_EMI_MISSED:"):
            alerts.append(
                {
                    "code": "WEEKLY_EMI_MISSED",
                    "severity": "HIGH",
                    "week": int(kind.split(":", 1)[1]),
                    "missed": money(as_decimal(entry["amount"], "ledger amount")),
                    "occurred_at": entry.get("entry_ts"),
                }
            )
        elif kind.startswith("WEEKLY_EMI_PARTIAL:"):
            _, week, missed = kind.split(":", 2)
            alerts.append(
                {
                    "code": "WEEKLY_EMI_MISSED",
                    "severity": "HIGH",
                    "week": int(week),
                    "missed": money(as_decimal(missed, "missed amount")),
                    "occurred_at": entry.get("entry_ts"),
                }
            )
    logger.info(
        "credit_alerts_ready loan_id=%s alert_count=%s",
        loan_id,
        len(alerts),
    )
    return {"loan_id": loan_id, "alerts": alerts}
