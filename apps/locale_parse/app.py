"""Failure D: locale-dependent number parsing (silent data corruption).

Mechanism: a config value written European-style ("1,5" = one and a half) is
parsed with locale.atof(), which honours the *ambient* locale's numeric
conventions. Under a comma-decimal locale it reads 1.5. Under a period-decimal
locale the comma is treated as a THOUSANDS separator and it silently reads
15.0 -- a 10x error, with no exception raised.

    de_DE.UTF-8   decimal_point=','  atof("1,5") -> 1.5    correct
    en_US.UTF-8   decimal_point='.'  atof("1,5") -> 15.0   silently wrong

    Env knob Morph turns : LANG / LC_ALL / LC_NUMERIC  (or --locale on Windows)
    Baseline (de_DE)     : 0% fail
    Fails when           : a period-decimal locale (en_US) is set -> 100% fail
    Fix (one line)       : parse locale-independently instead of via locale.atof
    Classification       : environment-caused

Fully deterministic -- no timing, no randomness, no network.

Windows note: setlocale(LC_ALL, "") reads OS settings, NOT the LANG/LC_ALL
environment variables, and changing the OS locale needs a reboot. So the locale
is also accepted as an explicit --locale / MORPH_D_LOCALE knob, which is how
Morph should drive this app on Windows (see docs/faultyapps.md section 6).

Tuning knobs:
    MORPH_D_LOCALE   locale to apply explicitly (default: ambient/env)
    MORPH_D_RAW      the raw config value to parse (default "1,5")
    MORPH_D_EXPECTED the correct parsed value (default 1.5)
"""

from __future__ import annotations

import json
import locale
import os
import sys

RAW_VALUE = os.getenv("MORPH_D_RAW", "1,5")
EXPECTED = float(os.getenv("MORPH_D_EXPECTED", "1.5"))
TOLERANCE = 1e-6

# Known locales: the naming variants worth trying, plus the numeric convention
# that locale MUST produce if it genuinely took effect.
#
# The `decimal_point` entry is not documentation -- it is a guard. Windows' CRT
# accepts any name shaped like ll_CC (e.g. "zz_ZZ") and silently falls back to a
# period-decimal default, and a Pi Lite image without generated locales can
# behave similarly. Without this check a locale that never applied would produce
# a *false* FAIL, and Morph would report "locale caused the failure" on evidence
# that was fabricated. Verify the convention, never trust setlocale's return.
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


def _base_name(requested: str) -> str:
    return requested.split(".")[0].replace("-", "_")


def _candidates(requested: str) -> list[str]:
    """Expands a requested locale into the naming variants worth trying."""
    entry = _LOCALES.get(_base_name(requested))
    if not entry:
        return [requested]
    # put the exact requested string first in case it is already valid here
    return [requested] + [c for c in entry["aliases"] if c != requested]


def _env_requested() -> str | None:
    """The locale the *environment* is asking for, Unix-style.

    Morph sets LC_ALL/LC_NUMERIC/LANG on Linux and macOS. Reading it back lets
    us verify the knob actually moved: on Windows the CRT ignores these
    variables entirely, so a run driven that way would otherwise report a FAIL
    produced by the machine's own locale rather than by the requested one.
    """
    for var in ("LC_ALL", "LC_NUMERIC", "LANG"):
        value = os.environ.get(var)
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return value
    return None


def _apply_locale(requested: str | None) -> tuple[str, str | None]:
    """Sets the process locale and verifies it actually took effect.

    Returns (applied_name, error). A non-None error means this trial is INVALID
    (exit 2, "not a failure") -- per the interface contract, Morph must discard
    it rather than count it as evidence.
    """
    if not requested:
        # Pure ambient with nothing requested: apply and report, but there is
        # no expectation to verify against.
        try:
            locale.setlocale(locale.LC_ALL, "")
            return locale.setlocale(locale.LC_NUMERIC), None
        except locale.Error as exc:
            return "", f"could not apply ambient locale: {exc}"

    entry = _LOCALES.get(_base_name(requested))
    if not entry:
        return "", (f"locale {requested!r} is not registered in this fixture, so its numeric "
                    f"convention cannot be verified -- add it to _LOCALES in app.py. "
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
                f"tried: {', '.join(_candidates(requested))}) -- "
                f"generate it, see docs/faultyapps.md section 6")


def _parse_buggy(raw: str) -> float:
    """The bug: trusts the ambient locale's numeric convention."""
    return locale.atof(raw)


def _parse_fixed(raw: str) -> float:
    """The fix: parse the value's own documented format, locale-independently."""
    return float(raw.replace(",", "."))


def main(machine_mode: bool, fixed: bool, requested_locale: str | None = None) -> int:
    # An explicit --locale / MORPH_D_LOCALE is a deliberate knob: verify it
    # strictly. A locale inherited from LC_ALL/LANG is only verified when this
    # fixture knows its numeric convention -- otherwise a developer's own
    # LANG=en_GB shell would turn every plain `run` into a setup error.
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
                               f"under {applied} (decimal comma read as thousands separator)"),
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
