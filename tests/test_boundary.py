"""morph.engine.boundary: probabilistic bisection with a noisy oracle."""

import math
import random

import pytest

from morph.engine.boundary import BoundaryPosterior, locate_boundary


def noisy_oracle(theta: float, floor: float = 0.05, ceiling: float = 0.75, scale: float = 8.0, seed: int = 1):
    rng = random.Random(seed)

    def run_at(x: float) -> bool:
        p = floor + (ceiling - floor) / (1.0 + math.exp(-(x - theta) / scale))
        return rng.random() > p

    return run_at


def test_posterior_starts_uniform_and_in_range():
    post = BoundaryPosterior(low=0.0, high=100.0, grid_size=50)
    lo, hi = post.credible_interval(0.9)
    assert lo < 10.0 and hi > 90.0
    probs = post.probabilities()
    assert probs["boundary_in_range"] == pytest.approx(0.8, abs=1e-9)


def test_posterior_rejects_bad_range():
    with pytest.raises(ValueError):
        BoundaryPosterior(low=5.0, high=5.0)


@pytest.mark.parametrize("theta", [50.0, 150.0, 250.0])
def test_locates_a_noisy_boundary_within_its_credible_interval(theta):
    events = []
    result = locate_boundary(
        "network.latency_ms", noisy_oracle(theta, seed=int(theta)), 0.0, 300.0,
        max_trials=45, on_event=events.append,
    )
    assert result.method == "probabilistic_bisection"
    assert result.boundary_estimate is not None
    assert result.credible_low <= theta + 25 and result.credible_high >= theta - 25
    assert abs(result.boundary_estimate - theta) < 40
    assert result.probability_boundary_in_range > 0.9
    assert result.trials == len(result.search_points) <= 45
    kinds = [e.kind for e in events]
    assert kinds[0] == "phase_start" and kinds[-1] == "phase_done"
    assert kinds.count("search_probe") == result.trials
    assert len(result.posterior) == 256 and len(result.dose_response) == 40


def test_never_failing_app_reports_no_boundary_instead_of_fabricating_one():
    result = locate_boundary("network.latency_ms", lambda x: True, 0.0, 300.0, max_trials=40)
    assert result.boundary_estimate is None
    assert result.credible_low is None and result.credible_high is None
    assert result.safe_value == 300.0 and result.failure_value is None
    assert result.probability_never_fails > 0.5
    assert result.trials < 40  # gave up early once the evidence was clear


def test_always_failing_app_reports_boundary_below_range():
    result = locate_boundary("network.latency_ms", lambda x: False, 0.0, 300.0, max_trials=40)
    assert result.boundary_estimate is None
    assert result.failure_value == 0.0 and result.safe_value is None
    assert result.probability_always_fails > 0.5


def test_stops_when_precise_enough():
    result = locate_boundary(
        "x", noisy_oracle(100.0, floor=0.0, ceiling=1.0, scale=0.5, seed=3), 0.0, 200.0,
        max_trials=60, precision=40.0,
    )
    assert result.trials < 60
    assert result.credible_high - result.credible_low <= 40.0


def test_decreasing_parameter_is_searched_in_real_units():
    """A file-descriptor limit hurts when it gets SMALLER: the boundary must
    still come back in real units with the credible interval the right way round."""
    rng = random.Random(9)

    def fd_oracle(limit: float) -> bool:  # fails below ~100 handles
        p = 0.05 + 0.85 / (1.0 + math.exp((limit - 100.0) / 5.0))
        return rng.random() > p

    events = []
    result = locate_boundary("process.fd_limit", fd_oracle, 16.0, 512.0, max_trials=40,
                             increasing=False, on_event=events.append)
    assert result.outcome == "boundary_found"
    assert 60 < result.boundary_estimate < 140
    assert result.credible_low < result.boundary_estimate < result.credible_high
    assert 16.0 <= result.credible_low and result.credible_high <= 512.0
    assert all(16.0 <= sp.value <= 512.0 for sp in result.search_points)
    values = [pt["value"] for pt in result.posterior]
    assert values == sorted(values) and values[0] >= 16.0
    probes = [e for e in events if e.kind == "search_probe"]
    assert all(16.0 <= e.param_value <= 512.0 for e in probes)
    assert all(e.safe_value <= e.failure_value for e in probes if e.safe_value is not None)
