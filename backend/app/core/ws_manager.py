"""In-memory WebSocket connection manager for CIS `/ws/counter`.

Every connected counter receives each broadcast. Connections are ephemeral:
no auth, rooms, persistence, or replay. The global client lock is not held
while sending network frames; per-client locks serialize frame writes.
"""

import asyncio
import logging
from typing import Any, Literal

from fastapi import WebSocket
from starlette.websockets import WebSocketState

logger = logging.getLogger("parchapay.api.ws")
WsEventName = Literal["SCAN_STARTED", "AUDIT_COMPLETE", "PAYOUT_APPROVED"]


class WebSocketManager:
    """Tracks active clients and broadcasts `{event, data}` envelopes."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._clients_lock = asyncio.Lock()
        self._send_locks: dict[WebSocket, asyncio.Lock] = {}

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._clients_lock:
            self._clients.add(websocket)
            self._send_locks[websocket] = asyncio.Lock()
        logger.info("counter websocket connected (clients=%d)", self.client_count)

    async def disconnect(self, websocket: WebSocket) -> None:
        async with self._clients_lock:
            self._clients.discard(websocket)
            self._send_locks.pop(websocket, None)
        logger.info("counter websocket disconnected (clients=%d)", self.client_count)

    async def broadcast(self, event: WsEventName, data: dict[str, Any]) -> None:
        """Broadcast one CIS envelope to the clients connected at send time."""
        envelope = {"event": event, "data": data}
        async with self._clients_lock:
            targets = [(client, self._send_locks[client]) for client in self._clients]
        if not targets:
            return

        results = await asyncio.gather(
            *(self._send_one(client, lock, envelope) for client, lock in targets),
            return_exceptions=True,
        )
        for (client, _), result in zip(targets, results):
            if isinstance(result, Exception) or result is False:
                await self.disconnect(client)

    async def _send_one(
        self,
        websocket: WebSocket,
        send_lock: asyncio.Lock,
        envelope: dict[str, Any],
    ) -> bool:
        async with send_lock:
            if websocket.client_state != WebSocketState.CONNECTED:
                return False
            await websocket.send_json(envelope)
        return True

    async def close_all(self) -> None:
        """Best-effort app-shutdown cleanup."""
        async with self._clients_lock:
            clients = list(self._clients)
            self._clients.clear()
            self._send_locks.clear()
        for websocket in clients:
            try:
                if websocket.application_state == WebSocketState.CONNECTED:
                    await websocket.close(code=1001, reason="server shutdown")
            except Exception:
                logger.debug("error closing websocket during shutdown", exc_info=True)
