"""ParchaPay AI — FastAPI Gateway & Realtime Broadcaster.

Orchestrates multimodal bill intake, Gemini 3.6 Flash extraction,
Pillow pen cropping, static asset serving, and WebSocket broadcasting.
"""

import logging
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.resolve_router import router as resolve_router
from app.api.scan_router import router as scan_router
from app.core.config import get_settings
from app.core.ws_manager import ws_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("parchapay")

app = FastAPI(
    title="ParchaPay AI Gateway",
    description="Backend API Gateway and Realtime Broadcaster for ParchaPay AI",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

settings = get_settings()

# Ensure static directories exist
crops_dir = settings.static_dir / "crops"
audio_dir = settings.static_dir / "audio"
crops_dir.mkdir(parents=True, exist_ok=True)
audio_dir.mkdir(parents=True, exist_ok=True)

# Mount local static assets for pen-markup proofs and audio synthesis
app.mount("/static", StaticFiles(directory=str(settings.static_dir)), name="static")

# Register REST routers
app.include_router(scan_router)
app.include_router(resolve_router)


@app.get("/health")
async def health_check():
    """Health check for container readiness."""
    return {"status": "ok", "service": "parchapay-api"}


@app.websocket("/ws/counter")
async def websocket_counter_endpoint(websocket: WebSocket):
    """Realtime duplex channel for /counter projector dashboard."""
    await ws_manager.connect(websocket)
    try:
        while True:
            # Keep connection open; receive client keep-alives or commands
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception as exc:
        logger.warning(f"[ws] Unexpected disconnect: {exc}")
        ws_manager.disconnect(websocket)

