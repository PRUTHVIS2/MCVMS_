from fastapi import APIRouter, WebSocket, WebSocketDisconnect
import json
import logging
from typing import List

router = APIRouter(prefix="/ws", tags=["websocket"])
logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast_tracks(self, message: dict):
        # Fire and forget or handle disconnected gracefully
        data = json.dumps(message)
        for connection in self.active_connections:
            try:
                await connection.send_text(data)
            except Exception as e:
                logger.error(f"WebSocket broadcast error: {e}")
                self.disconnect(connection)

manager = ConnectionManager()

@router.websocket("/tracks/{cam_id}")
async def websocket_tracks(websocket: WebSocket, cam_id: str):
    await manager.connect(websocket)
    try:
        while True:
            # wait for messages from client, e.g. ping
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
