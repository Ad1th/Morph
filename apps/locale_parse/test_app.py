"""Self-check for Failure D. Confirms the app still fails the way we think it does.

Run: pytest apps/locale_parse/test_app.py

Fully deterministic, so the acceptance bar is absolute: 0 % baseline failures,
100 % under condition. The `slow` tier here is a formality (5 repeats each).

The condition is injected the way every Morph adapter injects it: LC_ALL and
LANG in the child's environment. Tests needing a generated locale skip when
that locale is missing (GitHub's ubuntu image ships only C and en_US).
"""

from __future__ import annotations

import pytest

from apps.conftest import locale_available, run_app
from apps.locale_parse import app as locale_app

APP = "locale_parse"
TARGET = {"LC_ALL": "de_DE.UTF-8", "LANG": "de_DE.UTF-8"}   # what the adapter exports

needs_de = pytest.mark.skipif(
    not locale_available("de_DE", ","), reason="de_DE.UTF-8 is not generated on this host"
)


# --------------------------------------------------------------- contract tier

def test_baseline_passes_with_no_locale_env():
    """A plain shell (C.UTF-8 / unset): the developer's machine. Must pass."""
    code, payload, err = run_app(APP)
    assert code == 0 and payload["result"] == "pass", payload
    assert err == ""


@needs_de
def test_fails_under_target_locale_env():
    """LC_ALL/LANG=de_DE.UTF-8, exactly what `apply_locale` exports."""
    code, payload, _ = run_app(APP, env=TARGET)
    assert code == 1, payload
    assert payload["signal"] == "LocaleParseMismatch"
    assert "15.0" in payload["detail"], "the point is silent 10x corruption, not a crash"


@needs_de
def test_fails_under_explicit_locale_arg():
    """--locale is the Windows path (the CRT ignores LC_ALL)."""
    code, payload, _ = run_app(APP, "--locale", "de_DE")
    assert code == 1 and payload["signal"] == "LocaleParseMismatch"


@needs_de
def test_fixed_variant_survives_the_condition():
    code, payload, _ = run_app(APP, env=TARGET, fixed=True)
    assert code == 0 and payload["result"] == "pass", payload


def test_period_decimal_locales_pass():
    """en_US and en_IN share the developer's convention: no failure there."""
    for name in ("en_US", "en_IN"):
        if not locale_available(name, "."):
            continue
        code, payload, _ = run_app(APP, env={"LC_ALL": f"{name}.UTF-8", "LANG": f"{name}.UTF-8"})
        assert code == 0, (name, payload)


def test_unregistered_explicit_locale_is_an_invalid_trial():
    """Exit 2, not 1: Morph discards it rather than counting it as a failure."""
    code, payload, _ = run_app(APP, "--locale", "zz_ZZ")
    assert code == 2
    assert payload["signal"] == "LocaleUnavailable"


def test_unknown_ambient_locale_is_not_invalid():
    """A developer's own en_GB shell must not turn every run into a setup error."""
    code, payload, _ = run_app(APP, env={"LANG": "en_GB.UTF-8"})
    assert code in (0, 1), payload      # whatever en_GB does, it is a real trial


def test_guard_rejects_a_locale_that_did_not_take_effect(monkeypatch):
    """The false-evidence guard.

    Simulates a platform that accepts the locale name but silently keeps a
    period-decimal convention (real Windows CRT behaviour for names shaped like
    ll_CC, and a Pi with no generated locales). Requesting de_DE there must be
    an invalid trial, never a PASS that hides the bug or a FAIL blamed on the
    locale.
    """
    monkeypatch.setattr(locale_app.locale, "setlocale", lambda *a, **k: "de_DE")
    monkeypatch.setattr(locale_app.locale, "localeconv", lambda: {"decimal_point": "."})

    applied, err = locale_app._apply_locale("de_DE")
    assert applied == ""
    assert err is not None and "did not take effect" in err


@needs_de
def test_machine_mode_contract():
    code, payload, err = run_app(APP, env=TARGET)
    assert code == 1
    assert payload["result"] == "fail"
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}
    assert err == ""


# ------------------------------------------------------------ statistical tier

@pytest.mark.slow
@needs_de
def test_deterministic_over_repeats():
    assert {run_app(APP)[0] for _ in range(5)} == {0}
    assert {run_app(APP, env=TARGET)[0] for _ in range(5)} == {1}
