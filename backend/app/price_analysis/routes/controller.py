import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException

from app.price_analysis.schema.schema import InvoicePriceAnalysisResponse
from app.price_analysis.service.service import analyze_invoice_prices

router = APIRouter(prefix="/api/parcha", tags=["Module 4 — price analysis"])
logger = logging.getLogger(__name__)


@router.get("/{invoice_id}/price-analysis", response_model=InvoicePriceAnalysisResponse)
async def price_analysis_route(invoice_id: str):
    try:
        normalized_id = str(UUID(invoice_id))
    except ValueError as exc:
        logger.warning("price_analysis_request_rejected reason=invalid_invoice_uuid")
        raise HTTPException(status_code=422, detail="Invalid invoice UUID") from exc
    logger.info("price_analysis_request_started invoice_id=%s", normalized_id)
    try:
        result = await analyze_invoice_prices(normalized_id)
        logger.info(
            "price_analysis_request_completed invoice_id=%s item_count=%s",
            normalized_id,
            len(result.get("items", [])),
        )
        return result
    except KeyError as exc:
        logger.warning(
            "price_analysis_request_rejected invoice_id=%s reason=missing_fields",
            normalized_id,
        )
        raise HTTPException(status_code=422, detail="Invoice data is missing fields") from exc
    except LookupError as exc:
        logger.warning("price_analysis_invoice_not_found invoice_id=%s", normalized_id)
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ValueError, KeyError) as exc:
        logger.warning(
            "price_analysis_request_rejected invoice_id=%s reason=invalid_data",
            normalized_id,
        )
        raise HTTPException(status_code=422, detail="Price analysis input is invalid") from exc
    except Exception as exc:
        logger.exception(
            "price_analysis_request_failed invoice_id=%s",
            normalized_id,
        )
        raise HTTPException(status_code=503, detail="Supabase request failed") from exc
