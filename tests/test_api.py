from fastapi.testclient import TestClient

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
    assert res.json() == {"status": "ok", "service": "morph-api"}


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


def test_experiments_endpoint():
    profile = make_test_profile()
    payload = {
        "command": "python3 -c \"print('exp ok')\"",
        "target_profile": profile.model_dump(),
        "trials": 2,
        "timeout_sec": 10.0,
    }
    res = client.post("/experiments", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "experiment_id" in data
    assert "summary" in data


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
