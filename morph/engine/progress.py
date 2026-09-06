"""Shared helpers for the engine's optional ``on_event`` progress callback.

Kept tiny and dependency-light so ``experiment.py`` and ``threshold.py`` share
one definition of "how do we emit an event" and "what did this run_fn return".
"""

from __future__ import annotations

from collections.abc import Callable

from morph.schema.events import TrialEvent
from morph.schema.telemetry import RunResult

OnEvent = Callable[[TrialEvent], None]

TAIL_CHARS = 2000


def emit(on_event: OnEvent | None, event: TrialEvent) -> None:
    """Call ``on_event`` if one was supplied; a no-op otherwise."""
    if on_event is not None:
        on_event(event)


def coerce_result(raw: object) -> tuple[bool, RunResult | None]:
    """Normalise a run_fn return value.

    A trial callback may return a plain ``bool`` (the historical contract) or a
    full ``RunResult`` (used by the TUI so events can carry stdout/stderr and
    timing). Returns ``(passed, run_result_or_None)``.
    """
    if isinstance(raw, RunResult):
        return raw.passed, raw
    return bool(raw), None
