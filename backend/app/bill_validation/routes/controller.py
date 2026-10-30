import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.bill_validation.schema.schema import (
    InvoiceAlertsResponse,
    InvoiceValidationResponse,
)
from app.bill_validation.service.service import get_bill_alerts, validate_bill

router = APIRouter(prefix="/api/parcha", tags=["Module 4 — bill validation"])
logger = logging.getLogger(__name__)


def _validate_id(invoice_id: str) -> str:
    try:
        return str(UUID(invoice_id))
    except ValueError as exc:
        logger.warning("bill_request_rejected reason=invalid_invoice_uuid")
        raise HTTPException(status_code=422, detail="Invalid invoice UUID") from exc


async def _call(service, invoice_id: str):
    try:
        normalized_id = _validate_id(invoice_id)
        logger.info(
            "bill_request_started operation=%s invoice_id=%s",
            service.__name__,
            normalized_id,
        )
        result = await service(normalized_id)
        logger.info(
            "bill_request_completed operation=%s invoice_id=%s alert_count=%s",
            service.__name__,
            normalized_id,
            len(result.get("alerts", [])),
        )
        return result
    except KeyError as exc:
        logger.warning(
            "bill_request_rejected operation=%s invoice_id=%s reason=missing_fields",
            service.__name__,
            invoice_id,
        )
        raise HTTPException(status_code=422, detail="Invoice data is missing fields") from exc
    except LookupError as exc:
        logger.warning(
            "bill_request_not_found operation=%s invoice_id=%s",
            service.__name__,
            invoice_id,
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        logger.warning(
            "bill_request_rejected operation=%s invoice_id=%s reason=invalid_data",
            service.__name__,
            invoice_id,
        )
        raise HTTPException(status_code=422, detail="Invoice data cannot be validated") from exc
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(
            "bill_request_failed operation=%s invoice_id=%s",
            service.__name__,
            invoice_id,
        )
        raise HTTPException(status_code=503, detail="Supabase request failed") from exc


@router.get("/{invoice_id}/validate", response_model=InvoiceValidationResponse)
async def validate_invoice_route(invoice_id: str):
    return await _call(validate_bill, invoice_id)


@router.get("/{invoice_id}/alerts", response_model=InvoiceAlertsResponse)
async def invoice_alerts_route(invoice_id: str):
    return await _call(get_bill_alerts, invoice_id)
