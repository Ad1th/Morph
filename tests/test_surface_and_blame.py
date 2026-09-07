"""Tests for 2D Failure Surface Heatmap, Differential Blame, and Invariant Exporter."""

from pathlib import Path

from fastapi.testclient import TestClient

import morph
from morph.api.app import app
from morph.engine.blame import analyze_differential_blame
from morph.engine.exporter import generate_invariant_test_code
from morph.engine.surface import compute_failure_surface
from morph.schema.surface import SurfaceRequest

client = TestClient(app)
REPO_ROOT = Path(morph.__file__).resolve().parent.parent


def test_morph_environment_context_manager():
    import os
    assert "MORPH_LATENCY_MS" not in os.environ

    with morph.environment(latency_ms=120, packet_loss=0.02):
        assert os.environ["MORPH_LATENCY_MS"] == "120"
        assert os.environ["MORPH_PACKET_LOSS"] == "2.0"

    assert "MORPH_LATENCY_MS" not in os.environ
    assert "MORPH_PACKET_LOSS" not in os.environ


def test_differential_blame_analysis():
    pass_out = "[timeout] PASS in 204ms (timeout=250ms, signal=None)"
    fail_out = (
        "[timeout] FAIL in 255ms (timeout=250ms, signal=TimeoutException)\n"
        "  detail: deadline 250ms exceeded"
    )

    blame = analyze_differential_blame(
        pass_output=pass_out,
        fail_output=fail_out,
        pass_param_label="170ms",
        fail_param_label="185ms",
        project_dir=REPO_ROOT / "apps" / "timeout",
    )

    assert blame.culpable_file in ("app.py", "api_client.py")
    assert blame.pass_trace is not None
    assert blame.fail_trace is not None
    assert blame.pass_trace.run_type == "PASS"
    assert blame.fail_trace.run_type == "FAIL"
    assert "TimeoutException" in blame.fail_trace.status_or_exception
    assert "170ms" in blame.pass_trace.summary_line
    assert "185ms" in blame.fail_trace.summary_line


def test_invariant_test_exporter():
    code = generate_invariant_test_code(
        project_name="checkout-service",
        command="py -3 -m apps.timeout test",
        safe_latency_ms=160.0,
        safe_packet_loss=0.01,
        boundary_estimate=180.0,
    )
    assert "test_checkout_service_environment_tolerance" in code
    assert "with morph.environment(" in code
    assert "latency_ms=160.0" in code
    assert "packet_loss=0.01" in code


def test_surface_2d_heatmap_computation():
    import sys

    req = SurfaceRequest(
        project_path=str(REPO_ROOT / "apps" / "timeout"),
        # `py -3` is a Windows-only launcher; use the running interpreter so the
        # surface actually executes the app on macOS / Linux / CI.
        command=f"{sys.executable} -m apps.timeout test",
        param_x="network.latency_ms",
        param_y="network.packet_loss_percent",
        x_values=[10.0, 100.0],
        y_values=[0.0, 2.0],
        runs_per_point=1,
    )
    result = compute_failure_surface(req, repo_root=REPO_ROOT)
    assert result.total_points == 4
    assert len(result.grid) == 2
    assert len(result.grid[0]) == 2
    assert result.passing_count >= 1
    assert result.failing_count >= 1


def test_surface_api_endpoints():
    res_surf = client.post(
        "/surface",
        json={
            "project_path": "apps/timeout",
            "command": "py -3 -m apps.timeout test",
            "param_x": "network.latency_ms",
            "param_y": "network.packet_loss_percent",
            "x_values": [10.0, 120.0],
            "y_values": [0.0, 1.0],
        },
    )
    assert res_surf.status_code == 200
    surf_data = res_surf.json()
    assert surf_data["total_points"] == 4
    assert "grid" in surf_data

    res_blame = client.post(
        "/blame",
        json={
            "pass_output": "HTTP 200 (duration: 172ms)",
            "fail_output": "TimeoutException (configured timeout: 180ms)",
            "pass_param_label": "170ms",
            "fail_param_label": "185ms",
        },
    )
    assert res_blame.status_code == 200
    blame_data = res_blame.json()
    assert blame_data["pass_trace"]["run_type"] == "PASS"
    assert blame_data["fail_trace"]["run_type"] == "FAIL"

    res_export = client.post(
        "/export/invariant",
        json={
            "project_name": "timeout",
            "command": "py -3 -m apps.timeout test",
            "safe_latency_ms": 160.0,
            "safe_packet_loss": 0.01,
            "param_name": "network.latency_ms",
            "boundary_estimate": 180.0,
        },
    )
    assert res_export.status_code == 200
    exp_data = res_export.json()
    assert exp_data["filename"] == "test_morph_invariant.py"
    assert "test_timeout_environment_tolerance" in exp_data["code"]
