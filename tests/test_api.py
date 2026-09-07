import sys

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from morph.api.app import app
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
from morph.schema.regression import RegressionArtifact

client = TestClient(app)

_PY = sys.executable


def make_test_profile():
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
        memory=MemoryInfo(
            total_mb=ProfileField(value=16384, status=FieldStatus.CAPTURED)
        ),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=50.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        ),
    )


def test_health_check():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "ok"
    assert body["service"] == "morph-api"
    assert body["version"]
    assert "running_jobs" in body


def test_version_and_v1_aliases():
    v = client.get("/version")
    assert v.status_code == 200
    assert v.json()["api"] == "v1"
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/parameters").status_code == 200
    assert client.get("/api/v1/platform").status_code == 200


def test_openapi_every_route_has_tag_and_summary():
    spec = client.get("/openapi.json").json()
    for path, methods in spec["paths"].items():
        for method, op in methods.items():
            assert op.get("tags"), f"{method} {path} has no tag"
            assert op.get("summary") or op.get("description"), f"{method} {path} undocumented"


def test_parameter_catalog_endpoint():
    from morph.schema.parameters import PARAMETER_CATALOG

    res = client.get("/parameters")
    assert res.status_code == 200
    data = res.json()
    assert set(data) == set(PARAMETER_CATALOG)
    assert data["cpu_cores"]["field_path"] == "cpu.cores"


def test_capture_and_reconcile_profiles():
    res = client.post("/profiles/capture")
    assert res.status_code == 200
    profile_data = res.json()
    assert "os" in profile_data
    assert "cpu" in profile_data

    reconcile_res = client.post("/profiles/reconcile", json=profile_data)
    assert reconcile_res.status_code == 200
    assert "network" in reconcile_res.json()


def test_run_endpoint():
    payload = {
        "command": "python3 -c \"print('api run test')\"",
        "timeout": 10.0,
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["passed"] is True
    assert data["exit_code"] == 0
    assert "api run test" in data["stdout"]


def test_run_endpoint_env_overrides_no_profile():
    payload = {
        "command": "python3 -c \"import os; print(os.environ.get('MORPH_API_TEST'))\"",
        "timeout": 10.0,
        "env_overrides": {"MORPH_API_TEST": "from-api"},
    }
    res = client.post("/run", json=payload)
    assert res.status_code == 200
    assert "from-api" in res.json()["stdout"]


def test_run_app_failure_is_200_but_setup_error_is_422():
    failing = client.post("/run", json={"command": f'{_PY} -c "import sys; sys.exit(3)"'})
    assert failing.status_code == 200
    assert failing.json()["passed"] is False
    assert failing.json()["exit_code"] == 3

    missing = client.post("/run", json={"command": "definitely-not-a-binary-xyz --flag"})
    assert missing.status_code == 422
    assert "setup error" in missing.json()["detail"]

    bad_cwd = client.post("/run", json={"command": f'{_PY} -c "print(1)"', "cwd": "/nonexistent-dir-xyz"})
    assert bad_cwd.status_code == 422
    assert "nonexistent-dir-xyz" in bad_cwd.json()["detail"]


def test_run_rejects_empty_command_and_bad_timeout():
    assert client.post("/run", json={"command": ""}).status_code == 422
    assert client.post("/run", json={"command": "   "}).status_code == 400
    assert client.post("/run", json={"command": "echo hi", "timeout": 0}).status_code == 422


def test_experiments_endpoint_batch_mode():
    profile = make_test_profile()
    payload = {
        "command": "python3 -c \"print('exp ok')\"",
        "target_profile": profile.model_dump(),
        "trials": 2,
        "timeout_sec": 10.0,
        "mode": "batch",
    }
    res = client.post("/experiments", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["experiment_id"].startswith("exp-")
    assert "summary" in data
    assert data["baseline"]["total_runs"] == 2
    labels = {c["condition_label"] for c in data["comparisons"]}
    assert "full_treatment" in labels
    assert "latency_only" in labels

    got = client.get(f"/experiments/{data['experiment_id']}")
    assert got.status_code == 200
    assert client.get("/experiments").status_code == 200
    assert any(e["experiment_id"] == data["experiment_id"] for e in client.get("/experiments").json())


def test_experiments_endpoint_sequential_mode_default():
    payload = {
        "command": f'{_PY} -c "print(1)"',
        "target_profile": make_test_profile().model_dump(),
        "max_rounds": 3,
        "timeout_sec": 10.0,
    }
    res = client.post("/experiments", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    for cmp in data["comparisons"]:
        assert cmp["method"] == "paired_e_value"
        assert cmp["e_value"] is not None
        assert cmp["pairs"] == 3
        assert cmp["stopped_early"] is False
    assert data["classification"] in ("no_effect", "application_internal")


def test_experiments_validation():
    profile = make_test_profile().model_dump()
    base = {"command": f'{_PY} -c "print(1)"', "target_profile": profile}
    assert client.post("/experiments", json={**base, "trials": 0, "mode": "batch"}).status_code == 422
    assert client.post("/experiments", json={**base, "trials": -2, "mode": "batch"}).status_code == 422
    assert client.post("/experiments", json={**base, "max_rounds": 0}).status_code == 422
    assert client.post("/experiments", json={**base, "alpha": 0}).status_code == 422
    assert client.post("/experiments", json={**base, "alpha": 1}).status_code == 422
    assert client.post("/experiments", json={**base, "timeout_sec": 0}).status_code == 422
    assert client.post("/experiments", json={**base, "mode": "bogus"}).status_code == 422
    # No target: nothing to isolate, refuse instead of comparing the command to itself.
    assert client.post("/experiments", json={"command": "echo hi"}).status_code == 422


def test_experiments_setup_error_is_422_not_a_verdict():
    payload = {
        "command": "definitely-not-a-binary-xyz",
        "target_profile": make_test_profile().model_dump(),
        "max_rounds": 2,
    }
    res = client.post("/experiments", json=payload)
    assert res.status_code == 422
    assert "setup error" in res.json()["detail"]

    stream = client.post("/experiments/stream", json=payload)
    assert stream.status_code == 422


def test_regressions_lifecycle(tmp_path, monkeypatch):
    import morph.regression.artifact
    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    profile = make_test_profile()
    artifact = RegressionArtifact(
        regression_id="api-reg-001",
        environment=profile,
        command="python3 -c \"print('ok')\"",
        expected_exit_code=0,
        expected_max_failure_rate=0.0,
    )

    create_res = client.post("/regressions", json=artifact.model_dump())
    assert create_res.status_code == 200

    list_res = client.get("/regressions")
    assert list_res.status_code == 200
    assert any(r["regression_id"] == "api-reg-001" for r in list_res.json())

    replay_res = client.post("/regressions/api-reg-001/replay", json={"trials": 1})
    assert replay_res.status_code == 200
    assert replay_res.json()["matches_expected"] is True

    assert client.post("/regressions/api-reg-001/replay", json={"trials": 0}).status_code == 422
    assert client.delete("/regressions/api-reg-001").status_code == 200
    assert client.delete("/regressions/api-reg-001").status_code == 404


def test_websocket_unknown_experiment_closes_4404():
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws/experiment/exp-does-not-exist") as websocket:
            websocket.receive_json()
    assert excinfo.value.code == 4404


def test_threshold_bayes_via_api_returns_full_result():
    res = client.post(
        "/threshold",
        json={
            "command": f'{_PY} -c "print(1)"',
            "parameter": "network.latency_ms",
            "low": 0,
            "high": 100,
            "max_trials": 6,
            "profile": make_test_profile().model_dump(),
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["method"] == "probabilistic_bisection"
    assert data["outcome"] == "never_fails"
    assert data["boundary_estimate"] is None
    assert data["probability_boundary_in_range"] < 0.5
    assert data["credible_mass"] == 0.9
    assert data["trials"] == 6
    assert data["dose_response"]
    assert data["posterior"]


def test_threshold_validation():
    base = {"command": "echo hi", "parameter": "network.latency_ms"}
    assert client.post("/threshold", json={**base, "low": 10, "high": 0}).status_code == 422
    assert client.post("/threshold", json={**base, "precision": 0}).status_code == 422
    assert client.post("/threshold", json={**base, "trials": 0}).status_code == 422
    assert client.post("/threshold", json={**base, "method": "guess"}).status_code == 422
    assert client.post("/threshold", json={**base, "parameter": "bogus.field"}).status_code == 400
    setup = client.post("/threshold", json={**base, "command": "no-such-binary-xyz", "max_trials": 2})
    assert setup.status_code == 422
    assert "setup error" in setup.json()["detail"]
