"""WebSocket endpoints for real-time experiment and threshold-search progress.

One :class:`ConnectionManager` serves both ``/ws/experiment/{id}`` and
``/ws/threshold/{id}``: a job id is a job id, the engine events differ only in
``kind``. Guarantees, in order of how much they matter to a dashboard:

* **In order, exactly once.** Every event is appended to a per-job log and
  copied into each subscriber's queue under one lock. A late subscriber gets
  the log replayed into its queue under that same lock, so a live event can
  never overtake a replayed one.
* **No sending under the lock.** Each socket has one writer task draining its
  queue; a stalled browser stalls only itself.
* **Bounded.** At most ``MAX_CACHED_EXPERIMENTS`` job logs are kept (oldest
  evicted, together with the result cache in ``routes/experiments.py``), and
  per-trial stdout/stderr tails are cut to ``EVENT_TAIL_CHARS``.
* **Unknown ids are refused** with close code 4404 rather than left open.
* The socket is closed (1000) after the terminal ``done`` / ``error`` frame.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import OrderedDict
from collections.abc import Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from morph.api import defaults

router = APIRouter()

_TERMINAL = frozenset({"done", "error"})
_CLOSE_UNKNOWN = 4404


def _trim_tails(data: dict) -> dict:
    """Keep trial stdout/stderr tails in the replay log small."""
    limit = defaults.EVENT_TAIL_CHARS
    for key in ("stdout_tail", "stderr_tail"):
        value = data.get(key)
        if isinstance(value, str) and len(value) > limit:
            data[key] = value[-limit:]
    return data


class ConnectionManager:
    """Fan-out for progress events, with ordered replay for late subscribers."""

    def __init__(self, max_jobs: int = defaults.MAX_CACHED_EXPERIMENTS) -> None:
        self.max_jobs = max_jobs
        self.event_log: OrderedDict[str, list[dict]] = OrderedDict()
        self.finished: set[str] = set()
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._evict_hooks: list[Callable[[str], None]] = []

    # ----------------------------------------------------------- lifecycle

    def bind_loop(self, loop: asyncio.AbstractEventLoop | None = None) -> None:
        """Point the manager at the server loop (lifespan does this once;
        handlers repeat it so a bare ``TestClient(app)`` without lifespan works)."""
        loop = loop or asyncio.get_running_loop()
        if loop is not self._loop:
            self._loop = loop
            self._lock = asyncio.Lock()

    def on_evict(self, hook: Callable[[str], None]) -> None:
        """Register a callback run with each job id evicted from the log."""
        self._evict_hooks.append(hook)

    def known(self, job_id: str) -> bool:
        return job_id in self.event_log

    def is_finished(self, job_id: str) -> bool:
        return job_id in self.finished

    def open_log(self, job_id: str) -> None:
        """Create the log for a new job, evicting the oldest beyond the cap."""
        self.event_log[job_id] = []
        self.event_log.move_to_end(job_id)
        self.finished.discard(job_id)
        while len(self.event_log) > self.max_jobs:
            old, _ = self.event_log.popitem(last=False)
            self.finished.discard(old)
            for queue in self._queues.pop(old, []):
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(None)  # tells the writer to close
            for hook in self._evict_hooks:
                with contextlib.suppress(Exception):
                    hook(old)

    def drop(self, job_id: str) -> None:
        self.event_log.pop(job_id, None)
        self.finished.discard(job_id)
        for queue in self._queues.pop(job_id, []):
            with contextlib.suppress(asyncio.QueueFull):
                queue.put_nowait(None)

    # ------------------------------------------------------------ producers

    def _record(self, job_id: str, data: dict) -> None:
        data = _trim_tails(data)
        log = self.event_log.get(job_id)
        if log is None:
            # Job was evicted (or never opened): keep the event anyway so a
            # subscriber can still replay, but never let it grow past the cap.
            self.open_log(job_id)
            log = self.event_log[job_id]
        log.append(data)
        if data.get("type") in _TERMINAL:
            self.finished.add(job_id)

    def emit_threadsafe(self, job_id: str, data: dict) -> None:
        """Thread-safe entry point: schedule ``broadcast_event`` on the server loop."""
        loop = self._loop
        if loop is None or loop.is_closed():
            # No server loop (unit test without lifespan): log only.
            self._record(job_id, data)
            return
        with contextlib.suppress(RuntimeError):
            asyncio.run_coroutine_threadsafe(self.broadcast_event(job_id, data), loop)

    async def broadcast_event(self, job_id: str, data: dict) -> None:
        """Append ``data`` to the job log and enqueue it for every subscriber."""
        async with self._lock:
            self._record(job_id, data)
            for queue in self._queues.get(job_id, []):
                queue.put_nowait(data)
            if data.get("type") in _TERMINAL:
                for queue in self._queues.get(job_id, []):
                    queue.put_nowait(None)

    # ------------------------------------------------------------ consumers

    async def subscribe(self, job_id: str) -> asyncio.Queue | None:
        """Register a subscriber; its queue starts with the full backlog.

        Returns ``None`` for an unknown job id.
        """
        async with self._lock:
            if job_id not in self.event_log:
                return None
            queue: asyncio.Queue = asyncio.Queue()
            for event in self.event_log[job_id]:
                queue.put_nowait(event)
            if job_id in self.finished:
                queue.put_nowait(None)
            self._queues.setdefault(job_id, []).append(queue)
            return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            queues = self._queues.get(job_id)
            if queues and queue in queues:
                queues.remove(queue)
            if queues is not None and not queues:
                del self._queues[job_id]

    # Backwards-compatible names used by older callers/tests.
    async def connect(self, job_id: str, websocket: WebSocket) -> asyncio.Queue | None:
        await websocket.accept()
        return await self.subscribe(job_id)

    async def disconnect(self, job_id: str, queue: asyncio.Queue) -> None:
        await self.unsubscribe(job_id, queue)


manager = ConnectionManager()


async def _serve(websocket: WebSocket, job_id: str, kind: str) -> None:
    manager.bind_loop()
    await websocket.accept()
    queue = await manager.subscribe(job_id)
    if queue is None:
        await websocket.close(code=_CLOSE_UNKNOWN, reason=f"unknown {kind} id {job_id!r}")
        return

    async def writer() -> None:
        try:
            await websocket.send_json({
                "type": "connected",
                f"{kind}_id": job_id,
                "experiment_id": job_id,
                "status": "ready",
            })
            while True:
                event = await queue.get()
                if event is None:
                    break
                await websocket.send_json(event)
        finally:
            if websocket.client_state is WebSocketState.CONNECTED:
                with contextlib.suppress(Exception):
                    await websocket.close(code=1000)

    write_task = asyncio.create_task(writer())
    try:
        while not write_task.done():
            receive = asyncio.ensure_future(websocket.receive_text())
            done, _ = await asyncio.wait({receive, write_task}, return_when=asyncio.FIRST_COMPLETED)
            if receive in done:
                text = receive.result()
                if text == "ping":
                    await websocket.send_text("pong")
            else:
                receive.cancel()
                with contextlib.suppress(BaseException):
                    await receive
    except (WebSocketDisconnect, RuntimeError):
        pass
    except Exception:
        pass
    finally:
        write_task.cancel()
        with contextlib.suppress(BaseException):
            await write_task
        await manager.unsubscribe(job_id, queue)


@router.websocket("/experiment/{experiment_id}")
async def experiment_websocket_endpoint(websocket: WebSocket, experiment_id: str) -> None:
    """Stream live trial, evidence and comparison events and the verdict for one experiment."""
    await _serve(websocket, experiment_id, "experiment")


@router.websocket("/threshold/{threshold_id}")
async def threshold_websocket_endpoint(websocket: WebSocket, threshold_id: str) -> None:
    """Stream ``search_probe`` events and the final bracket for one threshold search."""
    await _serve(websocket, threshold_id, "threshold")
