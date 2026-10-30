"""WebSocket Connection Manager for Counter Dashboard (/ws/counter)."""

import json
import logging
from typing import Any, List
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Maintains active WebSocket connections to /counter projector dashboards."""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"[ws] Client connected. Total active: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"[ws] Client disconnected. Total active: {len(self.active_connections)}")

    async def broadcast(self, event: str, data: Any):
        """Broadcasts CIS-compliant envelope {"event": event, "data": data}."""
        payload = json.dumps({"event": event, "data": data})
        for connection in list(self.active_connections):
            try:
                await connection.send_text(payload)
            except Exception as exc:
                logger.warning(f"[ws] Send failed, disconnecting client: {exc}")
                self.disconnect(connection)


ws_manager = ConnectionManager()

