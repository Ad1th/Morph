import pytest
import json
from morph.schema import (
    FieldStatus,
    ProfileField,
    OSInfo,
    CPUInfo,
    MemoryInfo,
    LocaleInfo,
    FilesystemInfo,
    NetworkInfo,
    EnvironmentProfile,
    RunResult,
    TelemetryData,
    TrialBatch,
    ComparisonResult,
    ThresholdResult,
    ExperimentConfig,
    ExperimentResult,
    RegressionArtifact,
)


def sample_profile_dict():
    return {
        "version": "1.0",
        "os": {
            "family": {"value": "darwin", "status": "captured"},
            "version": {"value": "14.5", "status": "captured"},
        },
        "cpu": {
            "architecture": {"value": "arm64", "status": "captured"},
            "cores": {"value": 8, "status": "captured"},
            "logical_processors": {"value": 8, "status": "captured"},
            "clock_mhz": {"value": 3200, "status": "captured"},
        },
        "memory": {
            "total_mb": {"value": 16384, "status": "captured"},
        },
        "locale": {
            "locale": {"value": "en_US.UTF-8", "status": "captured"},
            "timezone": {"value": "America/New_York", "status": "captured"},
        },
        "filesystem": {
            "case_sensitive": {"value": False, "status": "captured"},
        },
        "network": {
            "latency_ms": {"value": 150.0, "status": "requested"},
            "packet_loss_percent": {"value": 2.5, "status": "requested"},
            "bandwidth_mbps": {"value": 10.0, "status": "approximated"},
        },
    }


def test_environment_profile_deserialization():
    data = sample_profile_dict()
    profile = EnvironmentProfile.model_validate(data)

    assert profile.version == "1.0"
    assert profile.os.family.value == "darwin"
    assert profile.os.family.status == FieldStatus.CAPTURED
    assert profile.cpu.cores.value == 8
    assert profile.network.latency_ms.value == 150.0
    assert profile.network.packet_loss_percent.status == FieldStatus.REQUESTED
    assert profile.network.bandwidth_mbps.status == FieldStatus.APPROXIMATED


def test_environment_profile_json_roundtrip():
    data = sample_profile_dict()
    profile = EnvironmentProfile.model_validate(data)
    json_str = profile.model_dump_json()
    reloaded = EnvironmentProfile.model_validate_json(json_str)

    assert reloaded.model_dump() == profile.model_dump()


def test_run_result_schema():
    run = RunResult(
        run_id="run-123",
        exit_code=0,
        stdout="Output text",
        stderr="",
        duration_ms=124.5,
        passed=True,
        timestamp="2026-09-06T12:00:00Z",
    )
    assert run.passed is True
    assert run.exit_code == 0
    assert run.error_type is None

    fail_run = RunResult(
        run_id="run-124",
        exit_code=1,
        stdout="",
        stderr="TimeoutExpired: call timed out",
        duration_ms=5000.0,
        passed=False,
        error_type="TimeoutExpired",
        error_message="call timed out",
        timestamp="2026-09-06T12:00:05Z",
    )
    assert fail_run.passed is False
    assert fail_run.error_type == "TimeoutExpired"


def test_experiment_schema():
    profile = EnvironmentProfile.model_validate(sample_profile_dict())
    b_run = RunResult(
        run_id="b-1", exit_code=0, stdout="", stderr="", duration_ms=10.0, passed=True, timestamp="now"
    )
    t_run = RunResult(
        run_id="t-1", exit_code=1, stdout="", stderr="err", duration_ms=20.0, passed=False, error_type="Err", timestamp="now"
    )

    batch_baseline = TrialBatch(
        condition_label="baseline",
        total_runs=1,
        failures=0,
        failure_rate=0.0,
        run_results=[b_run],
    )
    batch_treatment = TrialBatch(
        condition_label="latency_150ms",
        profile_overrides={"network.latency_ms": 150.0},
        total_runs=1,
        failures=1,
        failure_rate=1.0,
        run_results=[t_run],
    )

    comparison = ComparisonResult(
        baseline=batch_baseline,
        treatment=batch_treatment,
        p_value=0.01,
        is_significant=True,
        effect_label="significant_increase",
    )

    threshold = ThresholdResult(
        parameter="network.latency_ms",
        safe_value=50.0,
        failure_value=150.0,
        boundary_estimate=100.0,
        search_points=[{"value": 50.0, "passed": True}, {"value": 150.0, "passed": False}],
    )

    exp_result = ExperimentResult(
        experiment_id="exp-001",
        target_profile=profile,
        comparisons=[comparison],
        thresholds=[threshold],
        classification="environment_caused",
        strongest_condition="latency_150ms",
        summary="Latency caused checkout timeout",
    )

    assert exp_result.classification == "environment_caused"
    assert len(exp_result.comparisons) == 1
    assert exp_result.comparisons[0].is_significant is True


def test_regression_artifact_schema():
    profile = EnvironmentProfile.model_validate(sample_profile_dict())
    artifact = RegressionArtifact(
        regression_id="reg-001",
        environment=profile,
        command="python -m demo_apps.timeout_client",
        expected_exit_code=0,
        expected_max_failure_rate=0.05,
        failure_signature="TimeoutExpired",
        created_at="2026-09-06T12:00:00Z",
        metadata={"author": "Adith"},
    )

    dump = artifact.model_dump()
    assert dump["regression_id"] == "reg-001"
    assert dump["expected_exit_code"] == 0
