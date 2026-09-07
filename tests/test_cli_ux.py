"""CLI contract: --json purity, exit codes, no tracebacks, sequential/bayes modes.

``--json`` is tested through a real pipe (a subprocess with stdout captured
separately from stderr), because Typer's CliRunner merges the two streams by
default and a Rich console writes differently to a pipe than to a TTY.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from morph.cli.main import app
from tests.test_api import make_test_profile

runner = CliRunner()
_PY = sys.executable
_OK = f'{_PY} -c "print(1)"'


def _morph(*args: str, env: dict | None = None) -> subprocess.CompletedProcess:
    import os

    merged = {**os.environ, "MORPH_NO_NETWORK": "1", **(env or {})}
    return subprocess.run(
        [_PY, "-m", "morph.cli.main", *args], capture_output=True, text=True, timeout=120, env=merged
    )


def _only_json(proc: subprocess.CompletedProcess) -> dict:
    """stdout must parse as exactly one JSON document."""
    assert proc.stdout.strip(), f"empty stdout; stderr: {proc.stderr}"
    return json.loads(proc.stdout)


@pytest.fixture
def profile_file(tmp_path) -> Path:
    path = tmp_path / "target.json"
    path.write_text(make_test_profile().model_dump_json(), encoding="utf-8")
    return path


# --- global flags ------------------------------------------------------------ #


def test_version_flag():
    import morph

    res = runner.invoke(app, ["--version"])
    assert res.exit_code == 0
    assert morph.__version__ in res.output


def test_dash_h_is_help_everywhere():
    for cmd in ([], ["serve"], ["experiment"], ["threshold"], ["run"]):
        res = runner.invoke(app, [*cmd, "-h"])
        assert res.exit_code == 0, cmd
        assert "Usage" in res.output


def test_help_lists_new_commands_and_exit_codes():
    res = runner.invoke(app, ["--help"])
    for name in ("doctor", "demo", "minimize", "experiment", "threshold"):
        assert name in res.output
    assert "Exit codes" in res.output


# --- --json purity through a real pipe --------------------------------------- #


def test_run_json_is_pure_on_success_and_error_paths():
    ok = _morph("run", "--json", "-c", _OK)
    assert ok.returncode == 0
    assert _only_json(ok)["passed"] is True

    missing_project = _morph("run", "--json", "--project", "definitely-not-a-project")
    assert missing_project.returncode == 2
    assert _only_json(missing_project)["error"] == "no_project"
    assert "Error" in missing_project.stderr

    missing_profile = _morph("run", "--json", "-c", _OK, "--profile", "/nonexistent/profile.json")
    assert missing_profile.returncode == 2
    assert _only_json(missing_profile)["error"] == "profile_error"

    setup = _morph("run", "--json", "-c", "definitely-not-a-binary-xyz")
    assert setup.returncode == 2
    body = _only_json(setup)  # the RunResult itself, so a remote worker still gets a result
    assert body["passed"] is False
    assert body["exit_code"] == 127


def test_capture_json_and_plain_stdout_are_valid_json():
    plain = _morph("capture")
    assert plain.returncode == 0
    assert json.loads(plain.stdout)["os"]
    assert "Capturing" in plain.stderr  # status line on stderr, never stdout

    compact = _morph("capture", "--json")
    assert compact.returncode == 0
    assert len(compact.stdout.strip().splitlines()) == 1


def test_experiment_json_is_pure_and_sequential_by_default(profile_file):
    proc = _morph("experiment", "--json", "-c", _OK, "-p", str(profile_file), "--max-rounds", "3")
    assert proc.returncode == 0, proc.stderr
    body = _only_json(proc)
    assert body["classification"] == "no_effect"
    assert body["comparisons"]
    for cmp in body["comparisons"]:
        assert cmp["method"] == "paired_e_value"
        assert cmp["e_value"] is not None
        assert cmp["pairs"] == 3
    # Progress went to stderr, including evidence lines.
    assert "E =" in proc.stderr


def test_experiment_batch_mode_and_table(profile_file):
    res = runner.invoke(
        app, ["experiment", "-c", _OK, "-p", str(profile_file), "--mode", "batch", "-n", "2"]
    )
    assert res.exit_code == 0, res.output
    assert "Causal Isolation Results" in res.output
    assert "Verdict (batch mode)" in res.output
    assert "risk" in res.output

    seq = runner.invoke(app, ["experiment", "-c", _OK, "-p", str(profile_file), "--max-rounds", "2"])
    assert seq.exit_code == 0, seq.output
    assert "E-value" in seq.output
    assert "Verdict (sequential mode)" in seq.output


def test_experiment_rejects_bad_counts(profile_file):
    for args in (["-n", "0", "--mode", "batch"], ["--max-rounds", "0"], ["--alpha", "1"], ["--alpha", "0"]):
        res = runner.invoke(app, ["experiment", "-c", _OK, "-p", str(profile_file), *args])
        assert res.exit_code == 2, args


def test_threshold_json_bayes_and_bisect(profile_file):
    bayes = _morph(
        "threshold", "--json", "-c", _OK, "-p", str(profile_file),
        "--parameter", "network.latency_ms", "--low", "0", "--high", "100", "--max-trials", "6",
    )
    assert bayes.returncode == 3, bayes.stderr  # no boundary in range
    body = _only_json(bayes)
    assert body["method"] == "probabilistic_bisection"
    assert body["outcome"] == "never_fails"
    assert body["boundary_estimate"] is None
    assert body["probability_boundary_in_range"] < 0.5

    bisect = _morph(
        "threshold", "--json", "-c", _OK, "-p", str(profile_file), "--method", "bisect",
        "--parameter", "network.latency_ms", "--low", "0", "--high", "100", "-n", "1",
    )
    assert bisect.returncode == 3
    assert _only_json(bisect)["method"] == "bisection"


def test_threshold_finds_a_boundary_with_a_latency_sensitive_command(profile_file):
    # Fails whenever the requested latency is above 40 ms (read from the env
    # the proxy path exports), so a boundary genuinely lies inside [0, 100].
    cmd = (
        f'{_PY} -c "import os,sys; '
        "sys.exit(1 if float(os.environ.get('MORPH_NET_LATENCY_MS', 0)) > 40 else 0)\""
    )
    proc = _morph(
        "threshold", "--json", "-c", cmd, "-p", str(profile_file),
        "--parameter", "network.latency_ms", "--low", "0", "--high", "100", "--max-trials", "16",
    )
    assert proc.returncode == 0, proc.stderr
    body = _only_json(proc)
    assert body["outcome"] == "boundary_found"
    assert body["credible_low"] is not None and body["credible_high"] is not None
    assert body["credible_low"] <= body["boundary_estimate"] <= body["credible_high"]
    assert 20 <= body["boundary_estimate"] <= 60


def test_threshold_usage_errors_exit_2():
    bad_range = runner.invoke(
        app, ["threshold", "-c", _OK, "--parameter", "network.latency_ms", "--low", "10", "--high", "0"]
    )
    assert bad_range.exit_code == 2
    assert "must be greater" in bad_range.output

    bad_param = runner.invoke(app, ["threshold", "-c", _OK, "--parameter", "bogus.field"])
    assert bad_param.exit_code == 2
    assert "Traceback" not in bad_param.output


# --- setup errors and tracebacks --------------------------------------------- #


def test_setup_errors_exit_2_with_a_message_not_a_verdict(profile_file):
    res = runner.invoke(app, ["experiment", "-c", "definitely-not-a-binary-xyz", "-p", str(profile_file)])
    assert res.exit_code == 2, res.output
    assert "setup error" in res.output
    assert "Causal Isolation Results" not in res.output

    bad_cwd = runner.invoke(app, ["run", "-c", _OK, "--cwd", "/nonexistent-dir-xyz"])
    assert bad_cwd.exit_code == 2
    assert "setup error" in bad_cwd.output
    assert "Run Result" not in bad_cwd.output


def test_app_failure_exit_code_is_the_apps_code():
    res = runner.invoke(app, ["run", "-c", f'{_PY} -c "import sys; sys.exit(3)"'])
    assert res.exit_code == 3
    assert "FAIL" in res.output


def test_malformed_profile_and_missing_bundle_give_messages_not_tracebacks(tmp_path):
    not_a_profile = tmp_path / "nope.json"
    not_a_profile.write_text('{"hello": "world"}', encoding="utf-8")
    for args in (
        ["run", "-c", _OK, "-p", str(not_a_profile)],
        ["experiment", "-c", _OK, "-p", str(not_a_profile)],
        ["threshold", "-c", _OK, "-p", str(not_a_profile), "--parameter", "network.latency_ms"],
        ["run", "-c", _OK, "-p", "/nonexistent/profile.json"],
        ["replay", "/nonexistent/bundle"],
        ["export", "/nonexistent/bundle", "-o", str(tmp_path / "t.py")],
    ):
        res = runner.invoke(app, args)
        assert res.exit_code == 2, (args, res.output)
        assert "Traceback" not in res.output
        assert "Error" in res.output


def test_define_rejects_unknown_template_and_marks_requested(tmp_path):
    res = runner.invoke(app, ["define", "-t", "bogus", "-o", str(tmp_path / "x.json")])
    assert res.exit_code == 2
    assert not (tmp_path / "x.json").exists()

    out = tmp_path / "hl.json"
    res = runner.invoke(
        app, ["define", "-t", "high-latency", "-o", str(out), "--latency", "80", "--loss", "5"]
    )
    assert res.exit_code == 0
    data = json.loads(out.read_text())
    assert data["network"]["latency_ms"]["value"] == 80.0
    assert data["network"]["latency_ms"]["status"] == "requested"
    assert data["network"]["packet_loss_percent"]["value"] == 5.0


def test_save_rejects_traversal_ids(tmp_path):
    profile = tmp_path / "p.json"
    profile.write_text(make_test_profile().model_dump_json(), encoding="utf-8")
    res = runner.invoke(
        app, ["save", "--id", "../../evil", "-p", str(profile), "-c", "echo", "--dir", str(tmp_path / "b")]
    )
    assert res.exit_code == 2
    assert not (tmp_path / "evil").exists()
    assert not (tmp_path.parent / "evil").exists()


def test_projects_rm_missing_exits_1():
    res = runner.invoke(app, ["projects", "--rm", "definitely-not-a-project"])
    assert res.exit_code == 1


def test_run_cloud_without_profile_is_a_usage_error():
    res = runner.invoke(app, ["run", "-c", _OK, "--cloud"])
    assert res.exit_code == 2
    assert "--profile" in res.output


def test_child_output_is_not_interpreted_as_markup():
    res = runner.invoke(app, ["run", "-c", f'{_PY} -c "print(\'[bold]x[/] [/bogus]\')"'])
    assert res.exit_code == 0
    assert "[bold]x[/] [/bogus]" in res.output


# --- doctor / minimize / demo ---------------------------------------------- #


def test_doctor_runs_and_reports_json():
    proc = _morph("doctor", "--json", "--no-network")
    assert proc.returncode in (0, 1)
    body = _only_json(proc)
    names = {c["name"] for c in body["checks"]}
    assert {"python", "adapter", "privileges", "proxy self-check", "~/.morph", "worker"} <= names
    worker = next(c for c in body["checks"] if c["name"] == "worker")
    assert worker["status"] == "skip"  # MORPH_NO_NETWORK / no worker: never probed

    human = runner.invoke(app, ["doctor", "--no-network"])
    assert "morph doctor" in human.output
    assert "proxy self-check" in human.output


def test_minimize_finds_the_latency_condition(profile_file):
    cmd = (
        f'{_PY} -c "import os,sys; '
        "sys.exit(1 if float(os.environ.get('MORPH_NET_LATENCY_MS', 0)) > 0 else 0)\""
    )
    proc = _morph("minimize", "--json", "-c", cmd, "-p", str(profile_file), "--runs", "1")
    assert proc.returncode == 0, proc.stderr
    body = _only_json(proc)
    assert body["reproduced"] is True
    assert body["minimal"] == ["network.latency_ms"]
    assert body["oracle_calls"] >= 2

    not_reproduced = _morph("minimize", "--json", "-c", _OK, "-p", str(profile_file), "--runs", "1")
    assert not_reproduced.returncode == 1
    assert _only_json(not_reproduced)["reproduced"] is False


def test_demo_help_and_precondition():
    res = runner.invoke(app, ["demo", "--help"])
    assert res.exit_code == 0
    assert "pool_retry" in res.output
