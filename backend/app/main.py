"""ParchaPay AI — API gateway entrypoint (Module 2 slice 1: REST only).

Currently implements the four CIS §4 REST endpoints + a /healthz
operational probe. NOT yet implemented (next slices): /ws/counter
WebSocket events, /static mounts for crops/audio, live pipeline wiring
(Module 3/4 seams are provisionally backed — see app/services/).

All traffic is reverse-proxied through the Angular dev server on 4200
(CIS §6.2); the API itself listens on 8000. No CORS middleware needed.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.demo_router import router as demo_router
from app.api.export_router import router as export_router
from app.api.resolve_router import router as resolve_router
from app.api.scan_router import router as scan_router
from app.core.config import get_settings
from app.services.credit_rules import ProvisionalCreditRules, set_credit_rules
from app.services.pipeline import FixturePipeline, get_pipeline, set_pipeline

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("parchapay.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
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
    logger.info("ParchaPay API up (module2-rest-1): scan/resolve/export/load-sample live")
    yield


app = FastAPI(
    title="ParchaPay AI — API Gateway",
    description="Module 2 slice 1: the four CIS §4 REST endpoints (WS + /static are later slices).",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(scan_router)
app.include_router(resolve_router)
app.include_router(export_router)
app.include_router(demo_router)


@app.get("/healthz")
async def healthz() -> dict:
    """Operational probe for the compose healthcheck (additive, outside the
    CIS REST table — documented in .opencode/plans/module2-rest-api-plan.md)."""
    settings = get_settings()
    return {
        "status": "ok",
        "slice": "module2-rest-1",
        "pipeline": type(get_pipeline()).__name__,
        "demo_merchant_configured": bool(settings.demo_merchant_id),
        "supabase_configured": bool(settings.url and settings.secret_key),
    }
