"""POST /api/parcha/scan — CIS §4 (Module 2 slice 1).

multipart/form-data with `file` (image/jpeg | image/png | application/pdf)
and `merchant_id`. Validates, resolves the merchant (B1 chain), runs the
pipeline seam, returns the AuditedInvoiceResponse. In this slice the seam
is the FixturePipeline — the golden fixture shaped as the real payload,
zero DB writes (plan §3 note).
"""

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.contracts import AuditedInvoiceResponse
from app.core.config import ALLOWED_UPLOAD_CONTENT_TYPES, MAX_UPLOAD_BYTES, get_settings
from app.core.db import get_client
from app.services import merchant_resolver
from app.services.pipeline import get_pipeline

logger = logging.getLogger("parchapay.api")
router = APIRouter()


@router.post("/api/parcha/scan", response_model=AuditedInvoiceResponse)
async def scan_parcha(
    file: UploadFile = File(...),
    merchant_id: str = Form(""),
) -> AuditedInvoiceResponse:
    if file.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported file type {file.content_type!r}; allowed: image/jpeg, image/png, application/pdf",
        )
    try:
        image_bytes = await file.read()
    finally:
        await file.close()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=422, detail="empty file")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 20 MB limit")

    client = await get_client()
    try:
        merchant = await merchant_resolver.resolve_merchant(client, get_settings().demo_merchant_id, merchant_id)
    except RuntimeError as exc:
        logger.error("merchant resolution failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        pipeline = get_pipeline()
        audited = await pipeline.extract_and_audit(image_bytes, file.content_type or "", merchant)
    except Exception as exc:
        logger.error("scan pipeline failed: %s", exc)
        raise HTTPException(status_code=500, detail="scan pipeline failed") from exc
    return audited
