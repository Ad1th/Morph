"""Failure D: locale-dependent number parsing (silent data corruption).

Mechanism: a config value written the way the developer wrote it ("1.5", one
and a half, period decimal) is parsed with locale.atof(), which honours the
*ambient* locale's numeric conventions. On the developer's machine (C, POSIX,
en_US, en_IN: period decimal) it reads 1.5. On a German or French user's
machine the period is the THOUSANDS separator, so it is stripped and the value
silently reads 15.0. A 10x error, no exception raised.

    C / en_US / en_IN   decimal_point='.'  atof("1.5") -> 1.5    correct
    de_DE / fr_FR       decimal_point=','  atof("1.5") -> 15.0   silently wrong

    Env knob Morph turns : LC_ALL / LANG (profile ``locale.locale``), or --locale
    Baseline (no locale env, C.UTF-8 shell) : 0 % fail
    Fails when           : a comma-decimal locale (de_DE, fr_FR) is set -> 100 % fail
    Fix (one line)       : parse the value's documented format: float(raw)
    Classification       : environment-caused

Fully deterministic: no timing, no randomness, no network.

Exit codes follow the corpus contract. 0 pass, 1 the engineered failure, and
2 ONLY for a genuinely invalid trial: a locale was explicitly requested
(--locale, MORPH_D_LOCALE, or LC_ALL/LANG naming a locale this fixture knows)
and it is not installed or did not take effect. An unknown ambient locale is
not invalid: the app runs under whatever the machine has, which is exactly the
"works on my machine" situation the fixture models.

Windows note: setlocale(LC_ALL, "") reads OS settings, NOT the LANG/LC_ALL
environment variables, and changing the OS locale needs a reboot. This app
therefore reads LC_ALL/LANG itself and applies them explicitly, so Morph's env
export is honoured on Windows too; --locale / MORPH_D_LOCALE remain as a
backup knob.

Tuning knobs:
    MORPH_D_LOCALE   locale to apply explicitly (default: ambient/env)
    MORPH_D_RAW      the raw config value to parse (default "1.5")
    MORPH_D_EXPECTED the correct parsed value (default 1.5)
"""

from __future__ import annotations

import json
import locale
import os

RAW_VALUE = os.getenv("MORPH_D_RAW", "1.5")
EXPECTED = float(os.getenv("MORPH_D_EXPECTED", "1.5"))
TOLERANCE = 1e-6

# Known locales: the naming variants worth trying, plus the numeric convention
# that locale MUST produce if it genuinely took effect.
#
# The `decimal_point` entry is a guard, not documentation. Windows' CRT accepts
# any name shaped like ll_CC (e.g. "zz_ZZ") and silently falls back to a
# period-decimal default, and a Pi Lite image without generated locales can
# behave similarly. Without this check a locale that never applied would
# produce a *false* PASS or FAIL, and Morph would report on fabricated
# evidence. Verify the convention, never trust setlocale's return.
_LOCALES = {
    "de_DE": {"aliases": ["de_DE.UTF-8", "de_DE.utf8", "de_DE", "German_Germany.1252", "de-DE"],
              "decimal_point": ","},
    "fr_FR": {"aliases": ["fr_FR.UTF-8", "fr_FR.utf8", "fr_FR", "French_France.1252", "fr-FR"],
              "decimal_point": ","},
    "en_US": {"aliases": ["en_US.UTF-8", "en_US.utf8", "en_US", "English_United States.1252", "en-US"],
              "decimal_point": "."},
    "en_IN": {"aliases": ["en_IN.UTF-8", "en_IN.utf8", "en_IN", "English_India.1252", "en-IN"],
              "decimal_point": "."},
}

# Locale names that mean "no particular locale": the developer's default shell.
_NEUTRAL = {"", "C", "POSIX", "C.UTF-8", "C.utf8"}


def _base_name(requested: str) -> str:
    return requested.split(".")[0].split("@")[0].replace("-", "_")


def _candidates(requested: str) -> list[str]:
    """Expands a requested locale into the naming variants worth trying."""
    entry = _LOCALES.get(_base_name(requested))
    if not entry:
        return [requested]
    # put the exact requested string first in case it is already valid here
    return [requested] + [c for c in entry["aliases"] if c != requested]


def _env_requested() -> str | None:
    """The locale the *environment* is asking for, Unix-style.

    Morph exports LC_ALL and LANG (adapters' ``_apply_locale_env``). Reading
    them back lets the app verify the knob actually moved: on Windows the CRT
    ignores these variables, so a run driven that way would otherwise report
    an outcome produced by the machine's own locale, not the requested one.
    """
    for var in ("LC_ALL", "LC_NUMERIC", "LANG"):
        value = os.environ.get(var)
        if value and value not in _NEUTRAL:
            return value
    return None


def _apply_locale(requested: str | None) -> tuple[str, str | None]:
    """Sets the process locale and verifies it actually took effect.

    Returns (applied_name, error). A non-None error means this trial is INVALID
    (exit 2, "not a failure"): the engine discards it rather than counting it.
    """
    if not requested:
        # Nothing requested: the developer's ambient locale, whatever it is.
        try:
            locale.setlocale(locale.LC_ALL, "")
            return locale.setlocale(locale.LC_NUMERIC) or "C", None
        except locale.Error:
            locale.setlocale(locale.LC_ALL, "C")
            return "C", None

    entry = _LOCALES.get(_base_name(requested))
    if not entry:
        return "", (f"locale {requested!r} is not registered in this fixture, so its numeric "
                    f"convention cannot be verified; add it to _LOCALES in app.py. "
                    f"Known: {', '.join(sorted(_LOCALES))}")

    for candidate in _candidates(requested):
        try:
            locale.setlocale(locale.LC_ALL, candidate)
        except locale.Error:
            continue
        actual = locale.localeconv()["decimal_point"]
        if actual == entry["decimal_point"]:
            return candidate, None
        # Name accepted but the convention is wrong => it did not really apply.
        locale.setlocale(locale.LC_ALL, "C")

    return "", (f"locale {requested!r} is not installed, or did not take effect "
                f"(expected decimal_point {entry['decimal_point']!r}; "
                f"tried: {', '.join(_candidates(requested))}); "
                f"generate it, see docs/faultyapps.md section 6")


def _parse_buggy(raw: str) -> float:
    """The bug: trusts the ambient locale's numeric convention."""
    return locale.atof(raw)


def _parse_fixed(raw: str) -> float:
    """The fix: the config format is documented as period-decimal; parse that."""
    return float(raw)


def main(machine_mode: bool, fixed: bool, requested_locale: str | None = None) -> int:
    # An explicit --locale / MORPH_D_LOCALE is a deliberate knob: verify it
    # strictly. A locale inherited from LC_ALL/LANG is verified when this
    # fixture knows its numeric convention; any other ambient locale (a
    # developer's en_GB shell) is applied as-is and never a setup error.
    explicit = requested_locale or os.getenv("MORPH_D_LOCALE") or None
    requested = explicit
    if requested is None:
        from_env = _env_requested()
        if from_env and _base_name(from_env) in _LOCALES:
            requested = from_env

    applied, err = _apply_locale(requested)

    if err:
        outcome = {"result": "error", "signal": "LocaleUnavailable",
                   "duration_ms": 0, "detail": err}
    else:
        parser = _parse_fixed if fixed else _parse_buggy
        try:
            parsed = parser(RAW_VALUE)
            if abs(parsed - EXPECTED) < TOLERANCE:
                outcome = {"result": "pass", "signal": None, "duration_ms": 0,
                           "detail": f"parsed {RAW_VALUE!r} as {parsed} under {applied}"}
            else:
                outcome = {
                    "result": "fail", "signal": "LocaleParseMismatch", "duration_ms": 0,
                    "detail": (f"parsed {RAW_VALUE!r} as {parsed}, expected {EXPECTED} "
                               f"under {applied} (decimal point read as thousands separator)"),
                }
        except ValueError as exc:
            # Some locales reject the string outright rather than misreading it.
            # Still the engineered failure, just the loud variant.
            outcome = {"result": "fail", "signal": "ValueError", "duration_ms": 0,
                       "detail": f"{exc} under {applied}"}

    if machine_mode:
        print(json.dumps(outcome))
    else:
        label = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[outcome["result"]]
        print(f"[locale_parse] {label}  locale={applied or requested or 'ambient'}")
        print(f"  {outcome['detail']}")

    if outcome["result"] == "pass":
        return 0
    if outcome["result"] == "fail":
        return 1
    return 2
