"""WebSocket endpoints for real-time experiment progress and telemetry streaming."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Manages active WebSocket connections subscribed to experiment IDs."""

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, experiment_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            if experiment_id not in self.active_connections:
                self.active_connections[experiment_id] = []
            self.active_connections[experiment_id].append(websocket)

    async def disconnect(self, experiment_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            if experiment_id in self.active_connections:
                if websocket in self.active_connections[experiment_id]:
                    self.active_connections[experiment_id].remove(websocket)
                if not self.active_connections[experiment_id]:
                    del self.active_connections[experiment_id]

    async def broadcast_event(self, experiment_id: str, data: dict) -> None:
        """Send event payload to all clients connected to the experiment ID."""
        async with self._lock:
            sockets = list(self.active_connections.get(experiment_id, []))

        for ws in sockets:
            try:
                await ws.send_json(data)
            except Exception:
                await self.disconnect(experiment_id, ws)


manager = ConnectionManager()


@router.websocket("/experiment/{experiment_id}")
async def experiment_websocket_endpoint(websocket: WebSocket, experiment_id: str) -> None:
    """Stream live trial results, progress updates, and telemetry to connected dashboard clients."""
    await manager.connect(experiment_id, websocket)
    try:
        # Send initial confirmation handshake
        await websocket.send_json({
            "type": "connected",
            "experiment_id": experiment_id,
            "status": "ready",
        })
        while True:
            # Keep connection open and accept ping/pong or control messages
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(experiment_id, websocket)
    except Exception:
        await manager.disconnect(experiment_id, websocket)
