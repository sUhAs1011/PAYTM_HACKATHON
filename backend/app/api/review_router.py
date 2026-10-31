"""Human-in-the-loop review routes (Module 3 extension).

GET /api/parcha/pending-review?merchant_id=  — a merchant's review queue
GET /api/parcha/{invoice_id}/review          — one draft's parsed items
POST /api/parcha/{invoice_id}/confirm        — corrections → audit → bill_verified

Drafts live in `invoices`/`invoice_line_items` with status
`user_pending_review`; confirm flips them to `bill_verified` and is the
only point where AUDIT_COMPLETE is broadcast.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.contracts import (
    AuditCompleteData,
    AuditedInvoiceResponse,
    ConfirmCorrectionsRequest,
    DraftLineItem,
    InvoiceDraftReview,
    PendingReviewListResponse,
)
from app.core import repo
from app.core.db import get_client
from app.core.money import dec
from app.services.pipeline import DraftConflictError, DraftNotFoundError, get_pipeline

logger = logging.getLogger("parchapay.api")
router = APIRouter()


def _to_draft_review(bundle: dict) -> InvoiceDraftReview:
    supplier = bundle.get("suppliers") or {}
    items = [
        DraftLineItem(
            id=str(item["id"]),
            raw_item_name=item["raw_item_name"],
            printed_qty=int(item["printed_qty"]),
            billed_qty=int(item["billed_qty"]),
            free_qty=int(item["free_qty"]),
            billed_rate=float(dec(item["billed_rate"])),
            tax_percent=float(dec(item["tax_percent"])),
            true_landed_cost=float(dec(item["true_landed_cost"])),
            mrp=float(dec(item["mrp"])) if item.get("mrp") is not None else None,
            ocr_confidence=float(dec(item["ocr_confidence"])),
            has_pen_markup=bool(item["has_pen_markup"]),
            bounding_box=item.get("bounding_box"),
            canonical_sku_id=str(item["canonical_sku_id"]) if item.get("canonical_sku_id") else None,
        )
        for item in (bundle.get("invoice_line_items") or [])
    ]
    return InvoiceDraftReview(
        invoice_id=str(bundle["id"]),
        merchant_id=str(bundle["merchant_id"]),
        supplier_id=str(bundle["supplier_id"]) if bundle.get("supplier_id") else None,
        supplier_name=supplier.get("name") or "",
        supplier_gstin=supplier.get("gstin") or "",
        invoice_number=bundle.get("invoice_number") or "",
        invoice_date=str(bundle["invoice_date"]),
        billed_total=float(dec(bundle["billed_total"])),
        status=bundle["status"],
        dispute_crop_url=bundle.get("dispute_crop_url") or "",
        items=items,
    )


@router.get("/api/parcha/pending-review", response_model=PendingReviewListResponse)
async def list_pending_reviews(
    merchant_id: str = Query(..., min_length=1),
) -> PendingReviewListResponse:
    try:
        UUID(merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="merchant_id must be a UUID") from exc
    try:
        client = await get_client()
        rows = await repo.get_pending_reviews(client, merchant_id)
    except RuntimeError as exc:
        logger.error("pending-review query unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    logger.info(
        "pending-review list merchant_id=%s draft_count=%d", merchant_id, len(rows)
    )
    return PendingReviewListResponse(
        merchant_id=merchant_id,
        drafts=[_to_draft_review(row) for row in rows],
    )


@router.get("/api/parcha/{invoice_id}/review", response_model=InvoiceDraftReview)
async def get_review(
    invoice_id: str,
    merchant_id: str = Query(..., min_length=1),
) -> InvoiceDraftReview:
    try:
        UUID(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invoice_id must be a UUID") from exc
    try:
        UUID(merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="merchant_id must be a UUID") from exc
    try:
        client = await get_client()
        bundle = await repo.get_invoice_bundle(client, invoice_id, merchant_id)
    except RuntimeError as exc:
        logger.error("review fetch unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    if bundle is None:
        raise HTTPException(status_code=404, detail="invoice not found")
    if bundle.get("status") != repo.INVOICE_STATUS_USER_PENDING_REVIEW:
        raise HTTPException(
            status_code=409,
            detail=f"invoice status {bundle.get('status')!r} is not awaiting review",
        )
    return _to_draft_review(bundle)


@router.post("/api/parcha/{invoice_id}/confirm", response_model=AuditedInvoiceResponse)
async def confirm_review(
    request: Request,
    invoice_id: str,
    body: ConfirmCorrectionsRequest,
) -> AuditedInvoiceResponse:
    try:
        UUID(invoice_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invoice_id must be a UUID") from exc
    try:
        UUID(body.merchant_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="merchant_id must be a UUID") from exc
    try:
        audited = await get_pipeline().confirm_and_audit(
            invoice_id, body.merchant_id, body
        )
    except DraftNotFoundError as exc:
        raise HTTPException(status_code=404, detail="invoice not found") from exc
    except DraftConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.error("confirm pipeline unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="scan pipeline service unavailable") from exc
    except Exception as exc:
        logger.exception("confirm pipeline failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="confirm pipeline failed") from exc

    # AUDIT_COMPLETE fires only after human verification (review-layer decision).
    event_data = AuditCompleteData.model_validate(
        audited.model_dump(exclude={"supplier_gstin", "invoice_date"})
    )
    await request.app.state.ws_manager.broadcast("AUDIT_COMPLETE", event_data.model_dump(mode="json"))
    return audited
