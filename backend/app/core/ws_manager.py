"""In-memory WebSocket connection manager for CIS `/ws/counter`.

This is intentionally ephemeral: no auth, room routing, event persistence,
or replay. Every connected counter receives each broadcast. Locks protect
connection bookkeeping and serialize writes per socket; the global client
lock is never held while sending network frames.
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
        """Best-effort count for diagnostics/tests; mutate only under lock."""
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
        """Send one CIS envelope to the currently connected clients.

        Snapshot under the short-lived connection lock, then send without
        holding it. Failed/disconnected clients are removed after the send.
        """
        envelope = {"event": event, "data": data}
        async with self._clients_lock:
            targets = [(client, self._send_locks[client]) for client in self._clients]

        if not targets:
            return

        results = await asyncio.gather(
            *(self._send_one(client, send_lock, envelope) for client, send_lock in targets),
            return_exceptions=True,
        )
        failed = [
            client
            for (client, _), result in zip(targets, results)
            if isinstance(result, Exception) or result is False
        ]
        for client in failed:
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
