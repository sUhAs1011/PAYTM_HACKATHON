"""POST /api/demo/load-sample — CIS §4 (Module 2 slice 1).

Fail-safe demo trigger returning the seeded golden response (CIS §5)
VERBATIM — read from contracts/demo_bill_fixture.json, no DB writes.

Locked decision B2: load-sample NEVER broadcasts on /ws/counter. In live
REST mode the frontend applies this REST response directly; when the
WebSocket slice lands, only real scans broadcast.
"""

import logging

from fastapi import APIRouter, Body, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import GOLDEN_SAMPLE_ID
from app.services.pipeline import FixturePipeline

logger = logging.getLogger("parchapay.api")
router = APIRouter()

_fixture_cache = FixturePipeline()


@router.post("/api/demo/load-sample")
async def load_sample(body: dict = Body(default={})) -> JSONResponse:
    sample_id = (body or {}).get("sample_id") or ""
    if sample_id != GOLDEN_SAMPLE_ID:
        raise HTTPException(status_code=404, detail=f"unknown sample_id {sample_id!r}; available: {GOLDEN_SAMPLE_ID!r}")

    fixture = _fixture_cache.load()
    # Return the fixture as its original dict — verbatim, CIS §5.
    return JSONResponse(content=fixture.model_dump())
