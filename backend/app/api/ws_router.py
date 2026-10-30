"""Persistent `/ws/counter` endpoint (CIS §4)."""

import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.ws_manager import WebSocketManager

logger = logging.getLogger("parchapay.api.ws")
router = APIRouter()


@router.websocket("/ws/counter")
async def counter_socket(websocket: WebSocket) -> None:
    manager: WebSocketManager = websocket.app.state.ws_manager
    await manager.connect(websocket)
    try:
        # The client currently sends no application messages. receive_text()
        # keeps the connection alive and raises WebSocketDisconnect cleanly.
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    except Exception:
        logger.exception("counter websocket ended unexpectedly")
    finally:
        await manager.disconnect(websocket)
