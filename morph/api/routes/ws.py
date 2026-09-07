"""WebSocket endpoints for real-time experiment progress and telemetry streaming."""

from __future__ import annotations

import asyncio
import contextlib

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


class ConnectionManager:
    """Fan-out for experiment progress events, with replay for late subscribers.

    The experiment engine runs in a worker thread and pushes `TrialEvent` dicts
    through `broadcast_event`. A browser client usually opens its WebSocket a
    beat after the experiment already started, so every event is also appended
    to a per-experiment log and replayed in order the moment a socket connects.
    Append-and-send happens under one lock, so a socket that connects mid-run
    sees each event exactly once: either in the replayed log or live, never both.
    """

    def __init__(self) -> None:
        self.active_connections: dict[str, list[WebSocket]] = {}
        self.event_log: dict[str, list[dict]] = {}
        self.finished: set[str] = set()
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self) -> None:
        """Point the manager at the currently running server loop.

        A background experiment thread cannot ``await``; it hands events back to
        this loop via ``emit_threadsafe``. Called from the request handlers that
        run on the server loop, so it is idempotent and self-heals when a test
        harness stands up a fresh loop per client. The lock is recreated with
        the loop, since an ``asyncio.Lock`` must not migrate between loops.
        """
        loop = asyncio.get_running_loop()
        if loop is not self._loop:
            self._loop = loop
            self._lock = asyncio.Lock()

    def open_log(self, experiment_id: str) -> None:
        self.event_log.setdefault(experiment_id, [])
        self.finished.discard(experiment_id)

    def emit_threadsafe(self, experiment_id: str, data: dict) -> None:
        """Thread-safe entry point: schedule ``broadcast_event`` on the server loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            # No server loop (e.g. a unit test without lifespan): just log it so
            # a later subscriber can still replay.
            self.event_log.setdefault(experiment_id, []).append(data)
            if data.get("type") in ("done", "error"):
                self.finished.add(experiment_id)
            return
        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(self.broadcast_event(experiment_id, data), loop)

    async def connect(self, experiment_id: str, websocket: WebSocket) -> list[dict]:
        await websocket.accept()
        async with self._lock:
            self.active_connections.setdefault(experiment_id, []).append(websocket)
            return list(self.event_log.get(experiment_id, []))

    async def disconnect(self, experiment_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            sockets = self.active_connections.get(experiment_id)
            if sockets and websocket in sockets:
                sockets.remove(websocket)
            if sockets is not None and not sockets:
                del self.active_connections[experiment_id]

    async def broadcast_event(self, experiment_id: str, data: dict) -> None:
        """Append `data` to the experiment log and push it to every live socket."""
        async with self._lock:
            self.event_log.setdefault(experiment_id, []).append(data)
            if data.get("type") in ("done", "error"):
                self.finished.add(experiment_id)
            sockets = list(self.active_connections.get(experiment_id, []))
            dead = []
            for ws in sockets:
                try:
                    await ws.send_json(data)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                live = self.active_connections.get(experiment_id)
                if live and ws in live:
                    live.remove(ws)

    def is_finished(self, experiment_id: str) -> bool:
        return experiment_id in self.finished


manager = ConnectionManager()


@router.websocket("/experiment/{experiment_id}")
async def experiment_websocket_endpoint(websocket: WebSocket, experiment_id: str) -> None:
    """Stream live trial results, comparisons, and the final verdict to a client."""
    manager.bind_loop()
    backlog = await manager.connect(experiment_id, websocket)
    try:
        await websocket.send_json({
            "type": "connected",
            "experiment_id": experiment_id,
            "status": "ready",
        })
        for event in backlog:
            await websocket.send_json(event)

        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        await manager.disconnect(experiment_id, websocket)
    except Exception:
        await manager.disconnect(experiment_id, websocket)
