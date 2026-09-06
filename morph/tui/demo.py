"""Recorded experiment playback for ``morph tui --demo``.

The flagship story -- baseline and each variable alone are clean, the
combination fails every time, verdict ENVIRONMENT-CAUSED -- rendered from a
canned event script with realistic pacing. No root, no network shaping, no
target application required, so the live views work anywhere.

This is clearly a recording: the status line reads DEMO, and live mode
(the default) runs the real engine.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from morph.schema.events import TrialEvent

# (condition, per-trial pass/fail). "full_target" = latency + packet loss together.
_SCRIPT: list[tuple[str, list[bool]]] = [
    ("baseline", [True, True, True, True, True]),
    ("latency_only", [True, True, True, True, True]),
    ("loss_only", [True, True, True, True, True]),
    ("full_target", [False, False, False, False, False]),
]

_STDERR = (
    "Traceback (most recent call last):\n"
    '  File "checkout_service/demo_app.py", line 118, in _commit\n'
    "    raise LockLostException(order_id)\n"
    "LockLostException: lock for order 8123 expired mid-payment"
)


def demo_events() -> list[TrialEvent]:
    """The full event stream a real run would emit for this scenario."""
    events: list[TrialEvent] = [TrialEvent(kind="phase_start", phase="isolation")]
    baseline_fr = 0.0
    for condition, outcomes in _SCRIPT:
        total = len(outcomes)
        events.append(TrialEvent(kind="condition_start", condition=condition, total=total))
        failures = 0
        for i, passed in enumerate(outcomes):
            if not passed:
                failures += 1
            events.append(
                TrialEvent(
                    kind="trial", condition=condition, trial_index=i, total=total,
                    passed=passed, duration_ms=41.0 if passed else 30021.0,
                    failures_so_far=failures,
                    error_type=None if passed else "LockLostException",
                    stderr_tail=None if passed else _STDERR,
                )
            )
        rate = failures / total
        events.append(
            TrialEvent(kind="condition_done", condition=condition, total=total,
                       failures=failures, failure_rate=rate)
        )
        if condition == "baseline":
            baseline_fr = rate
            continue
        significant = rate > baseline_fr + 0.5
        events.append(
            TrialEvent(
                kind="comparison", condition=condition,
                failures=failures, failure_rate=rate,
                p_value=0.0079 if significant else 1.0,
                is_significant=significant,
                effect_label="significant_increase" if significant else "no_effect",
            )
        )
    events.append(TrialEvent(kind="phase_done", phase="isolation"))
    events.append(
        TrialEvent(
            kind="verdict", phase="isolation", classification="environment_caused",
            strongest_condition="full_target", p_value=0.0079, is_significant=True,
            extra={
                "summary": "baseline 0/5; 'full_target' (latency 180ms + loss 2%) 5/5 (p=0.0079). "
                "Neither latency nor loss alone reproduced it."
            },
        )
    )
    return events


def play(on_event: Callable[[TrialEvent], None], *, speed: float = 1.0) -> None:
    """Emit the recorded events with pacing (call from a worker thread)."""
    gaps = {"trial": 0.16, "condition_start": 0.35, "condition_done": 0.3,
            "comparison": 0.6, "phase_start": 0.2, "phase_done": 0.3, "verdict": 0.4}
    for event in demo_events():
        on_event(event)
        time.sleep(gaps.get(event.kind, 0.1) / max(speed, 0.01))
