"""Recorded playback for ``morph tui --demo``.

Nothing here is hand-written. The event streams come from running the *real*
engines (:func:`morph.engine.sequential.run_sequential_experiment` and
:func:`morph.engine.boundary.locate_boundary`) over deterministic synthetic
trial functions that model apps/pool_retry at its 120 ms / 18 % operating point
(see apps/README.md): baseline and each network variable alone are clean, the
combination misses its deadline every time. Every e-value, credible interval
and early stop on screen is therefore one the engine actually produced.

No root, no network shaping, no target application: the run functions never
spawn a process. The status bar says DEMO the whole time.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from functools import lru_cache

from morph.engine.boundary import locate_boundary
from morph.engine.experiment import run_trials
from morph.engine.sequential import run_sequential_experiment
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult
from morph.schema.telemetry import RunResult, TelemetryData

DEMO_COMMAND = "python -m apps.pool_retry"
DEMO_SEED = 8

# What the fixture actually prints when the batch misses its deadline. It
# goes to stdout, not stderr: pool_retry suppresses its own tracebacks so
# Morph's error parser is not misled by the connection resets that are part
# of the design.
FAIL_STDOUT = (
    "[pool_retry] FAIL\n"
    "  9/12 requests completed in 2607ms (deadline 2400ms, pool 2)"
)
PASS_STDOUT = "[pool_retry] OK\n  12/12 requests completed in 558ms (deadline 2400ms, pool 2)"
FAIL_ERROR_TYPE = "DeadlineExceeded"


def synthetic_run(passed: bool, rng: random.Random, *, latency_ms: float = 0.0) -> RunResult:
    """One pool_retry-shaped RunResult without spawning anything."""
    base = 558.0 + latency_ms * 1.1
    duration = base + rng.gauss(0, 25) if passed else 2607.0 + rng.gauss(0, 40)
    return RunResult(
        exit_code=0 if passed else 1,
        passed=passed,
        duration_ms=max(1.0, duration),
        stdout=PASS_STDOUT if passed else FAIL_STDOUT,
        stderr="",
        peak_memory_mb=round(96 + rng.gauss(0, 3), 1),
        telemetry=TelemetryData(cpu_percent=round(18 + rng.gauss(0, 2), 1)),
        error_type=None if passed else FAIL_ERROR_TYPE,
        error_message=None if passed else "batch missed its 2400ms deadline",
    )


def _pool_retry_fails(latency_ms: float, loss_pct: float, rng: random.Random) -> bool:
    """pool_retry's measured behaviour: latency alone never trips the deadline
    in range, loss alone flakes about once in twelve, together the retries
    stack past the deadline every time. Along the latency axis at 18 % loss
    the deadline starts to bite around 95 ms."""
    if loss_pct >= 10.0 and latency_ms >= 60.0:
        p_fail = 0.02 + 0.96 / (1.0 + pow(2.718281828, -(latency_ms - 95.0) / 9.0))
    elif loss_pct >= 10.0:
        p_fail = 0.08
    else:
        p_fail = 0.005
    return rng.random() < p_fail


@lru_cache(maxsize=1)
def experiment_recording() -> tuple[list[TrialEvent], ExperimentResult]:
    """Sequential isolation of pool_retry at 120 ms + 18 % loss, recorded."""
    rng = random.Random(DEMO_SEED)
    events: list[TrialEvent] = []

    def baseline() -> RunResult:
        return synthetic_run(not _pool_retry_fails(0.0, 0.0, rng), rng)

    def latency_only() -> RunResult:
        return synthetic_run(not _pool_retry_fails(120.0, 0.0, rng), rng, latency_ms=120.0)

    def loss_only() -> RunResult:
        return synthetic_run(not _pool_retry_fails(0.0, 18.0, rng), rng)

    def full_target() -> RunResult:
        return synthetic_run(not _pool_retry_fails(120.0, 18.0, rng), rng, latency_ms=120.0)

    result = run_sequential_experiment(
        baseline,
        {"latency_only": latency_only, "loss_only": loss_only, "full_target": full_target},
        max_rounds=12,
        on_event=events.append,
    )
    return events, result


@lru_cache(maxsize=1)
def threshold_recording() -> tuple[list[TrialEvent], ThresholdResult]:
    """Bayesian boundary search along latency at 18 % loss, recorded."""
    rng = random.Random(DEMO_SEED + 1)
    events: list[TrialEvent] = []

    def run_at(latency_ms: float) -> RunResult:
        return synthetic_run(
            not _pool_retry_fails(latency_ms, 18.0, rng), rng, latency_ms=latency_ms
        )

    result = locate_boundary(
        "network.latency_ms", run_at, 0.0, 400.0, max_trials=24, on_event=events.append
    )
    return events, result


@lru_cache(maxsize=1)
def replay_recording() -> list[TrialEvent]:
    """A regression replay under a fixed environment (three clean trials)."""
    rng = random.Random(DEMO_SEED + 2)
    events: list[TrialEvent] = []
    run_trials(lambda: synthetic_run(True, rng), 3, "replay:demo", on_event=events.append)
    events.append(
        TrialEvent(
            kind="verdict", condition="demo", classification="compliant",
            extra={"summary": "0/3 failed (0%); tolerance ≤ 0%"},
        )
    )
    return events


def demo_events() -> list[TrialEvent]:
    """The experiment stream (kept for callers that only want the story)."""
    return list(experiment_recording()[0])


_GAPS = {
    "trial": 0.06, "evidence": 0.04, "condition_start": 0.2, "condition_done": 0.2,
    "comparison": 0.35, "phase_start": 0.2, "phase_done": 0.3, "verdict": 0.4,
    "search_probe": 0.22,
}


def play(
    on_event: Callable[[TrialEvent], None],
    events: list[TrialEvent] | None = None,
    *,
    speed: float = 1.0,
) -> None:
    """Emit recorded events with pacing (call from a worker thread). Raises
    whatever ``on_event`` raises, so a cancelling callback stops playback."""
    for event in events if events is not None else demo_events():
        on_event(event)
        time.sleep(_GAPS.get(event.kind, 0.1) / max(speed, 0.01))
