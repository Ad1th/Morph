"""Self-check for Failure C. Confirms the app still fails the way we think it does.

Run: pytest apps/race/test_app.py

The condition is applied two ways:

* ``MORPH_C_YIELD_EVERY`` (root-free, every OS): a deterministic preemption
  inside the race window. This is what the contract and statistical tiers use.
* a real cgroup CPU quota via ``systemd-run`` (Linux only, ``needs_linux``):
  skipped elsewhere, and skipped on Linux hosts where systemd-run cannot
  create a scope.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

import pytest

from apps.conftest import failure_rate, max_failures, min_failures, run_app

APP = "race"
THROTTLE = {"MORPH_C_YIELD_EVERY": "2"}     # ~50 % of iterations see a preemption
HARD = {"MORPH_C_YIELD_EVERY": "1"}


# --------------------------------------------------------------- contract tier

def test_baseline_passes():
    """A calm CPU must hide the race, or there is no baseline to compare against."""
    code, payload, err = run_app(APP)
    assert code == 0, payload
    assert payload["rate"] <= 0.05
    assert err == ""


def test_race_appears_under_yield_knob():
    code, payload, _ = run_app(APP, env=THROTTLE)
    assert code == 1 and payload["signal"] == "RaceDetected", payload
    assert payload["rate"] > 0.05


def test_fixed_variant_survives_the_condition():
    """The lock must hold under the exact condition that breaks the app."""
    code, payload, _ = run_app(APP, env=HARD, fixed=True)
    assert code == 0 and payload["rate"] == 0.0, payload


def test_it_is_the_same_code_under_both_conditions():
    """The environment-EXPOSED claim.

    Nothing about the application changes between baseline and treatment; only
    the environment does. This is what entitles Morph to say the CPU constraint
    exposed the bug rather than caused it.
    """
    baseline_code, baseline, _ = run_app(APP)
    throttled_code, throttled, _ = run_app(APP, env=THROTTLE)
    assert baseline_code == 0 and throttled_code == 1
    assert baseline["rate"] < throttled["rate"]


def test_machine_mode_contract():
    code, payload, _ = run_app(APP, env=THROTTLE)
    assert code == 1
    assert payload["result"] == "fail"
    assert payload["signal"] == "RaceDetected"
    assert isinstance(payload["duration_ms"], int)
    assert payload["detail"]


def test_run_is_fast_enough_for_batching():
    """The engine runs 100+ trials per condition; a slow app makes that unusable."""
    _, payload, _ = run_app(APP)
    assert payload["duration_ms"] < 1500, (
        f"{payload['duration_ms']}ms per run is too slow; lower MORPH_C_ITERS")


# ------------------------------------------------------------ statistical tier

TRIALS = 10


@pytest.mark.slow
def test_baseline_rate_under_5_percent():
    failures, invalid = failure_rate(APP, TRIALS)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.05)


@pytest.mark.slow
def test_yield_knob_fails_at_least_half_the_runs():
    failures, invalid = failure_rate(APP, TRIALS, env=THROTTLE)
    assert invalid == 0
    assert failures >= min_failures(TRIALS, 0.50), f"only {failures}/{TRIALS} failed"


@pytest.mark.slow
def test_yield_knob_rate_reads_as_a_race():
    """With N=2 roughly half the iterations are preempted: the double-call
    rate should sit in a band that reads as a race, not "always broken"."""
    rates = [run_app(APP, env=THROTTLE)[1]["rate"] for _ in range(5)]
    mean = sum(rates) / len(rates)
    assert 0.2 <= mean <= 0.8, rates


# ------------------------------------------------------------ real cgroup path

@pytest.mark.needs_linux
@pytest.mark.slow
def test_real_cpu_quota_exposes_the_race():
    """A real cgroup v2 quota via systemd-run. Skips if scopes cannot be created."""
    if shutil.which("systemd-run") is None:
        pytest.skip("systemd-run not installed")
    cmd = ["systemd-run", "--user", "--scope", "--quiet", "-p", "CPUQuota=10%",
           sys.executable, "-m", "apps.race", "test"]
    failures = 0
    for _ in range(5):
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode not in (0, 1):
            pytest.skip(f"systemd-run could not create a scope: {proc.stderr[:200]}")
        failures += proc.returncode == 1
    assert failures >= 3, f"real quota exposed the race in only {failures}/5 runs"
