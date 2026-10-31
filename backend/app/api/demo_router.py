"""POST /api/demo/load-sample — CIS §4 (Module 2 slice 1).

Fail-safe demo trigger reading the golden response from the shared JSON fixture.
Audit/financial fields stay fixture-verbatim; voice fields are localized when
Sarvam is available. No Gemini scan or DB writes occur.

Locked decision B2: load-sample NEVER broadcasts on /ws/counter. In live
REST mode the frontend applies this REST response directly; when the
WebSocket slice lands, only real scans broadcast.
"""

import logging

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from app.core.config import GOLDEN_SAMPLE_ID
from app.services.pipeline import FixturePipeline
from app.services.sarvam_tts import synthesize_alert, translate_alert

logger = logging.getLogger("parchapay.api")
router = APIRouter()

_fixture_cache = FixturePipeline()


@router.post("/api/demo/load-sample")
async def load_sample(body: dict = Body(default={})) -> JSONResponse:
    sample_id = (body or {}).get("sample_id") or ""
    if sample_id != GOLDEN_SAMPLE_ID:
        raise HTTPException(status_code=404, detail=f"unknown sample_id {sample_id!r}; available: {GOLDEN_SAMPLE_ID!r}")

    fixture = _fixture_cache.load()
    translated_transcript = await run_in_threadpool(translate_alert, fixture.voice_transcript)
    if translated_transcript is None:
        return JSONResponse(content=fixture.model_dump(mode="json"))

    audio_url = await run_in_threadpool(
        synthesize_alert, translated_transcript, fixture.invoice_id
    )
    localized_fixture = fixture.model_copy(
        update={
            "voice_transcript": translated_transcript,
            "audio_alert_url": audio_url or fixture.audio_alert_url,
        }
    )
    return JSONResponse(content=localized_fixture.model_dump(mode="json"))
