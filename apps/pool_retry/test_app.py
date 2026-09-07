"""Self-check for Failure B, the interaction fixture.

Run: pytest apps/pool_retry/test_app.py            # contract tier (seconds)
     pytest apps/pool_retry/test_app.py -m slow    # the 2x2, 12 trials per leg

The whole value of this app is that it fails ONLY on the combination, so the
statistical tier asserts all four legs of the 2x2 plus the fix, not just that
it can fail. If a single variable alone starts failing, the interaction story
is gone and the app needs re-tuning (see README).

Conditions are injected for real by Morph's TCP proxy through the same
``MORPH_NET_*`` hand-off the runtime uses. The bounds are binomial-aware
(``apps/conftest.py``): a healthy fixture is rejected at most 1 % of the time.
"""

from __future__ import annotations

import pytest

from apps.conftest import failure_rate, max_failures, min_failures, run_app

APP = "pool_retry"
# The validated operating point (README): 120 ms RTT, 18 % loss.
LATENCY = {"MORPH_NET_LATENCY_MS": "120"}
LOSS = {"MORPH_NET_PACKET_LOSS_PCT": "18"}
BOTH = {**LATENCY, **LOSS}


# --------------------------------------------------------------- contract tier

def test_baseline_passes():
    code, payload, err = run_app(APP)
    assert code == 0 and payload["result"] == "pass", payload
    assert err == ""


def test_combination_fails():
    """Seeded so the proxy's loss pattern is a known failing one. Thread timing
    still varies, so two seeds are tried; the fixture is broken only if
    neither reproduces the cascade."""
    outcomes = []
    for seed in ("4", "5"):
        code, payload, err = run_app(APP, env={**BOTH, "MORPH_SEED": seed})
        assert err == "", f"unexpected stderr noise: {err[:300]}"
        outcomes.append((code, payload))
        if code == 1:
            assert payload["signal"] == "DeadlineExceeded"
            return
    pytest.fail(f"combination did not fail with either seed: {outcomes}")


def test_fixed_variant_survives_the_combination():
    code, payload, _ = run_app(APP, env={**BOTH, "MORPH_SEED": "4"}, fixed=True)
    assert code == 0, payload


def test_machine_mode_contract():
    code, payload, _ = run_app(APP, env=LATENCY)
    assert code in (0, 1)
    assert payload["result"] in ("pass", "fail")
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}


# ------------------------------------------------------------ statistical tier

TRIALS = 12


@pytest.mark.slow
def test_baseline_rate_under_5_percent():
    failures, invalid = failure_rate(APP, TRIALS)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.05), f"{failures}/{TRIALS}"


@pytest.mark.slow
def test_latency_alone_mostly_passes():
    """If this starts failing, the interaction claim collapses into 'latency did it'."""
    failures, invalid = failure_rate(APP, TRIALS, env=LATENCY)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.15), f"{failures}/{TRIALS}"


@pytest.mark.slow
def test_loss_alone_mostly_passes():
    """The sensitive leg: raising the loss rate breaks this one first."""
    failures, invalid = failure_rate(APP, TRIALS, env=LOSS)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.15), f"{failures}/{TRIALS}"


@pytest.mark.slow
def test_combination_fails_at_least_80_percent():
    failures, invalid = failure_rate(APP, TRIALS, env=BOTH)
    assert invalid == 0
    assert failures >= min_failures(TRIALS, 0.80), f"only {failures}/{TRIALS} failed"


@pytest.mark.slow
def test_fixed_variant_passes_at_least_90_percent():
    """Sizing the pool to the batch removes the queueing that causes the cascade."""
    failures, invalid = failure_rate(APP, TRIALS, env=BOTH, fixed=True)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.10), f"{failures}/{TRIALS}"
