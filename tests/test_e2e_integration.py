"""End-to-End integration test suite for Morph Phase 6.

Validates the full loop:
1. Environment capture and status reconciliation.
2. Controlled command execution and telemetry collection via RuntimeController.
3. Automated causal isolation experiment execution.
4. Flight recorder regression bundle persistence (.morph/regressions/<id>).
5. Regression bundle replay and invariant verification.
6. CI test file export and execution via pytest.
7. Full FastAPI REST API lifecycle.
8. Full Typer CLI workflow.
"""

from __future__ import annotations

import subprocess
import sys

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from morph.api.app import app
from morph.cli.main import app as cli_app
from morph.engine.experiment import run_experiment
from morph.profiler.capture import capture_environment
from morph.regression import (
    export_ci_test,
    list_regressions,
    load_regression,
    replay_regression,
    save_regression,
)
from morph.runtime.controller import RuntimeController, reconcile_profile_statuses
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


def make_sample_profile() -> EnvironmentProfile:
    """Construct a clean, valid sample EnvironmentProfile."""
    return EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value=sys.platform, status=FieldStatus.CAPTURED),
            version=ProfileField(value="1.0.0", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="x86_64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=4, status=FieldStatus.CAPTURED),
            logical_processors=ProfileField(value=4, status=FieldStatus.CAPTURED),
        ),
        memory=MemoryInfo(
            total_mb=ProfileField(value=8192, status=FieldStatus.CAPTURED),
            available_mb=ProfileField(value=4096, status=FieldStatus.CAPTURED),
        ),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=20.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        ),
    )


def test_e2e_environment_capture_and_reconciliation():
    """1. Test capturing the host environment and reconciling field statuses."""
    captured = capture_environment()
    assert captured.os is not None
    assert captured.os.family.value is not None
    assert captured.cpu is not None
    assert captured.memory is not None

    sample = make_sample_profile()
    reconciled = reconcile_profile_statuses(sample)
    expected_statuses = (FieldStatus.REPRODUCED, FieldStatus.APPROXIMATED, FieldStatus.UNAVAILABLE)
    assert reconciled.os.family.status in expected_statuses
    assert reconciled.network.latency_ms.status in expected_statuses


def test_e2e_runtime_controller_execution():
    """2. Test running a process under RuntimeController with telemetry."""
    controller = RuntimeController(force_proxy=False)
    profile = make_sample_profile()

    # Successful command run
    result_pass = controller.run(
        profile=profile,
        command=f"{sys.executable} -c \"print('e2e_pass')\"",
        timeout=10.0,
    )
    assert result_pass.passed is True
    assert result_pass.exit_code == 0
    assert "e2e_pass" in result_pass.stdout
    assert result_pass.duration_ms > 0
    assert result_pass.peak_memory_mb >= 0

    # Failing command run with telemetry error parsing
    result_fail = controller.run(
        profile=profile,
        command=f"{sys.executable} -c \"raise ValueError('e2e_deliberate_error')\"",
        timeout=10.0,
    )
    assert result_fail.passed is False
    assert result_fail.exit_code != 0
    assert result_fail.error_type == "ValueError"


def test_e2e_causal_isolation_experiment():
    """3. Test running an automated causal isolation experiment on candidate treatments."""
    def baseline_fn() -> bool:
        return True

    candidates = {
        "candidate_a": lambda: True,
        "candidate_b": lambda: False,
        "candidate_c": lambda: True,
    }


    experiment_result = run_experiment(
        baseline_run_fn=baseline_fn,
        candidates=candidates,
        n=5,
    )

    assert experiment_result.baseline.failure_rate == 0.0
    assert experiment_result.classification == "environment_caused"
    assert experiment_result.strongest_condition == "candidate_b"
    assert len(experiment_result.comparisons) == 3


def test_e2e_flight_recorder_full_lifecycle(tmp_path, monkeypatch):
    """4. Test saving, loading, replaying, exporting, and running CI tests from a regression bundle."""
    import morph.regression.artifact
    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    profile = make_sample_profile()
    artifact = RegressionArtifact(
        regression_id="e2e-reg-test-01",
        environment=profile,
        command=f"{sys.executable} -c \"print('invariant_pass')\"",
        expected_exit_code=0,
        expected_max_failure_rate=0.0,
        metadata={"author": "Adith", "phase": "6"},
    )

    # Save bundle
    saved_path = save_regression(artifact, base_dir=tmp_path)
    assert saved_path.exists()
    assert (saved_path / "environment.json").exists()
    assert (saved_path / "command.json").exists()
    assert (saved_path / "expected.json").exists()
    assert (saved_path / "metadata.json").exists()

    # Load bundle
    loaded = load_regression("e2e-reg-test-01", base_dir=tmp_path)
    assert loaded.regression_id == "e2e-reg-test-01"
    assert loaded.command == artifact.command

    # List bundles
    all_bundles = list_regressions(base_dir=tmp_path)
    assert any(b.regression_id == "e2e-reg-test-01" for b in all_bundles)

    # Replay bundle
    replay_res = replay_regression(saved_path, trials=2, timeout=10.0)
    assert replay_res.matches_expected is True
    assert replay_res.failures == 0
    assert replay_res.failure_rate == 0.0

    # Export CI test file
    ci_export_path = tmp_path / "test_ci_invariant.py"
    export_ci_test(saved_path, output_path=ci_export_path)
    assert ci_export_path.exists()

    # Run the exported CI test file via pytest in a subprocess
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", str(ci_export_path)],
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, f"Exported CI test failed with output:\n{proc.stdout}\n{proc.stderr}"


def test_e2e_fastapi_rest_api_workflow(tmp_path, monkeypatch):
    """5. Test the complete REST API workflow via FastAPI TestClient."""
    import morph.regression.artifact
    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    client = TestClient(app)

    # 5.1 Health Check
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    # 5.2 Capture Profile
    cap_res = client.post("/profiles/capture")
    assert cap_res.status_code == 200
    profile_data = cap_res.json()

    # 5.3 Reconcile Profile
    rec_res = client.post("/profiles/reconcile", json=profile_data)
    assert rec_res.status_code == 200

    # 5.4 Execute Run
    run_payload = {
        "command": f"{sys.executable} -c \"print('api_e2e_ok')\"",
        "timeout": 10.0,
    }
    run_res = client.post("/run", json=run_payload)
    assert run_res.status_code == 200
    assert run_res.json()["passed"] is True

    # 5.5 Create Experiment
    exp_payload = {
        "command": f"{sys.executable} -c \"print('exp_e2e_ok')\"",
        "target_profile": profile_data,
        "trials": 1,
        "timeout_sec": 10.0,
    }
    exp_res = client.post("/experiments", json=exp_payload)
    assert exp_res.status_code == 200
    exp_id = exp_res.json()["experiment_id"]

    # 5.6 Get Experiment
    exp_fetch = client.get(f"/experiments/{exp_id}")
    assert exp_fetch.status_code == 200

    # 5.7 Save Regression
    reg_artifact = {
        "regression_id": "api-e2e-reg-01",
        "environment": profile_data,
        "command": f"{sys.executable} -c \"print('api_replay_ok')\"",
        "expected_exit_code": 0,
        "expected_max_failure_rate": 0.0,
    }
    reg_create = client.post("/regressions", json=reg_artifact)
    assert reg_create.status_code == 200

    # 5.8 Replay Regression
    reg_replay = client.post("/regressions/api-e2e-reg-01/replay", json={"trials": 1})
    assert reg_replay.status_code == 200
    assert reg_replay.json()["matches_expected"] is True


def test_e2e_typer_cli_workflow(tmp_path, monkeypatch):
    """6. Test the complete CLI interface workflow via CliRunner."""
    import morph.regression.artifact
    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    runner = CliRunner()

    # 6.1 CLI Capture
    cap_file = tmp_path / "cli_captured.json"
    res_cap = runner.invoke(cli_app, ["capture", "--output", str(cap_file)])
    assert res_cap.exit_code == 0
    assert cap_file.exists()

    # 6.2 CLI Define Template
    tpl_file = tmp_path / "cli_template.json"
    res_tpl = runner.invoke(cli_app, ["define", "--output", str(tpl_file), "--template", "high-latency"])
    assert res_tpl.exit_code == 0
    assert tpl_file.exists()

    # 6.3 CLI Run Command
    res_run = runner.invoke(cli_app, ["run", "--command", f"{sys.executable} -c \"print('cli_run_pass')\""])
    assert res_run.exit_code == 0
    assert "cli_run_pass" in res_run.stdout

    # 6.4 CLI Regression Setup, Replay, and Export
    profile = make_sample_profile()
    artifact = RegressionArtifact(
        regression_id="cli-e2e-reg-01",
        environment=profile,
        command=f"{sys.executable} -c \"print('cli_replay_pass')\"",
        expected_exit_code=0,
    )
    saved_path = save_regression(artifact, base_dir=tmp_path)

    res_replay = runner.invoke(cli_app, ["replay", str(saved_path), "--trials", "1"])
    assert res_replay.exit_code == 0
    assert "COMPLIANT" in res_replay.stdout

    ci_file = tmp_path / "cli_exported_ci.py"
    res_export = runner.invoke(cli_app, ["export", str(saved_path), "--output", str(ci_file)])
    assert res_export.exit_code == 0
    assert ci_file.exists()
