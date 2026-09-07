"""The streaming experiment / threshold endpoints + their progress WebSockets.

`POST /experiments/stream` runs the engine in a worker thread and forwards every
`TrialEvent` to `/ws/experiment/{id}`, finishing with a `done` (or `error`)
frame. A subscriber that connects after the run started still gets the full
history replayed from the manager's per-job log, in order.
"""

from __future__ import annotations

import asyncio
import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from morph.api.app import app
from morph.api.routes.ws import ConnectionManager
from morph.schema.profile import (
    CPUInfo,
    EnvironmentProfile,
    FieldStatus,
    LocaleInfo,
    MemoryInfo,
    NetworkInfo,
    OSInfo,
    ProfileField,
)

_CMD = f'{sys.executable} -c "print(1)"'


def _profile(latency: float = 20.0, loss: float = 0.0) -> dict:
    return EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value="darwin", status=FieldStatus.CAPTURED),
            version=ProfileField(value="14.5", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="arm64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=8, status=FieldStatus.CAPTURED),
            logical_processors=ProfileField(value=8, status=FieldStatus.CAPTURED),
        ),
        memory=MemoryInfo(total_mb=ProfileField(value=16384, status=FieldStatus.CAPTURED)),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=latency, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=loss, status=FieldStatus.REQUESTED),
        ),
    ).model_dump()


def _drain(ws) -> tuple[list[dict], dict]:
    events: list[dict] = []
    while True:
        msg = ws.receive_json()
        if msg.get("type") == "event":
            events.append(msg)
        elif msg.get("type") in ("done", "error"):
            return events, msg


def test_stream_emits_events_then_done_batch():
    with TestClient(app) as client:
        resp = client.post(
            "/experiments/stream",
            json={"command": _CMD, "trials": 3, "mode": "batch", "target_profile": _profile()},
        )
        assert resp.status_code == 200, resp.text
        exp_id = resp.json()["experiment_id"]

        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "connected"
            events, final = _drain(ws)

        kinds = [e["kind"] for e in events]
        assert final["type"] == "done"
        assert "condition_start" in kinds
        assert "trial" in kinds
        assert "verdict" in kinds
        assert final["result"]["classification"]
        assert final["result"]["experiment_id"] == exp_id

    # And the completed result is retrievable over REST.
    with TestClient(app) as client:
        got = client.get(f"/experiments/{exp_id}")
        assert got.status_code == 200
        assert got.json()["experiment_id"] == exp_id


def test_stream_sequential_mode_forwards_evidence_events():
    with TestClient(app) as client:
        resp = client.post(
            "/experiments/stream",
            json={"command": _CMD, "max_rounds": 3, "target_profile": _profile()},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["mode"] == "sequential"
        exp_id = resp.json()["experiment_id"]

        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            ws.receive_json()
            events, final = _drain(ws)

    evidence = [e for e in events if e["kind"] == "evidence"]
    assert evidence, "sequential mode must stream evidence events"
    for ev in evidence:
        assert ev["condition"] in ("latency_only", "full_treatment")
        assert ev["e_value"] is not None
        assert ev["evidence_threshold"] > 1
        assert ev["pairs"] >= 1
        assert isinstance(ev["decisive"], bool)
    assert final["type"] == "done"
    assert all(c["method"] == "paired_e_value" for c in final["result"]["comparisons"])
    # A trial event never carries a p-value; evidence events carry the anytime p.
    assert all(e.get("p_value") is None for e in events if e["kind"] == "trial")


def test_late_subscriber_gets_replay_in_order():
    with TestClient(app) as client:
        exp_id = client.post(
            "/experiments/stream",
            json={"command": _CMD, "trials": 2, "mode": "batch", "target_profile": _profile()},
        ).json()["experiment_id"]

        # First subscriber runs the stream to completion.
        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            ws.receive_json()
            first, final = _drain(ws)
        assert final["type"] == "done"

        # A second subscriber connecting afterwards sees the identical sequence.
        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            assert ws.receive_json()["type"] == "connected"
            second, final = _drain(ws)
        assert final["type"] == "done"
        assert [e["kind"] for e in second] == [e["kind"] for e in first]
        assert [e.get("trial_index") for e in second] == [e.get("trial_index") for e in first]


def test_unknown_id_closes_with_4404():
    with TestClient(app) as client:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/experiment/exp-nope") as ws:
                ws.receive_json()
        assert excinfo.value.code == 4404
        with pytest.raises(WebSocketDisconnect) as excinfo:
            with client.websocket_connect("/ws/threshold/thr-nope") as ws:
                ws.receive_json()
        assert excinfo.value.code == 4404


def test_threshold_stream_emits_probes_then_done():
    with TestClient(app) as client:
        resp = client.post(
            "/threshold/stream",
            json={
                "command": _CMD,
                "parameter": "network.latency_ms",
                "low": 0,
                "high": 50,
                "max_trials": 6,
                "profile": _profile(),
            },
        )
        assert resp.status_code == 200, resp.text
        thr_id = resp.json()["threshold_id"]
        assert resp.json()["method"] == "bayes"

        with client.websocket_connect(f"/ws/threshold/{thr_id}") as ws:
            hello = ws.receive_json()
            assert hello["threshold_id"] == thr_id
            events, final = _drain(ws)

    probes = [e for e in events if e["kind"] == "search_probe"]
    assert probes
    assert all(e["param_value"] is not None for e in probes)
    assert final["type"] == "done"
    assert final["result"]["method"] == "probabilistic_bisection"
    assert final["result"]["outcome"] == "never_fails"


def test_cancel_running_experiment():
    slow = f'{sys.executable} -c "import time; time.sleep(0.3)"'
    with TestClient(app) as client:
        exp_id = client.post(
            "/experiments/stream",
            json={"command": slow, "max_rounds": 12, "target_profile": _profile(), "timeout_sec": 5},
        ).json()["experiment_id"]
        cancel = client.delete(f"/experiments/{exp_id}")
        assert cancel.status_code == 200
        assert cancel.json()["cancelled"] is True
        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            ws.receive_json()
            events, final = _drain(ws)
    assert final["type"] == "error"
    assert final.get("cancelled") is True
    assert len([e for e in events if e["kind"] == "trial"]) < 24


def test_stream_setup_error_is_422_before_any_trial():
    with TestClient(app) as client:
        resp = client.post(
            "/experiments/stream",
            json={"command": "definitely-not-a-binary-xyz", "target_profile": _profile()},
        )
        assert resp.status_code == 422
        assert "setup error" in resp.json()["detail"]


# --- manager unit tests: ordering under concurrency, bounds ---------------- #


@pytest.mark.asyncio
async def test_manager_late_subscriber_never_sees_reordered_events():
    manager = ConnectionManager(max_jobs=5)
    manager.bind_loop()
    manager.open_log("job")

    async def producer():
        for i in range(200):
            await manager.broadcast_event("job", {"type": "event", "seq": i})
            if i % 7 == 0:
                await asyncio.sleep(0)
        await manager.broadcast_event("job", {"type": "done", "seq": 200})

    task = asyncio.create_task(producer())
    await asyncio.sleep(0.001)  # let some events land before subscribing
    queue = await manager.subscribe("job")
    seen = []
    while True:
        item = await queue.get()
        if item is None:
            break
        seen.append(item["seq"])
    await task
    assert seen == list(range(201))


@pytest.mark.asyncio
async def test_manager_bounds_logs_and_trims_tails():
    manager = ConnectionManager(max_jobs=3)
    manager.bind_loop()
    evicted = []
    manager.on_evict(evicted.append)
    for i in range(5):
        manager.open_log(f"job-{i}")
    assert list(manager.event_log) == ["job-2", "job-3", "job-4"]
    assert evicted == ["job-0", "job-1"]
    assert await manager.subscribe("job-0") is None

    big = "x" * 10_000
    await manager.broadcast_event("job-4", {"type": "event", "kind": "trial", "stdout_tail": big})
    assert len(manager.event_log["job-4"][0]["stdout_tail"]) == 2048
