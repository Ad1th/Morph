"""Self-check for Failure F. Confirms the app still fails the way we think it does.

Run: pytest apps/tz_dst/test_app.py

Fully deterministic. The condition is injected the way every Morph adapter
injects it: ``TZ`` in the child's environment.
"""

from __future__ import annotations

import os

import pytest

from apps.conftest import run_app

APP = "tz_dst"
TARGET = {"TZ": "America/Sao_Paulo"}          # what apply_locale exports for the profile

posix_only = pytest.mark.skipif(os.name == "nt", reason="TZ handling needs tzset()")


# --------------------------------------------------------------- contract tier

@posix_only
def test_baseline_passes_with_tz_unset():
    """No TZ in the environment: the host zone. Passes unless the host itself
    switched clocks on 2018-11-04 (Sao Paulo, New York, ...)."""
    code, payload, err = run_app(APP)
    assert code in (0, 1), payload
    assert err == ""
    if code == 1:
        pytest.skip("host zone has a DST transition on the anchor night; use TZ=UTC")


@posix_only
def test_baseline_passes_under_utc():
    code, payload, _ = run_app(APP, env={"TZ": "UTC"})
    assert code == 0 and payload["result"] == "pass", payload


@posix_only
def test_fails_under_target_zone():
    code, payload, err = run_app(APP, env=TARGET)
    assert code == 1, payload
    assert payload["signal"] == "ScheduleDrift"
    assert "2018-11-05" in payload["detail"], "the midnight transition skips a whole day"
    assert err == ""


@posix_only
def test_fails_under_a_fall_back_zone_too():
    """The bug is not Sao-Paulo-specific; any transition that night triggers it."""
    code, payload, _ = run_app(APP, env={"TZ": "America/New_York"})
    assert code == 1 and payload["signal"] == "ScheduleDrift"


@posix_only
def test_no_dst_zone_passes():
    code, payload, _ = run_app(APP, env={"TZ": "Asia/Kolkata"})
    assert code == 0, payload


@posix_only
def test_explicit_tz_arg_matches_env():
    code_env, _, _ = run_app(APP, env=TARGET)
    code_arg, _, _ = run_app(APP, "--tz", "America/Sao_Paulo")
    assert code_env == code_arg == 1


@posix_only
def test_fixed_variant_survives_the_condition():
    code, payload, _ = run_app(APP, env=TARGET, fixed=True)
    assert code == 0 and payload["result"] == "pass", payload


@posix_only
def test_unknown_zone_is_an_invalid_trial():
    """libc turns an unknown TZ into UTC silently; that must be exit 2, never a
    PASS credited to a zone that was never applied."""
    code, payload, _ = run_app(APP, env={"TZ": "Nowhere/Bogus"})
    assert code == 2
    assert payload["signal"] == "TimezoneUnavailable"


@posix_only
def test_machine_mode_contract():
    code, payload, _ = run_app(APP, env=TARGET)
    assert code == 1
    assert payload["result"] == "fail"
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}


# ------------------------------------------------------------ statistical tier

@pytest.mark.slow
@posix_only
def test_deterministic_over_repeats():
    assert {run_app(APP, env={"TZ": "UTC"})[0] for _ in range(5)} == {0}
    assert {run_app(APP, env=TARGET)[0] for _ in range(5)} == {1}
