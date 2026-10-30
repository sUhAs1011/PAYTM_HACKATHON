"""ParchaPay AI — integrated FastAPI gateway (Module 2 merge base).

Registers the CIS §4 REST/WebSocket/static surfaces plus Module 4's
read-only bill validation, price analysis, and credit GET endpoints. The
real Gemini/audit pipeline remains behind the replaceable services seams.

Weekly-credit write routes are deliberately not registered: the user chose
to keep the approved ledger contract unchanged. See AGENTS.md and the merge
integration plan for that decision.
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
from app.bill_validation.routes.controller import router as bill_validation_router
from app.core.config import get_settings
from app.core.logging_config import RequestLoggingMiddleware, configure_logging
from app.core.ws_manager import WebSocketManager
from app.price_analysis.routes.controller import router as price_analysis_router
from app.credit.routes.controller import router as credit_read_router
from app.services.credit_rules import ProvisionalCreditRules, set_credit_rules
from app.services.pipeline import FixturePipeline, get_pipeline, set_pipeline

configure_logging()
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("parchapay.api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    ws_manager = WebSocketManager()
    application.state.ws_manager = ws_manager
    set_pipeline(FixturePipeline())  # Module 3/4 replace via set_pipeline().
    set_credit_rules(ProvisionalCreditRules())  # Module 4 replaces via set_credit_rules().
    if not (settings.url and settings.secret_key):
        logger.warning("SUPABASE_URL / SUPABASE_SECRET_KEY missing — DB endpoints will return 503")
    if not settings.demo_merchant_id:
        logger.warning("PARCHA_DEMO_MERCHANT_ID not set — merchant resolution uses the invoice-owning fallback")
    logger.info("ParchaPay API up (integrated gateway): REST + WebSocket + static + Module 4 read routes")
    try:
        yield
    finally:
        await ws_manager.close_all()


app = FastAPI(
    title="ParchaPay AI — API Gateway",
    description="CIS §4 REST, /ws/counter, /static, and compatible Module 4 read APIs.",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(RequestLoggingMiddleware)

# CIS §4 REST APIs, WebSocket, plus Module 4's compatible read-only routes.
app.include_router(scan_router)
app.include_router(resolve_router)
app.include_router(export_router)
app.include_router(demo_router)
app.include_router(ws_router)
app.include_router(bill_validation_router)
app.include_router(price_analysis_router)
app.include_router(credit_read_router)

# CIS §6.2 relative static URLs are served through the Angular reverse proxy.
# Existing Compose mounts persist generated crop/audio assets outside the image.
STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"
STATIC_ROOT.mkdir(parents=True, exist_ok=True)
(STATIC_ROOT / "crops").mkdir(parents=True, exist_ok=True)
(STATIC_ROOT / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_ROOT, check_dir=True), name="static")


@app.get("/healthz")
async def healthz() -> dict:
    """Operational Compose probe; not an additional product API."""
    settings = get_settings()
    return {
        "status": "ok",
        "slice": "integrated-gateway",
        "pipeline": type(get_pipeline()).__name__,
        "demo_merchant_configured": bool(settings.demo_merchant_id),
        "supabase_configured": bool(settings.url and settings.secret_key),
    }
