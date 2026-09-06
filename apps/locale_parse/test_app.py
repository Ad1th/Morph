"""Self-check for Failure D. Confirms the app still fails the way we think it does.

Run: pytest apps/locale_parse/test_app.py

Unlike Failure A this fixture is fully deterministic, so the acceptance bar is
absolute: 0% baseline failures, 100% under condition.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

from apps.locale_parse import app as locale_app

TRIALS = 5


def _run(args: list[str], env_overrides: dict[str, str] | None = None) -> tuple[int, dict]:
    env = dict(os.environ)
    # Stop the developer's own shell locale from leaking into the fixture.
    for var in ("LC_ALL", "LC_NUMERIC", "LANG"):
        env.pop(var, None)
    env.update(env_overrides or {})

    proc = subprocess.run(
        [sys.executable, "-m", "apps.locale_parse", "test", *args],
        capture_output=True, text=True, env=env, timeout=30,
    )
    payload = json.loads(proc.stdout.strip().splitlines()[-1])
    return proc.returncode, payload


def test_baseline_passes_deterministically():
    """de_DE is the baseline: it must never fail, on any run."""
    codes = {_run(["--locale", "de_DE"])[0] for _ in range(TRIALS)}
    assert codes == {0}, f"baseline not clean: saw exit codes {codes}"


def test_fails_under_en_US_deterministically():
    """en_US is the condition: it must always fail, on any run."""
    codes = {_run(["--locale", "en_US"])[0] for _ in range(TRIALS)}
    assert codes == {1}, f"condition not reliable: saw exit codes {codes}"


def test_failure_is_silent_corruption_not_a_crash():
    """The demo's point: a wrong value, not an exception. 1,5 read as 15.0."""
    code, payload = _run(["--locale", "en_US"])
    assert code == 1
    assert payload["signal"] == "LocaleParseMismatch"
    assert "15.0" in payload["detail"]


def test_fixed_variant_survives_the_condition():
    """The one-line fix must pass under the exact locale that breaks the app."""
    code, payload = _run(["--fixed", "--locale", "en_US"])
    assert code == 0 and payload["result"] == "pass"


def test_env_var_knob_works():
    """Morph drives this with LC_ALL on Linux/macOS -- and here too."""
    assert _run([], {"LC_ALL": "en_US.UTF-8"})[0] == 1
    assert _run([], {"LC_ALL": "de_DE.UTF-8"})[0] == 0


def test_unregistered_locale_is_an_invalid_trial():
    """Exit 2, not 1: Morph must discard it rather than count it as a failure."""
    code, payload = _run(["--locale", "zz_ZZ"])
    assert code == 2
    assert payload["signal"] == "LocaleUnavailable"


def test_guard_rejects_a_locale_that_did_not_take_effect(monkeypatch):
    """The false-evidence guard.

    Simulates a platform that accepts the locale name but silently keeps a
    period-decimal convention (real Windows CRT behaviour for names shaped like
    ll_CC, and a Pi with no generated locales). Requesting de_DE there must be
    an invalid trial -- never a FAIL, which would hand Morph fabricated
    evidence that the locale caused something.
    """
    monkeypatch.setattr(locale_app.locale, "setlocale", lambda *a, **k: "de_DE")
    monkeypatch.setattr(locale_app.locale, "localeconv", lambda: {"decimal_point": "."})

    applied, err = locale_app._apply_locale("de_DE")
    assert applied == ""
    assert err is not None and "did not take effect" in err


def test_machine_mode_contract():
    """`test` must emit a parseable JSON result line with the agreed keys."""
    code, payload = _run(["--locale", "en_US"])
    assert code == 1
    assert payload["result"] == "fail"
    assert set(payload) >= {"result", "signal", "duration_ms", "detail"}
    assert payload["detail"]
