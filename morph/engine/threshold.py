"""Binary search for the failure boundary of a single continuous parameter
(e.g. network.latency_ms), holding all other conditions constant.

This is the *deterministic* method: it halves the interval and takes a
majority vote of ``trials`` runs at each probe. That is fine for a target
whose pass/fail flips cleanly at the boundary, but on a flaky application one
wrong vote sends the search into the wrong half for good, and the reported
bracket (``failure_value - safe_value <= precision``) then overstates how much
is actually known. For a noisy oracle use
:func:`morph.engine.boundary.locate_boundary`, which models the noise and
returns a credible interval instead of a point. The result records
``method="bisection"`` and ``trials`` so a reader can tell the two apart.

Takes an optional keyword ``on_event`` (see :mod:`morph.schema.events`). When
supplied, a ``search_probe`` event fires for every value the search evaluates,
and a ``phase_done`` event carries the final bracket -- enough for a live gauge
that visibly converges. Default ``None`` leaves behaviour unchanged.
"""

from __future__ import annotations

from morph.engine.progress import OnEvent, RunAtFn, emit, run_valid_trial
from morph.schema.comparison import SearchPoint, ThresholdResult
from morph.schema.events import TrialEvent

DEFAULT_FAILURE_RATE_THRESHOLD = 0.5


def search_threshold(
    parameter: str,
    run_at: RunAtFn,
    low: float,
    high: float,
    trials: int = 5,
    precision: float = 1.0,
    failure_rate_threshold: float = DEFAULT_FAILURE_RATE_THRESHOLD,
    *,
    on_event: OnEvent | None = None,
) -> ThresholdResult:
    """`run_at(value)` runs one trial at `value` and returns True if it passed
    (a ``RunResult`` is also accepted).

    `low` should be a value expected to pass and `high` one expected to fail;
    both are probed first, and the search only bisects when they behave that
    way (``outcome="boundary_found"``). If ``high`` passes the result is
    ``outcome="never_fails"`` with ``safe_value=high``; if ``low`` fails it is
    ``outcome="always_fails"`` with ``failure_value=low``; either way
    ``boundary_estimate`` is ``None``.

    A probe "passes" when its failure rate is ``<= failure_rate_threshold``.
    See the module docstring for why this method fabricates precision on a
    noisy target and when to prefer ``morph.engine.boundary.locate_boundary``.
    """
    if trials < 1:
        raise ValueError(f"trials must be >= 1, got {trials}")
    if not precision > 0:
        raise ValueError(f"precision must be > 0, got {precision}")
    if not high > low:
        raise ValueError(f"high ({high}) must exceed low ({low})")
    if not 0.0 <= failure_rate_threshold < 1.0:
        raise ValueError("failure_rate_threshold must be in [0, 1)")

    emit(on_event, TrialEvent(kind="phase_start", phase="threshold", condition=parameter))
    search_points: list[SearchPoint] = []

    safe_value = low
    failure_value = high

    def failure_rate_at(value: float) -> float:
        failures = 0
        for i in range(trials):
            passed, _result, _ms = run_valid_trial(
                lambda: run_at(value), parameter, on_event,
                trial_index=i, total=trials, param_value=value,
            )
            if not passed:
                failures += 1
        rate = failures / trials
        point_passed = rate <= failure_rate_threshold
        search_points.append(SearchPoint(value=value, failure_rate=rate, passed=point_passed))
        emit(
            on_event,
            TrialEvent(
                kind="search_probe",
                phase="threshold",
                condition=parameter,
                param_value=value,
                failures=failures,
                total=trials,
                failure_rate=rate,
                safe_value=safe_value,
                failure_value=failure_value,
                extra={"passed": point_passed},
            ),
        )
        return rate

    def finish(
        outcome: str, safe: float | None, fail: float | None, estimate: float | None
    ) -> ThresholdResult:
        result = ThresholdResult(
            parameter=parameter,
            safe_value=safe,
            failure_value=fail,
            boundary_estimate=estimate,
            search_points=search_points,
            outcome=outcome,
            method="bisection",
            trials=trials,
        )
        emit(
            on_event,
            TrialEvent(
                kind="phase_done",
                phase="threshold",
                condition=parameter,
                safe_value=safe,
                failure_value=fail,
                boundary_estimate=estimate,
                extra={"outcome": outcome, "trials_per_probe": trials, "probes": len(search_points)},
            ),
        )
        return result

    # 1. Probe high bound first: if high passes, no threshold is in range
    if failure_rate_at(high) <= failure_rate_threshold:
        return finish("never_fails", high, None, None)

    # 2. Probe low bound: if low already fails, threshold is at/below low
    if failure_rate_at(low) > failure_rate_threshold:
        return finish("always_fails", None, low, None)

    # 3. Binary search between known safe (low) and known failing (high).
    #    With precision >= high - low this loop never runs and the estimate
    #    rests on the two endpoint probes alone.
    while (failure_value - safe_value) > precision:
        mid = (safe_value + failure_value) / 2
        if failure_rate_at(mid) > failure_rate_threshold:
            failure_value = mid
        else:
            safe_value = mid

    return finish("boundary_found", safe_value, failure_value, (safe_value + failure_value) / 2)
