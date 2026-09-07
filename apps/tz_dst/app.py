"""Failure F: "same time tomorrow" scheduling across a DST transition.

Mechanism. A scheduler stores the last run as a local wall-clock time and
computes the next run as ``last_run_epoch + 86400``: "24 hours later". On
almost every day, in almost every zone, that is the same wall-clock time
tomorrow. On the night a zone changes its clocks it is not: the calendar day
is 23 or 25 hours long, so the job fires an hour early or an hour late, and
when the transition sits at midnight it can land on the wrong DATE.

    anchor            2018-11-03 23:30 local ("run nightly at 23:30")
    TZ=UTC            next run 2018-11-04 23:30           correct
    TZ=Asia/Kolkata   next run 2018-11-04 23:30           correct (no DST)
    TZ=America/Sao_Paulo   DST starts 2018-11-04 00:00 (clocks jump to 01:00)
                      next run 2018-11-05 00:30 -02       a whole day skipped
    TZ=America/New_York    DST ends 2018-11-04 02:00
                      next run 2018-11-04 22:30 EST       an hour early

    Env knob Morph turns : TZ (profile ``locale.timezone``), or --tz
    Baseline (host zone, or TZ unset) : PASS unless the host observes a
                                        transition that night
    Fails when           : TZ names a zone whose clocks change between the
                           anchor and the next run (America/Sao_Paulo is the
                           documented target)
    Fix (one line)       : do calendar arithmetic on wall-clock fields and let
                           mktime resolve the offset (tm_isdst = -1)
    Classification       : environment-caused

Fully deterministic: no timing, no randomness, no network. Real-world
evidence: moment-timezone #672 / #728 / #967, pytz #56 (see
docs/faultyapps.md section 8.2); this is that bug in pure Python.

Exit codes: 0 pass, 1 the engineered failure (``ScheduleDrift``), 2 invalid
trial: ``TZ`` (or --tz) names a zone the host does not know, or libc did not
apply it (the false-evidence guard: an unknown TZ silently becomes UTC, which
would look like a PASS "under" the requested zone).

Tuning knobs:
    MORPH_F_TZ       zone to apply explicitly (default: TZ env / host zone)
    MORPH_F_ANCHOR   anchor wall-clock time, "YYYY-MM-DD HH:MM" (default 2018-11-03 23:30)
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta

ANCHOR = os.getenv("MORPH_F_ANCHOR", "2018-11-03 23:30")
DAY_S = 86400


def _apply_tz(requested: str | None) -> tuple[str, str | None]:
    """Make ``requested`` (or the ambient TZ) the process zone and verify it.

    Returns (zone_label, error). A non-None error means an INVALID trial.
    """
    zone = requested or os.environ.get("TZ") or ""
    if not zone:
        return time.tzname[0] or "host", None       # the host's own zone: nothing to verify

    if not hasattr(time, "tzset"):
        return "", "this platform has no tzset(); pass the zone to a zoneinfo-based build"

    try:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        try:
            info = ZoneInfo(zone)
        except (ZoneInfoNotFoundError, ValueError):
            return "", (f"timezone {zone!r} is not a known IANA zone on this host "
                        f"(tzdata missing?); see docs/faultyapps.md section 6")
    except ImportError:
        info = None

    os.environ["TZ"] = zone
    time.tzset()

    if info is not None:
        # Guard: libc and zoneinfo must agree on the offset at the anchor,
        # otherwise the zone did not really take effect.
        anchor = datetime.strptime(ANCHOR, "%Y-%m-%d %H:%M")
        expected = info.utcoffset(anchor.replace(tzinfo=info))
        libc = time.localtime(time.mktime((*anchor.timetuple()[:6], 0, 0, -1))).tm_gmtoff
        if expected is not None and int(expected.total_seconds()) != libc:
            return "", (f"TZ={zone!r} did not take effect: libc offset {libc}s, "
                        f"zoneinfo says {int(expected.total_seconds())}s")
    return zone, None


def _next_run_buggy(anchor: time.struct_time) -> time.struct_time:
    """The bug: 'tomorrow' as 24 hours of elapsed time."""
    return time.localtime(time.mktime(anchor) + DAY_S)


def _next_run_fixed(anchor: time.struct_time) -> time.struct_time:
    """The fix: 'tomorrow' as the same wall-clock time one calendar day on,
    with the DST flag left to mktime (tm_isdst = -1)."""
    d = datetime(*anchor[:5]) + timedelta(days=1)
    return time.localtime(time.mktime((d.year, d.month, d.day, d.hour, d.minute, 0, 0, 0, -1)))


def main(machine_mode: bool, fixed: bool, requested_tz: str | None = None) -> int:
    explicit = requested_tz or os.getenv("MORPH_F_TZ") or None
    zone, err = _apply_tz(explicit)

    if err:
        outcome = {"result": "error", "signal": "TimezoneUnavailable", "duration_ms": 0, "detail": err}
    else:
        anchor_dt = datetime.strptime(ANCHOR, "%Y-%m-%d %H:%M")
        anchor = time.localtime(time.mktime((*anchor_dt.timetuple()[:6], 0, 0, -1)))
        want = anchor_dt + timedelta(days=1)
        got = (_next_run_fixed if fixed else _next_run_buggy)(anchor)
        got_dt = datetime(*got[:5])
        stamp = time.strftime("%Y-%m-%d %H:%M %Z", got)
        if got_dt == want:
            outcome = {"result": "pass", "signal": None, "duration_ms": 0,
                       "detail": f"next run {stamp} under {zone}"}
        else:
            delta_h = (got_dt - want).total_seconds() / 3600
            outcome = {"result": "fail", "signal": "ScheduleDrift", "duration_ms": 0,
                       "detail": (f"next run scheduled {stamp}, expected "
                                  f"{want:%Y-%m-%d %H:%M} under {zone} "
                                  f"({delta_h:+.0f} h: the calendar day was not 24 h long)")}

    if machine_mode:
        print(json.dumps(outcome))
    else:
        label = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[outcome["result"]]
        print(f"[tz_dst] {label}  tz={zone or explicit or 'host'}"
              + ("  (--fixed: wall-clock arithmetic)" if fixed else ""))
        print(f"  {outcome['detail']}")

    if outcome["result"] == "pass":
        return 0
    if outcome["result"] == "fail":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(machine_mode="test" in sys.argv, fixed="--fixed" in sys.argv))
