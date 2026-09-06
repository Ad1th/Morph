"""Binary search for the failure boundary of a single continuous parameter
(e.g. network.latency_ms), holding all other conditions constant."""

from typing import Callable

from morph.schema.comparison import ThresholdResult

DEFAULT_FAILURE_RATE_THRESHOLD = 0.5


def search_threshold(
    parameter: str,
    run_at: Callable[[float], bool],
    low: float,
    high: float,
    trials: int = 5,
    precision: float = 1.0,
    failure_rate_threshold: float = DEFAULT_FAILURE_RATE_THRESHOLD,
) -> ThresholdResult:
    """`run_at(value)` runs one trial at `value` and returns True if it passed.

    `low` must be a known-safe value and `high` a known-failing value; the
    search narrows toward the boundary between them.
    """
    search_points: list[dict] = []

    def failure_rate_at(value: float) -> float:
        failures = sum(1 for _ in range(trials) if not run_at(value))
        rate = failures / trials
        search_points.append({"value": value, "failure_rate": rate, "passed": rate <= failure_rate_threshold})
        return rate

    safe_value = low
    failure_value = high

    while (failure_value - safe_value) > precision:
        mid = (safe_value + failure_value) / 2
        if failure_rate_at(mid) > failure_rate_threshold:
            failure_value = mid
        else:
            safe_value = mid

    return ThresholdResult(
        parameter=parameter,
        safe_value=safe_value,
        failure_value=failure_value,
        boundary_estimate=(safe_value + failure_value) / 2,
        search_points=search_points,
    )
