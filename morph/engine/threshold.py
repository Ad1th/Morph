"""Binary search for the failure boundary of a single continuous parameter
(e.g. network.latency_ms), holding all other conditions constant.

Takes an optional keyword ``on_event`` (see :mod:`morph.schema.events`). When
supplied, a ``search_probe`` event fires for every value the search evaluates,
and a ``phase_done`` event carries the final bracket -- enough for a live gauge
that visibly converges. Default ``None`` leaves behaviour unchanged.
"""

from collections.abc import Callable

from morph.engine.progress import OnEvent, coerce_result, emit
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent

DEFAULT_FAILURE_RATE_THRESHOLD = 0.5


def search_threshold(
    parameter: str,
    run_at: Callable[[float], bool],
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

    `low` must be a known-safe value and `high` a known-failing value; the
    search narrows toward the boundary between them.
    """
    emit(on_event, TrialEvent(kind="phase_start", phase="threshold", condition=parameter))
    search_points: list[dict] = []

    safe_value = low
    failure_value = high

    def failure_rate_at(value: float) -> float:
        failures = 0
        for _ in range(trials):
            passed, _result = coerce_result(run_at(value))
            if not passed:
                failures += 1
        rate = failures / trials
        point_passed = rate <= failure_rate_threshold
        search_points.append({"value": value, "failure_rate": rate, "passed": point_passed})
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

    # 1. Probe high bound first: if high passes, no threshold is in range
    high_rate = failure_rate_at(high)
    if high_rate <= failure_rate_threshold:
        result = ThresholdResult(
            parameter=parameter,
            safe_value=high,
            failure_value=None,
            boundary_estimate=None,
            search_points=search_points,
        )
        emit(
            on_event,
            TrialEvent(
                kind="phase_done",
                phase="threshold",
                condition=parameter,
                safe_value=high,
                failure_value=None,
                boundary_estimate=None,
            ),
        )
        return result

    # 2. Probe low bound: if low already fails, threshold is at/below low
    low_rate = failure_rate_at(low)
    if low_rate > failure_rate_threshold:
        result = ThresholdResult(
            parameter=parameter,
            safe_value=None,
            failure_value=low,
            boundary_estimate=None,
            search_points=search_points,
        )
        emit(
            on_event,
            TrialEvent(
                kind="phase_done",
                phase="threshold",
                condition=parameter,
                safe_value=None,
                failure_value=low,
                boundary_estimate=None,
            ),
        )
        return result

    # 3. Binary search between known safe (low) and known failing (high)
    while (failure_value - safe_value) > precision:
        mid = (safe_value + failure_value) / 2
        if failure_rate_at(mid) > failure_rate_threshold:
            failure_value = mid
        else:
            safe_value = mid

    result = ThresholdResult(
        parameter=parameter,
        safe_value=safe_value,
        failure_value=failure_value,
        boundary_estimate=(safe_value + failure_value) / 2,
        search_points=search_points,
    )
    emit(
        on_event,
        TrialEvent(
            kind="phase_done",
            phase="threshold",
            condition=parameter,
            safe_value=safe_value,
            failure_value=failure_value,
            boundary_estimate=result.boundary_estimate,
        ),
    )
    return result

