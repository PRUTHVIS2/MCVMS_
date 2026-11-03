"""WebSocket manager for real-time tracks, events, alerts, and system status updates.

docs/08_API_AND_UI.md section 2:
WebSocket /ws: alert.created, alert.updated, event.created|updated|ended, camera.status, tracks.
"""

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages active WebSocket connections and delivers broadcasts."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]):
        """Asynchronously send message to all connected clients."""
        if not self.active_connections:
            return
        data = json.dumps(message)
        dead_connections = []
        for connection in list(self.active_connections):
            try:
                await connection.send_text(data)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"WebSocket client disconnected during send: {e}")
                dead_connections.append(connection)
        for dc in dead_connections:
            self.disconnect(dc)

    def broadcast_sync(self, message: dict[str, Any]):
        """Thread-safe synchronous broadcast dispatch."""
        if self.loop and self.loop.is_running():
            try:
                asyncio.run_coroutine_threadsafe(self.broadcast(message), self.loop)
            except Exception as e:  # noqa: BLE001
                logger.error(f"Failed to schedule WebSocket broadcast: {e}")
        else:
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    loop.create_task(self.broadcast(message))
            except Exception:  # noqa: BLE001, S110
                pass

    def broadcast_event(self, event_type: str, data: dict[str, Any]):
        """Broadcast an event update: event.created, event.updated, event.ended."""
        self.broadcast_sync({"type": event_type, "data": data})

    def broadcast_alert(self, alert_type: str, data: dict[str, Any]):
        """Broadcast an alert update: alert.created, alert.updated."""
        self.broadcast_sync({"type": alert_type, "data": data})

    async def broadcast_tracks(self, message: dict[str, Any]):
        """Legacy helper for live wall tracks."""
        await self.broadcast(message)


manager = ConnectionManager()


@router.websocket("")
@router.websocket("/")
async def websocket_dashboard(websocket: WebSocket):
    """Main dashboard WebSocket for events, alerts, and system notices."""
    await manager.connect(websocket)
    try:
        while True:
            # Keep-alive or client commands
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        manager.disconnect(websocket)


@router.websocket("/tracks/{cam_id}")
async def websocket_tracks(websocket: WebSocket, cam_id: str):
    """Live camera track overlay feed."""
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        manager.disconnect(websocket)
