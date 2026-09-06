"""Self-check for Failure C. Confirms the app still fails the way we think it does.

Run: pytest apps/race/test_app.py

The condition here is simulated with MORPH_C_SWITCH_INTERVAL, because this
machine has no cgroups. That verifies the race and the fix, NOT that a real
cgroup quota exposes it -- that has to be measured on the Pi. See the README.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

TRIALS = 5
THROTTLE = {"MORPH_C_SWITCH_INTERVAL": "0.0005"}


def _run(env_overrides: dict[str, str] | None = None, fixed: bool = False) -> tuple[int, dict]:
    env = dict(os.environ)
    env.update(env_overrides or {})
    cmd = [sys.executable, "-m", "apps.race", "test"]
    if fixed:
        cmd.append("--fixed")

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return proc.returncode, payload


def test_baseline_passes():
    """A calm CPU must hide the race, or there is no baseline to compare against."""
    failures = sum(1 for _ in range(TRIALS) if _run()[0] != 0)
    assert failures / TRIALS < 0.05, f"baseline too flaky: {failures}/{TRIALS} failed"


def test_race_appears_under_constraint():
    """Frequent preemption must expose the race at the doc's 30-60% rate."""
    rates = [_run(THROTTLE)[1]["rate"] for _ in range(TRIALS)]
    assert all(r > 0.05 for r in rates), f"race did not appear: {rates}"
    assert sum(rates) / len(rates) < 0.9, (
        f"rate suspiciously total ({rates}) -- window may be too wide to read as a race")


def test_fixed_variant_survives_the_condition():
    """The lock must hold under the exact condition that breaks the app."""
    for _ in range(TRIALS):
        code, payload = _run(THROTTLE, fixed=True)
        assert code == 0 and payload["rate"] == 0.0, f"fixed variant raced: {payload}"


def test_it_is_the_same_code_under_both_conditions():
    """The environment-EXPOSED claim.

    Nothing about the application changes between baseline and treatment -- only
    the environment does. This is what entitles Morph to say the CPU constraint
    exposed the bug rather than caused it.
    """
    baseline_code, baseline = _run()
    throttled_code, throttled = _run(THROTTLE)
    assert baseline_code == 0 and throttled_code == 1
    assert baseline["rate"] == 0.0 < throttled["rate"]


def test_machine_mode_contract():
    """`test` must emit a parseable JSON result line with the agreed keys."""
    code, payload = _run(THROTTLE)
    assert code == 1
    assert payload["result"] == "fail"
    assert payload["signal"] == "RaceDetected"
    assert isinstance(payload["duration_ms"], int)
    assert payload["detail"]


def test_run_is_fast_enough_for_batching():
    """The engine runs 100+ trials per condition; a slow app makes that unusable."""
    _, payload = _run()
    assert payload["duration_ms"] < 1500, (
        f"{payload['duration_ms']}ms per run is too slow -- lower MORPH_C_ITERS")
