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


class SweepDayPreview(BaseModel):
    day: int
    forecast_qr_inflow: float
    due: float
    paytm_balance_before: float
    qr_deduction: float
    bank_mandate_deduction: float
    missed: float
    paytm_balance_after: float
    projected_loan_balance: float
    mandate_triggered: bool


class SweepPreviewResponse(BaseModel):
    invoice_id: str
    loan_id: str
    simulation_only: bool = True
    forecast_source: str
    starting_paytm_balance: float
    daily_deduction: float
    autopay_mandate_active: bool
    days: list[SweepDayPreview]
