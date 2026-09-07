"""Self-check for Failure B, the interaction fixture.

Run: pytest apps/pool_retry/test_app.py

The whole value of this app is that it fails ONLY on the combination, so these
tests assert all four legs of the 2x2, not just that it can fail. If a single
variable alone starts failing, the interaction story is gone and the app needs
re-tuning (see README).

Conditions are injected for real by morph's user-space TCP proxy, which genuinely
delays and drops chunks. Confirming the OS-native path (tc netem) agrees is still
worth doing on the Pi.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

TRIALS = 8
# Real conditions, injected by morph's TCP proxy. Latency is per direction, so
# 120ms here is ~240ms round-trip. 120/18 is the validated operating point
# (see README): neither leg alone moves the rate, the pair pins it near 100%.
LATENCY = {"MORPH_B_PROXY_LATENCY_MS": "120"}
LOSS = {"MORPH_B_PROXY_LOSS_PCT": "18"}
BOTH = {**LATENCY, **LOSS}


def _rate(env_overrides: dict[str, str] | None = None, fixed: bool = False,
          trials: int = TRIALS) -> float:
    env = dict(os.environ)
    env.update(env_overrides or {})
    cmd = [sys.executable, "-m", "apps.pool_retry", "test"]
    if fixed:
        cmd.append("--fixed")

    failures = 0
    for _ in range(trials):
        proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=60)
        assert proc.returncode in (0, 1), f"setup error: {proc.stderr[:300]}"
        failures += proc.returncode == 1
    return failures / trials


@pytest.mark.slow
def test_baseline_passes():
    assert _rate() < 0.05


@pytest.mark.slow
def test_latency_alone_passes():
    """If this starts failing, the interaction claim collapses into 'latency did it'."""
    assert _rate(LATENCY) < 0.15


@pytest.mark.slow
def test_loss_alone_passes():
    """The sensitive leg -- raising the stall rate breaks this one first."""
    assert _rate(LOSS) < 0.15


@pytest.mark.slow
def test_combination_fails():
    """The flagship claim: only the combination breaches the deadline.

    The acceptance bar is >90%, but this asserts a looser >=80% because eight
    trials cannot tell 0.875 from 0.95: at a true rate of 0.95 there is still a
    ~34% chance of seeing 7/8, so asserting >0.9 here would fail a third of the
    time on a perfectly healthy fixture. The authoritative measurement is the
    20-trial run recorded in the README (19/20). This test guards against the
    interaction disappearing, not against a few percent of drift.
    """
    assert _rate(BOTH) >= 0.8


@pytest.mark.slow
def test_fixed_variant_survives_the_combination():
    """Sizing the pool to the batch removes the queueing that causes the cascade."""
    assert _rate(BOTH, fixed=True) < 0.05


def test_machine_mode_contract():
    """`test` must emit a parseable JSON result line with the agreed keys."""
    env = dict(os.environ)
    env.update(BOTH)
    proc = subprocess.run(
        [sys.executable, "-m", "apps.pool_retry", "test"],
        capture_output=True, text=True, env=env, timeout=60,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    assert payload["result"] in ("pass", "fail")
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}
    assert proc.stderr == "", f"unexpected stderr noise: {proc.stderr[:300]}"
