"""Self-check for Failure A. Confirms the app still fails the way we think it does.

Run: pytest apps/timeout/test_app.py            # contract tier
     pytest apps/timeout/test_app.py -m slow    # statistical tier

The condition is injected the way Morph injects it on an unprivileged host:
``MORPH_NET_LATENCY_MS`` (an RTT) makes the app front its own server with
Morph's TCP proxy. ``MORPH_A_RESP_DELAY_S`` is kept as a deterministic fallback
that exercises the same deadline without any proxy.
"""

from __future__ import annotations

import pytest

from apps.conftest import failure_rate, max_failures, min_failures, run_app

APP = "timeout"
# Well past the measured flip point (~45 ms RTT, see README) so a single run
# is decisive; the threshold itself is a `slow` sweep below.
LATENCY = {"MORPH_NET_LATENCY_MS": "120"}
SLOW_SERVER = {"MORPH_A_RESP_DELAY_S": "0.38"}


# --------------------------------------------------------------- contract tier

def test_baseline_passes():
    code, payload, err = run_app(APP)
    assert code == 0 and payload["result"] == "pass", payload
    assert err == ""


def test_fails_under_injected_latency():
    """The proxy path Morph actually uses."""
    code, payload, err = run_app(APP, env=LATENCY)
    assert code == 1, payload
    assert payload["signal"] == "TimeoutException"
    assert err == "", f"unexpected stderr noise: {err[:300]}"


def test_fails_under_slow_server():
    """Deterministic fallback: no proxy, same deadline code path."""
    code, payload, _ = run_app(APP, env=SLOW_SERVER)
    assert code == 1 and payload["signal"] == "TimeoutException"


def test_fixed_variant_survives_the_condition():
    code, payload, _ = run_app(APP, env=LATENCY, fixed=True)
    assert code == 0, payload


def test_only_fails_via_deadline_under_loss():
    """Loss stalls the request; it must still surface as a timeout, never a
    protocol error (exit 2). Whether it passes depends on which chunks were
    lost, so only the *kind* of outcome is asserted here."""
    code, payload, _ = run_app(APP, env={"MORPH_NET_PACKET_LOSS_PCT": "40", "MORPH_SEED": "1"})
    assert code in (0, 1), payload
    if code == 1:
        assert payload["signal"] == "TimeoutException"


def test_machine_mode_contract():
    code, payload, _ = run_app(APP, env=SLOW_SERVER)
    assert code == 1
    assert payload["result"] == "fail"
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}
    assert isinstance(payload["duration_ms"], int)
    assert payload["detail"]


# ------------------------------------------------------------ statistical tier

TRIALS = 20


@pytest.mark.slow
def test_baseline_rate_under_5_percent():
    failures, invalid = failure_rate(APP, TRIALS)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.05), f"{failures}/{TRIALS} baseline failures"


@pytest.mark.slow
def test_condition_rate_over_90_percent():
    failures, invalid = failure_rate(APP, TRIALS, env=LATENCY)
    assert invalid == 0
    assert failures >= min_failures(TRIALS, 0.90), f"only {failures}/{TRIALS} failed"


@pytest.mark.slow
def test_fixed_rate_under_5_percent():
    failures, invalid = failure_rate(APP, TRIALS, env=LATENCY, fixed=True)
    assert invalid == 0
    assert failures <= max_failures(TRIALS, 0.05)


@pytest.mark.slow
@pytest.mark.parametrize("rtt_ms,expect", [(20, "pass"), (80, "fail")])
def test_threshold_lies_between(rtt_ms, expect):
    """The flip point is ~45 ms RTT; well either side of it the outcome is
    near-certain (5 trials, majority)."""
    failures, invalid = failure_rate(APP, 5, env={"MORPH_NET_LATENCY_MS": str(rtt_ms)})
    assert invalid == 0
    assert (failures >= 3) == (expect == "fail"), f"{failures}/5 failed at {rtt_ms} ms"
