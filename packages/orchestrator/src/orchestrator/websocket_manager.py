import asyncio
import json
import logging
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger("orchestrator.ws")


class WebSocketManager:
    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.append(ws)
        logger.info(f"[WS] Client connected — total: {len(self._connections)}")

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.remove(ws)
        logger.info(f"[WS] Client disconnected — total: {len(self._connections)}")

    async def broadcast(self, data: Any) -> None:
        if not self._connections:
            return
        message = json.dumps(data, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.remove(ws)

    async def broadcast_log(self, message: str) -> None:
        await self.broadcast({"type": "log", "message": message})

    async def broadcast_status(self, query_id: str, status: str) -> None:
        await self.broadcast(
            {"type": "status_change", "query_id": query_id, "status": status}
        )

    async def relay_redis_logs(self, redis_client) -> None:
        """Subscribe to orchestrator:logs Redis channel and relay to WS clients."""
        pubsub = redis_client.pubsub()
        await pubsub.subscribe("orchestrator:logs")
        async for message in pubsub.listen():
            if message["type"] == "message":
                await self.broadcast_log(message["data"].decode())
