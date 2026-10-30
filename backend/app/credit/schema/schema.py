from decimal import Decimal
from typing import Any

from pydantic import BaseModel


class AcceptCreditRequest(BaseModel):
    mandate_accepted: bool


class CreditRecommendationResponse(BaseModel):
    invoice_id: str
    merchant_id: str
    is_eligible: bool
    ineligibility_reason: str | None = None
    principal: Decimal
    average_weekly_earnings: Decimal
    weekly_cap_limit: Decimal
    tenure_weeks: int
    weekly_emi: Decimal
    schedule: list[dict[str, Any]]
    history_basis: str


class CreditAcceptanceResponse(BaseModel):
    loan_id: str
    invoice_id: str
    status: str
    principal_amount: Decimal
    tenure_weeks: int
    weekly_emi_schedule: list[dict[str, Any]]
    autopay_mandate_active: bool


class CreditScheduleResponse(BaseModel):
    loan_id: str
    status: str
    principal_amount: Decimal
    remaining_balance: Decimal
    tenure_weeks: int
    schedule: list[dict[str, Any]]
    ledger_entries: list[dict[str, Any]]


class WeeklySimulationResponse(BaseModel):
    loan_id: str
    week: int
    due: Decimal
    qr_available: Decimal
    paid: Decimal
    missed: Decimal
    remaining_balance: Decimal
    status: str
    alerts: list[dict[str, Any]]


class CreditAlertsResponse(BaseModel):
    loan_id: str
    alerts: list[dict[str, Any]]
