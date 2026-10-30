"""ParchaPay AI — API gateway entrypoint (Module 2 slices 1–2).

Implements the four CIS §4 REST endpoints, `/ws/counter`, `/static`, and
the `/healthz` operational probe. The live vision/audit pipeline remains
provisionally backed (see app/services/).

All traffic is reverse-proxied through the Angular dev server on 4200
(CIS §6.2); the API itself listens on 8000. No CORS middleware needed.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.api.demo_router import router as demo_router
from app.api.export_router import router as export_router
from app.api.resolve_router import router as resolve_router
from app.api.scan_router import router as scan_router
from app.api.ws_router import router as ws_router
from app.core.config import get_settings
from app.core.ws_manager import WebSocketManager
from app.services.credit_rules import ProvisionalCreditRules, set_credit_rules
from app.services.pipeline import FixturePipeline, get_pipeline, set_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("parchapay.api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    ws_manager = WebSocketManager()
    application.state.ws_manager = ws_manager
    set_pipeline(FixturePipeline())  # Module 3/4 replace via set_pipeline()
    set_credit_rules(ProvisionalCreditRules())  # Module 4 replaces via set_credit_rules()
    # Boot resilient: the compose healthcheck only needs a listening socket;
    # DB misconfiguration surfaces as a clean 503 on the first DB-touching
    # call instead of crashing the pod.
    if not (settings.url and settings.secret_key):
        logger.warning("SUPABASE_URL / SUPABASE_SECRET_KEY missing — DB endpoints will return 503")
    if not settings.demo_merchant_id:
        logger.warning(
            "PARCHA_DEMO_MERCHANT_ID not set — merchant resolution falls back to the first seeded merchant"
        )
    logger.info("ParchaPay API up (module2-slice-2): REST + websocket + static")
    try:
        yield
    finally:
        await ws_manager.close_all()


app = FastAPI(
    title="ParchaPay AI — API Gateway",
    description="Module 2 slices 1–2: CIS §4 REST + /ws/counter and /static.",
    version="0.2.0",
    lifespan=lifespan,
)

app.include_router(scan_router)
app.include_router(resolve_router)
app.include_router(export_router)
app.include_router(demo_router)
app.include_router(ws_router)

# CIS §6.2 relative static URLs are served through the Angular reverse proxy.
# Directory existence is maintained in the repo and persisted by compose.yaml.
# The golden fixture crop path has a labeled placeholder JPEG. Its audio WAV
# is intentionally absent, so the existing client can fall back to speaking
# voice_transcript instead of playing fake/empty audio.
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
(STATIC_ROOT / "crops").mkdir(parents=True, exist_ok=True)
(STATIC_ROOT / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_ROOT, check_dir=True), name="static")


@app.get("/healthz")
async def healthz() -> dict:
    """Operational probe for the compose healthcheck (additive, outside the
    CIS REST table — documented in .opencode/plans/module2-rest-api-plan.md)."""
    settings = get_settings()
    return {
        "status": "ok",
        "slice": "module2-slice-2",
        "pipeline": type(get_pipeline()).__name__,
        "demo_merchant_configured": bool(settings.demo_merchant_id),
        "supabase_configured": bool(settings.url and settings.secret_key),
    }
