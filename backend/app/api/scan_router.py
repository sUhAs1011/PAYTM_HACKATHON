"""POST /api/parcha/scan — CIS §4 (Module 2 slices 1–2).

multipart/form-data with `file` (image/jpeg | image/png | application/pdf)
and `merchant_id`. Validates, resolves the merchant (B1 chain), runs the
pipeline seam, returns the AuditedInvoiceResponse. In this slice the seam
is the FixturePipeline — the golden fixture shaped as the real payload,
zero DB writes (plan §3 note).
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.contracts import AuditCompleteData, AuditedInvoiceResponse, ScanStartedData
from app.core.config import ALLOWED_UPLOAD_CONTENT_TYPES, MAX_UPLOAD_BYTES, get_settings
from app.core.db import get_client
from app.services import merchant_resolver
from app.services.pipeline import get_pipeline

logger = logging.getLogger("parchapay.api")
router = APIRouter()


@router.post("/api/parcha/scan", response_model=AuditedInvoiceResponse)
async def scan_parcha(
    request: Request,
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

    # Broadcast before any DB/pipeline work, matching CIS §4's immediate
    # SCAN_STARTED event. Only uploaded scans take this path; load-sample is
    # deliberately REST-only (locked B2 decision).
    session_id = f"sess_{uuid4().hex[:8]}"
    timestamp = datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    started = ScanStartedData(
        session_id=session_id,
        timestamp=timestamp,
        status="PROCESSING_IMAGE",
        message="Auditing supplier parcha via Gemini 2.5 Flash...",
    )
    await request.app.state.ws_manager.broadcast("SCAN_STARTED", started.model_dump(mode="json"))

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

    # The REST response intentionally has supplier_gstin/invoice_date; CIS
    # Event 2 is narrower and omits both. Re-validate/exclude to keep the WS
    # payload exact instead of broadcasting REST-only fields.
    event_data = AuditCompleteData.model_validate(
        audited.model_dump(exclude={"supplier_gstin", "invoice_date"})
    )
    await request.app.state.ws_manager.broadcast("AUDIT_COMPLETE", event_data.model_dump(mode="json"))
    return audited
