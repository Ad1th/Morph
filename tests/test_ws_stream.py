"""The streaming experiment endpoint + its progress WebSocket.

`POST /experiments/stream` runs the engine in a worker thread and forwards every
`TrialEvent` to `/ws/experiment/{id}`, finishing with a `done` (or `error`)
frame. A subscriber that connects after the run started still gets the full
history replayed from the manager's per-experiment log.
"""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from morph.api.app import app

_CMD = f'{sys.executable} -c "print(1)"'


def _drain(ws) -> tuple[list[str], dict]:
    kinds: list[str] = []
    while True:
        msg = ws.receive_json()
        if msg.get("type") == "event":
            kinds.append(msg["kind"])
        elif msg.get("type") in ("done", "error"):
            return kinds, msg


def test_stream_emits_events_then_done():
    with TestClient(app) as client:
        resp = client.post("/experiments/stream", json={"command": _CMD, "trials": 3})
        assert resp.status_code == 200
        exp_id = resp.json()["experiment_id"]

        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            hello = ws.receive_json()
            assert hello["type"] == "connected"
            kinds, final = _drain(ws)

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


def test_late_subscriber_gets_replay():
    with TestClient(app) as client:
        exp_id = client.post(
            "/experiments/stream", json={"command": _CMD, "trials": 2}
        ).json()["experiment_id"]

        # First subscriber runs the stream to completion.
        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            ws.receive_json()
            _, final = _drain(ws)
        assert final["type"] == "done"

        # A second subscriber connecting afterwards still sees the whole run.
        with client.websocket_connect(f"/ws/experiment/{exp_id}") as ws:
            assert ws.receive_json()["type"] == "connected"
            kinds, final = _drain(ws)
        assert final["type"] == "done"
        assert "trial" in kinds
