"""CIS 7-day daily-credit rules backed by Module 4 QR history.

The Soumya weekly-credit write flow is intentionally not mounted; this
adapter serves the CIS scan pre-approval and APPROVE_SPLIT resolve flow only.
All financial quantities are Decimal and quantized to paise.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional, Protocol

from app.core.money import q2

logger = logging.getLogger("parchapay.api")
DAILY_CAP_RATIO = Decimal("0.35")
HISTORY_DAYS = 30


@dataclass(frozen=True)
class CreditPlan:
    daily_cap: Decimal
    max_credit_limit: Decimal
    is_eligible: bool
    principal: Decimal
    daily_deduction: Decimal
    remaining_balance: Decimal
    average_daily_qr_volume: Decimal


class CreditRules(Protocol):
    async def plan(self, merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan:
        ...


_rules: Optional[CreditRules] = None


def set_credit_rules(implementation: CreditRules) -> None:
    """Integration seam; Module 4's QR-backed implementation is registered at startup."""
    global _rules
    _rules = implementation
    logger.info("CreditRules seam set: %s", type(implementation).__name__)


def get_credit_rules() -> CreditRules:
    if _rules is None:
        raise RuntimeError("CreditRules not initialized; app lifespan must register LiveCreditRules")
    return _rules


class LiveCreditRules:
    """Compute the CIS daily cap from successful incoming QR transactions over 30 days."""

    async def plan(self, merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan:
        from app.credit.db.query import get_transactions
        from app.engine.credit_engine import successful_qr_amount

        now = datetime.now(timezone.utc)
        transactions = await get_transactions(
            str(merchant["id"]),
            str(merchant["upi_vpa"]),
            now - timedelta(days=HISTORY_DAYS),
            now,
        )
        total_successful = successful_qr_amount(transactions)
        if total_successful > 0:
            average_daily = q2(total_successful / Decimal(HISTORY_DAYS))
            source = "transactions"
        else:
            average_daily = q2(Decimal(str(merchant["avg_daily_qr_volume"])))
            source = "avg_daily_qr_volume fallback"
        plan = _make_plan(average_daily, principal, tenure_days)
        logger.info(
            "cis_credit_plan merchant_id=%s source=%s eligible=%s",
            merchant.get("id"), source, plan.is_eligible,
        )
        return plan


def _make_plan(average_daily: Decimal, principal: Decimal, tenure_days: int) -> CreditPlan:
    if tenure_days <= 0:
        raise ValueError("tenure_days must be positive")
    principal = q2(principal)
    cap = q2(average_daily * DAILY_CAP_RATIO)
    max_limit = q2(cap * Decimal(tenure_days))
    eligible = principal > 0 and principal <= max_limit
    installment = q2(principal / Decimal(tenure_days))
    # Never suggest a daily cut above the cap. The resolve endpoint rejects
    # ineligible principals before writing any rows.
    daily = min(installment, cap)
    return CreditPlan(
        daily_cap=cap,
        max_credit_limit=max_limit,
        is_eligible=eligible,
        principal=principal,
        daily_deduction=q2(daily),
        remaining_balance=q2(max(Decimal("0"), principal - daily)),
        average_daily_qr_volume=q2(average_daily),
    )
