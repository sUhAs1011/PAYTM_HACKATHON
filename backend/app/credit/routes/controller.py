import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.credit.schema.schema import (
    AcceptCreditRequest,
    CreditAcceptanceResponse,
    CreditAlertsResponse,
    CreditRecommendationResponse,
    CreditScheduleResponse,
    WeeklySimulationResponse,
)
from app.credit.service.service import (
    accept_credit,
    get_credit_alerts,
    get_credit_recommendation,
    get_credit_schedule,
    simulate_credit_week,
)

router = APIRouter(prefix="/api/credit", tags=["Module 4 — credit reads"])
# The weekly-credit POST flows are intentionally split onto a separate router.
# The user chose to keep the existing merchant_account_ledger kind contract
# unchanged, so main.py mounts `router` only. Do not mount `write_router`
# without a fresh schema/contract decision.
write_router = APIRouter(prefix="/api/credit", tags=["Module 4 — weekly credit writes (disabled)"])
logger = logging.getLogger(__name__)


def _uuid(value: str, label: str) -> str:
    try:
        return str(UUID(value))
    except ValueError as exc:
        logger.warning("credit_request_rejected resource=%s reason=invalid_uuid", label)
        raise HTTPException(status_code=422, detail=f"Invalid {label} UUID") from exc


async def _handle(service, *args):
    logger.info("credit_request_started operation=%s", service.__name__)
    try:
        result = await service(*args)
        logger.info("credit_request_completed operation=%s", service.__name__)
        return result
    except KeyError as exc:
        logger.warning("credit_request_rejected operation=%s reason=missing_fields", service.__name__)
        raise HTTPException(status_code=422, detail="Required database field is missing") from exc
    except LookupError as exc:
        logger.warning("credit_resource_not_found operation=%s", service.__name__)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FileExistsError as exc:
        logger.warning("credit_request_conflict operation=%s reason=active_loan", service.__name__)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except PermissionError as exc:
        logger.warning("credit_request_conflict operation=%s reason=ineligible", service.__name__)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning("credit_request_conflict operation=%s reason=invalid_state", service.__name__)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("credit_request_failed operation=%s", service.__name__)
        raise HTTPException(status_code=503, detail="Supabase request failed") from exc


@router.get("/{invoice_id}/recommendation", response_model=CreditRecommendationResponse)
async def credit_recommendation_route(invoice_id: str):
    return await _handle(
        get_credit_recommendation, _uuid(invoice_id, "invoice")
    )


@write_router.post("/{invoice_id}/accept", response_model=CreditAcceptanceResponse)
async def accept_credit_route(invoice_id: str, request: AcceptCreditRequest):
    if not request.mandate_accepted:
        logger.warning("credit_accept_rejected reason=mandate_not_accepted")
        raise HTTPException(status_code=422, detail="Mandate acceptance is required")
    return await _handle(accept_credit, _uuid(invoice_id, "invoice"))


@router.get("/loans/{loan_id}/schedule", response_model=CreditScheduleResponse)
async def credit_schedule_route(loan_id: str):
    return await _handle(get_credit_schedule, _uuid(loan_id, "loan"))


@write_router.post(
    "/loans/{loan_id}/simulate-week", response_model=WeeklySimulationResponse
)
async def simulate_credit_week_route(loan_id: str):
    return await _handle(simulate_credit_week, _uuid(loan_id, "loan"))


@router.get("/loans/{loan_id}/alerts", response_model=CreditAlertsResponse)
async def credit_alerts_route(loan_id: str):
    return await _handle(get_credit_alerts, _uuid(loan_id, "loan"))
