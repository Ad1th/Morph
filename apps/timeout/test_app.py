"""Self-check for Failure A. Confirms the app still fails the way we think it does.

Run: pytest apps/timeout/test_app.py

These are fixture-integrity checks, not Morph's own tests: they verify the
engineered failure is still engineered correctly after anyone touches app.py.
The real network-shaping verification (tc netem / Clumsy / dnctl) is manual --
see this app's README. Here the condition is simulated by raising the server
delay, which exercises the same timeout code path deterministically on any OS.
"""

from __future__ import annotations

import json
import subprocess
import sys

TRIALS = 10


def _run(env_overrides: dict[str, str] | None = None, fixed: bool = False) -> tuple[int, dict]:
    import os

    env = dict(os.environ)
    env.update(env_overrides or {})
    cmd = [sys.executable, "-m", "apps.timeout", "test"]
    if fixed:
        cmd.append("--fixed")

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return proc.returncode, payload


def test_baseline_passes():
    """Baseline fail rate must stay under 5% or the experiment engine has no signal."""
    failures = sum(1 for _ in range(TRIALS) if _run()[0] != 0)
    assert failures / TRIALS < 0.05, f"baseline too flaky: {failures}/{TRIALS} failed"


def test_fails_under_latency():
    """With the response pushed past the deadline, the failure must be near-total."""
    slow = {"MORPH_A_RESP_DELAY_S": "0.38"}
    failures = sum(1 for _ in range(TRIALS) if _run(slow)[0] == 1)
    assert failures / TRIALS > 0.9, f"condition too weak: only {failures}/{TRIALS} failed"


def test_fixed_variant_survives_the_condition():
    """The one-line fix must pass under the exact condition that breaks the app."""
    slow = {"MORPH_A_RESP_DELAY_S": "0.38"}
    failures = sum(1 for _ in range(TRIALS) if _run(slow, fixed=True)[0] != 0)
    assert failures == 0, f"fixed variant still failing: {failures}/{TRIALS}"


def test_machine_mode_contract():
    """`test` must emit a parseable JSON result line with the agreed keys."""
    code, payload = _run({"MORPH_A_RESP_DELAY_S": "0.38"})
    assert code == 1
    assert payload["result"] == "fail"
    assert payload["signal"] == "TimeoutException"
    assert isinstance(payload["duration_ms"], int)
    assert payload["detail"]


def test_clean_stderr_on_failure():
    """Client-disconnect tracebacks must not leak: Morph reads stderr for the signal."""
    import os

    env = dict(os.environ)
    env["MORPH_A_RESP_DELAY_S"] = "0.38"
    proc = subprocess.run(
        [sys.executable, "-m", "apps.timeout", "test"],
        capture_output=True, text=True, env=env, timeout=30,
    )
    assert proc.stderr == "", f"unexpected stderr noise: {proc.stderr[:300]}"
