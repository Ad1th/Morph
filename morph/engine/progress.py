"""Shared helpers for the engine's optional ``on_event`` progress callback.

Kept tiny and dependency-light so ``experiment.py``, ``sequential.py``,
``threshold.py`` and ``boundary.py`` share one definition of "how do we emit
an event", "what did this run_fn return", and "what happens when a trial could
not be run at all".
"""

from __future__ import annotations

import time
from collections.abc import Callable

from morph.engine.errors import InvalidTrialError
from morph.schema.events import TrialEvent
from morph.schema.telemetry import RunResult

OnEvent = Callable[[TrialEvent], None]

# A trial callback returns ``True`` when the run passed, or a full ``RunResult``
# (used by the TUI so events can carry stdout/stderr and timing).
RunFn = Callable[[], bool | RunResult]
RunAtFn = Callable[[float], bool | RunResult]

TAIL_CHARS = 2000
INVALID_TRIAL_ATTEMPTS = 3  # first attempt + up to 2 retries


def emit(on_event: OnEvent | None, event: TrialEvent) -> None:
    """Call ``on_event`` if one was supplied; a no-op otherwise."""
    if on_event is not None:
        on_event(event)


def tail(text: str | None) -> str | None:
    if not text:
        return None
    return text[-TAIL_CHARS:]


def coerce_result(raw: object) -> tuple[bool, RunResult | None]:
    """Normalise a run_fn return value.

    A trial callback may return a plain ``bool`` (the historical contract) or a
    full ``RunResult``. Anything else -- notably ``None`` from a callback that
    forgot to ``return`` -- is a programming error, not a failed trial, and
    raises ``TypeError`` rather than silently counting as a failure.
    """
    if isinstance(raw, RunResult):
        return raw.passed, raw
    if isinstance(raw, bool):
        return raw, None
    raise TypeError(
        f"run_fn must return a bool or a RunResult, got {type(raw).__name__}: {raw!r}"
    )


def is_invalid(result: RunResult | None) -> bool:
    """A ``RunResult`` flagged as a setup error (guarded so it works before the
    ``invalid`` field exists on the schema)."""
    return bool(getattr(result, "invalid", False)) if result is not None else False


def run_valid_trial(
    run_fn: Callable[[], object],
    condition: str,
    on_event: OnEvent | None,
    *,
    trial_index: int | None = None,
    total: int | None = None,
    param_value: float | None = None,
    attempts: int = INVALID_TRIAL_ATTEMPTS,
) -> tuple[bool, RunResult | None, float]:
    """Run one trial, retrying when the runtime reports it as *invalid*.

    An invalid result (``RunResult.invalid``: command not launchable, exit
    code 2/126/127, ...) is neither a pass nor a failure. It is retried up to
    ``attempts`` times in total, each invalid attempt emitting a
    ``kind="trial"`` event with ``passed=None`` and ``extra={"invalid": True,
    "reason": ...}``; if every attempt is invalid,
    :class:`~morph.engine.errors.InvalidTrialError` is raised so the caller can
    report a setup problem instead of a verdict.

    Returns ``(passed, run_result_or_None, elapsed_ms)``.
    """
    reason: str | None = None
    for attempt in range(attempts):
        start = time.perf_counter()
        raw = run_fn()
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        passed, result = coerce_result(raw)
        if result is not None and result.duration_ms:
            elapsed_ms = result.duration_ms
        if not is_invalid(result):
            return passed, result, elapsed_ms
        reason = getattr(result, "invalid_reason", None) or result.error_message or result.error_type
        emit(
            on_event,
            TrialEvent(
                kind="trial",
                condition=condition,
                trial_index=trial_index,
                total=total,
                passed=None,
                duration_ms=elapsed_ms,
                error_type=result.error_type,
                stdout_tail=tail(result.stdout),
                stderr_tail=tail(result.stderr),
                param_value=param_value,
                extra={"invalid": True, "reason": reason, "attempt": attempt + 1},
            ),
        )
    raise InvalidTrialError(condition, reason, attempts)
