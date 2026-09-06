import json
from pathlib import Path
import pytest

from morph.regression import (
    delete_regression,
    export_ci_test,
    list_regressions,
    load_regression,
    replay_regression,
    save_regression,
)
from morph.runtime.controller import RuntimeController
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


def make_sample_artifact(regression_id="test-checkout-001"):
    profile = EnvironmentProfile(
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
            timezone=ProfileField(value="America/New_York", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=180.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=2.0, status=FieldStatus.REQUESTED),
        ),
    )
    return RegressionArtifact(
        regression_id=regression_id,
        environment=profile,
        command="python3 -c \"print('checkout ok')\"",
        expected_exit_code=0,
        expected_max_failure_rate=0.0,
        failure_signature="LockLostException",
        created_at="2026-09-06T12:00:00Z",
        metadata={"author": "Adith", "scenario": "checkout_latency"},
    )


def test_save_and_load_regression(tmp_path):
    artifact = make_sample_artifact()
    saved_path = save_regression(artifact, base_dir=tmp_path)

    assert saved_path.is_dir()
    assert (saved_path / "environment.json").exists()
    assert (saved_path / "command.json").exists()
    assert (saved_path / "expected.json").exists()
    assert (saved_path / "metadata.json").exists()

    loaded = load_regression(saved_path)
    assert loaded.regression_id == artifact.regression_id
    assert loaded.command == artifact.command
    assert loaded.expected_exit_code == 0
    assert loaded.environment.network.latency_ms.value == 180.0


def test_list_and_delete_regressions(tmp_path):
    art1 = make_sample_artifact("reg-001")
    art2 = make_sample_artifact("reg-002")

    save_regression(art1, base_dir=tmp_path)
    save_regression(art2, base_dir=tmp_path)

    all_regs = list_regressions(base_dir=tmp_path)
    assert len(all_regs) == 2
    ids = {r.regression_id for r in all_regs}
    assert "reg-001" in ids
    assert "reg-002" in ids

    deleted = delete_regression("reg-001", base_dir=tmp_path)
    assert deleted is True
    assert len(list_regressions(base_dir=tmp_path)) == 1


def test_replay_regression_success(tmp_path):
    artifact = make_sample_artifact()
    save_regression(artifact, base_dir=tmp_path)

    result = replay_regression(artifact, trials=2)
    assert result.passed is True
    assert result.matches_expected is True
    assert result.failure_rate == 0.0
    assert len(result.runs) == 2
    assert "checkout ok" in result.runs[0].stdout


def test_replay_regression_failure(tmp_path):
    artifact = make_sample_artifact("fail-reg")
    artifact.command = "python3 -c \"raise RuntimeError('timeout')\""
    save_regression(artifact, base_dir=tmp_path)

    result = replay_regression(artifact, trials=1)
    assert result.passed is False
    assert result.matches_expected is False
    assert result.failure_rate == 1.0


def test_export_ci_test(tmp_path):
    artifact = make_sample_artifact()
    out_file = tmp_path / "test_morph_invariant.py"

    exported = export_ci_test(artifact, output_path=out_file)
    assert exported.exists()
    content = exported.read_text()
    assert "def test_morph_test_checkout_001_environment_invariant" in content
    assert "replay_regression" in content
