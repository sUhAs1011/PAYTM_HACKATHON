"""POST /api/parcha/scan — CIS §4 ingress, human-in-the-loop variant.

Scan now runs Gemini extraction only and persists a `user_pending_review`
draft; the deterministic audit runs on POST /api/parcha/{id}/confirm after
the merchant reviews and corrects the parse. SCAN_STARTED still broadcasts
here; AUDIT_COMPLETE moved to the confirm route.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.contracts import ScanDraftResponse, ScanStartedData
from app.core.config import ALLOWED_UPLOAD_CONTENT_TYPES, MAX_UPLOAD_BYTES, get_settings
from app.core.db import get_client
from app.services import merchant_resolver
from app.services.pipeline import get_pipeline

logger = logging.getLogger("parchapay.api")
router = APIRouter()


@router.post("/api/parcha/scan", response_model=ScanDraftResponse)
async def scan_parcha(
    request: Request,
    file: UploadFile = File(...),
    merchant_id: str = Form(""),
) -> ScanDraftResponse:
    if file.content_type not in ALLOWED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"unsupported file type {file.content_type!r}; allowed: image/jpeg, image/png, application/pdf",
        )
    try:
        image_bytes = await file.read()
    finally:
        await file.close()
    if not image_bytes:
        raise HTTPException(status_code=422, detail="empty file")
    if len(image_bytes) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="file exceeds 20 MB limit")

    # Event 1 precedes DB and pipeline work; load-sample is deliberately REST-only.
    started = ScanStartedData(
        session_id=f"sess_{uuid4().hex[:8]}",
        timestamp=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        status="PROCESSING_IMAGE",
        message="Extracting supplier bill details via Gemini 3.6 Flash...",
    )
    await request.app.state.ws_manager.broadcast("SCAN_STARTED", started.model_dump(mode="json"))

    try:
        client = await get_client()
        merchant = await merchant_resolver.resolve_merchant(
            client, get_settings().demo_merchant_id, merchant_id
        )
    except RuntimeError as exc:
        logger.error("merchant resolution failed: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    try:
        return await get_pipeline().extract_and_draft(
            image_bytes, file.content_type or "", merchant
        )
    except ValueError as exc:
        logger.info("scan draft rejected during extraction or parsing: %s", exc)
        raise HTTPException(status_code=422, detail="invoice data failed validation") from exc
    except RuntimeError as exc:
        logger.error("vision or scan service unavailable: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="scan pipeline service unavailable") from exc
    except Exception as exc:
        logger.exception("scan pipeline failed (%s)", type(exc).__name__)
        raise HTTPException(status_code=500, detail="scan pipeline failed") from exc
