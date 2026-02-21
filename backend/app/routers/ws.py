"""
WebSocket endpoint for real-time UI updates.
Clients connect here and receive push notifications for:
  - Pipeline run status changes
  - Trade executions
  - Circuit breaker events
  - Price updates (Phase 5)
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.append(ws)
        logger.info(f"WebSocket connected. Total connections: {len(self.active)}")

    def disconnect(self, ws: WebSocket) -> None:
        self.active.remove(ws)
        logger.info(f"WebSocket disconnected. Total connections: {len(self.active)}")

    async def broadcast(self, message: dict[str, Any]) -> None:
        disconnected = []
        for ws in self.active:
            try:
                await ws.send_text(json.dumps(message))
            except Exception:
                disconnected.append(ws)
        for ws in disconnected:
            self.active.remove(ws)


manager = ConnectionManager()


@router.websocket("/updates")
async def websocket_updates(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send a welcome ping so the client knows we're alive
        await websocket.send_text(json.dumps({"type": "connected", "message": "Class Trader online."}))
        while True:
            # Keep connection alive — actual events are pushed via manager.broadcast()
            await asyncio.sleep(30)
            await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
