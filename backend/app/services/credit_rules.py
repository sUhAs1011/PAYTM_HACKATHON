"""CreditRules — the Module 2 ⇄ Module 4 seam (resolve path).

Module 4 owns the deterministic credit/underwriting engine (Decimal math,
35%-cap sourcing over the 30-day QR history, full schedule). Until it is
wired, this provisional implementation applies the documented formulas
directly — the SAME formulas the synthetic seed was generated with, so
rows written by this slice stay consistent with the seeded invariants:

  - daily_cap_limit = 0.35 × merchant.avg_daily_qr_volume
    (source = the stored merchant column, mirroring the seeded
    split_credit_loans.daily_cap_limit invariant. Deliberately NOT
    recomputed from `transactions` — that comparison is Module 4's live
    engine work; the two sources agree by data-generation rule.)
  - principal = invoice.approved_total
  - daily_deduction = (principal / tenure_days).quantize(0.01, HALF_UP)
  - remaining_balance = principal − daily_deduction
    (Day-1 sweep already booked — the demo semantics per CIS §5 fixture
    `loan_schedule.day_1_deducted = true`.)

Golden-fixture cap (3500/24500 on a hypothetical seed merchant) vs. seed
merchant caps differ — KNOWN SPEC TENSION (AGENTS.md), untouched here.
Module 4's engine replaces this class via set_credit_rules; gateway code
does not change.
"""

import logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Protocol

from app.core.money import q2

logger = logging.getLogger("parchapay.api")

DAILY_CAP_RATIO = Decimal("0.35")


@dataclass(frozen=True)
class CreditPlan:
    daily_cap: Decimal
    principal: Decimal
    daily_deduction: Decimal
    remaining_balance: Decimal


class CreditRules(Protocol):
    def plan(self, merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan:  # pragma: no cover
        ...


_rules: Optional[CreditRules] = None


def set_credit_rules(implementation: CreditRules) -> None:
    """Integration point for Module 4: register the real engine."""
    global _rules
    _rules = implementation
    logger.info("CreditRules seam replaced: %s", type(implementation).__name__)


def get_credit_rules() -> CreditRules:
    return _rules if _rules is not None else ProvisionalCreditRules()


class ProvisionalCreditRules:
    def plan(self, merchant: dict, principal: Decimal, tenure_days: int) -> CreditPlan:
        avg_daily = Decimal(str(merchant["avg_daily_qr_volume"]))
        cap = q2(DAILY_CAP_RATIO * avg_daily)
        daily = q2(principal / Decimal(tenure_days))
        return CreditPlan(daily_cap=cap, principal=principal, daily_deduction=daily, remaining_balance=q2(principal - daily))
