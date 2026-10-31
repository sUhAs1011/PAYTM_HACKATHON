"""Integrated ParchaPay FastAPI gateway.

Registers CIS §4 routes, `/ws/counter`, `/static`, Module 4 read-only
endpoints, and the operational `/healthz` probe. Weekly-credit POST routes
remain unmounted per the user-approved ledger-contract decision.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
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
from app.credit.routes.controller import router as credit_read_router
from app.price_analysis.routes.controller import router as price_analysis_router
from app.services.credit_rules import LiveCreditRules, set_credit_rules
from app.services.pipeline import LiveParchaPipeline, get_pipeline, set_pipeline

configure_logging()
logger = logging.getLogger("parchapay.api")


@asynccontextmanager
async def lifespan(application: FastAPI):
    settings = get_settings()
    ws_manager = WebSocketManager()
    application.state.ws_manager = ws_manager
    set_pipeline(LiveParchaPipeline())
    set_credit_rules(LiveCreditRules())
    if not (settings.url and settings.secret_key):
        logger.warning("SUPABASE_URL / SUPABASE_SECRET_KEY missing — DB endpoints will return 503")
    if not settings.demo_merchant_id:
        logger.warning("PARCHA_DEMO_MERCHANT_ID not set — merchant resolution uses invoice-owning fallback")
    logger.info("ParchaPay integrated API starting pipeline=%s", type(get_pipeline()).__name__)
    try:
        yield
    finally:
        await ws_manager.close_all()


app = FastAPI(
    title="ParchaPay AI — API Gateway",
    description="CIS REST, WebSocket/static, and compatible Module 4 read APIs.",
    version="0.3.0",
    lifespan=lifespan,
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(scan_router)
app.include_router(resolve_router)
app.include_router(export_router)
app.include_router(demo_router)
app.include_router(ws_router)
app.include_router(bill_validation_router)
app.include_router(price_analysis_router)
app.include_router(credit_read_router)

settings = get_settings()
settings.static_dir.mkdir(parents=True, exist_ok=True)
(settings.static_dir / "crops").mkdir(parents=True, exist_ok=True)
(settings.static_dir / "audio").mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=settings.static_dir, check_dir=True), name="static")


@app.get("/healthz")
async def healthz() -> dict:
    """Operational container probe; not a product endpoint."""
    settings = get_settings()
    return {
        "status": "ok",
        "slice": "integrated-gateway",
        "pipeline": type(get_pipeline()).__name__,
        "demo_merchant_configured": bool(settings.demo_merchant_id),
        "supabase_configured": bool(settings.url and settings.secret_key),
    }


# Render uses one public web service. When the production image includes the
# Angular build, serve its SPA routes from this same origin so `/api`, `/static`,
# and `/ws` continue to work without a separate CORS/proxy configuration.
frontend_dir = settings.base_dir / "frontend-dist"
if frontend_dir.is_dir():
    frontend_root = frontend_dir.resolve()

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(frontend_root / "index.html")

    @app.get("/{frontend_path:path}", include_in_schema=False)
    async def frontend_spa_fallback(frontend_path: str) -> FileResponse:
        first_segment = frontend_path.partition("/")[0]
        if first_segment in {"api", "static", "ws"}:
            raise HTTPException(status_code=404, detail="not found")

        candidate = (frontend_root / frontend_path).resolve()
        if not candidate.is_relative_to(frontend_root):
            raise HTTPException(status_code=404, detail="not found")
        if candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(frontend_root / "index.html")
