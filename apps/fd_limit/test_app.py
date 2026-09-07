"""Self-check for Failure E. Confirms the app still fails the way we think it does.

Run: pytest apps/fd_limit/test_app.py

The condition is applied exactly as Morph applies it: ``RLIMIT_NOFILE``
lowered in the child before exec. Here that is done with a tiny launcher
wrapper (``resource.setrlimit`` then ``runpy``), which is the same call the
telemetry collector's ``preexec_fn`` makes.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from apps.conftest import _LEAKY_VARS, failure_rate, max_failures, run_app

APP = "fd_limit"
LIMIT = 64          # the documented target; the profile in profiles/fd_limit.json
SAFE = 256          # a classic default `ulimit -n`; must still pass

_LAUNCH = (
    "import resource, runpy, sys; lim = int(sys.argv[1]); "
    "resource.setrlimit(resource.RLIMIT_NOFILE, (lim, lim)); "
    "sys.argv = ['apps.fd_limit', *sys.argv[2:]]; "
    "runpy.run_module('apps.fd_limit', run_name='__main__')"
)


def run_limited(limit: int, *args: str, fixed: bool = False) -> tuple[int, dict, str]:
    """Run the app under a lowered RLIMIT_NOFILE (POSIX only)."""
    env = {k: v for k, v in os.environ.items() if k not in _LEAKY_VARS}
    cmd = [sys.executable, "-c", _LAUNCH, str(limit), "test", *args]
    if fixed:
        cmd.append("--fixed")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
    lines = proc.stdout.strip().splitlines()
    return proc.returncode, (json.loads(lines[-1]) if lines else {}), proc.stderr


posix_only = pytest.mark.skipif(os.name == "nt", reason="RLIMIT_NOFILE is POSIX")


# --------------------------------------------------------------- contract tier

def test_baseline_passes():
    code, payload, err = run_app(APP)
    assert code == 0 and payload["result"] == "pass", payload
    assert err == ""


@posix_only
def test_passes_under_a_generous_limit():
    code, payload, _ = run_limited(SAFE)
    assert code == 0, payload


@posix_only
def test_fails_under_the_target_limit():
    code, payload, err = run_limited(LIMIT)
    assert code == 1, payload
    assert payload["signal"] == "EMFILE"
    assert err == "", f"unexpected stderr noise: {err[:300]}"


@posix_only
def test_fixed_variant_survives_the_condition():
    code, payload, _ = run_limited(LIMIT, fixed=True)
    assert code == 0 and payload["result"] == "pass", payload


@posix_only
def test_limit_too_low_to_run_is_an_invalid_trial():
    """Below MIN_FDS the app cannot even hold stdio, its listener and one
    connection: exit 2, never a failure blamed on the pool."""
    code, payload, _ = run_limited(8)
    assert code == 2 and payload["signal"] == "LimitTooLowToRun", payload


def test_machine_mode_contract():
    _code, payload, _ = run_app(APP)
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}
    assert isinstance(payload["duration_ms"], int)
    assert payload["detail"]


# ------------------------------------------------------------ statistical tier

TRIALS = 10


@pytest.mark.slow
def test_baseline_rate_under_5_percent():
    failures, invalid = failure_rate(APP, TRIALS)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.05)


@pytest.mark.slow
@posix_only
def test_deterministic_under_the_target_limit():
    codes = {run_limited(LIMIT)[0] for _ in range(TRIALS)}
    assert codes == {1}, codes
