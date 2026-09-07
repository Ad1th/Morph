"""Probabilistic bisection: locating a failure boundary with a flaky oracle.

The problem with plain bisection
--------------------------------
`search_threshold` halves an interval and asks "does it fail here?". Real
applications answer that question noisily: a timeout that trips 70 % of the
time at 200 ms and 5 % of the time at 100 ms. Plain bisection treats each
majority vote as ground truth, so one unlucky batch sends the search into the
wrong half for good, and it then reports that wrong answer with confident
precision. It also cannot say *how sure* it is.

What this does instead
----------------------
Horstein's probabilistic bisection (1963), whose geometric convergence with a
noisy oracle was proved by Waeber, Frazier & Henderson (2013), keeps a
posterior distribution over where the boundary is and probes at its median.
Each single trial updates the posterior through an explicit response model, so
noise is *modelled* rather than voted away, and the answer is a credible
interval instead of a point.

The response model is the logistic dose-response curve used for psychometric
thresholds (Watson & Pelli's QUEST, 1983):

    P(fail | x)  =  floor + (ceiling - floor) * sigmoid((x - theta) / scale)

`theta` is the boundary we want. `floor` is the failure rate far below it
(flakiness that has nothing to do with the parameter), `ceiling` the rate far
above it (a fault that only bites 80 % of the time is still a fault). Rather
than guess those, the posterior is over a small grid of (theta, floor,
ceiling) triples and theta is marginalised out, so "how flaky is the app"
is learned from the same trials.

Two extra hypotheses guard against fabricated boundaries: "never fails in this
range" (P = floor everywhere) and "always fails in this range" (P = ceiling
everywhere). If either wins, no boundary is reported -- a fix for the failure
mode recorded in PROGRESS.md where every probe passed and a threshold was
still announced.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from morph.engine.progress import OnEvent, RunAtFn, emit, run_valid_trial
from morph.schema.comparison import SearchPoint, ThresholdOutcome, ThresholdResult
from morph.schema.events import TrialEvent

RunAt = RunAtFn  # may also return RunResult

FLOORS = (0.02, 0.10)
CEILINGS = (0.60, 0.85, 0.98)
NO_BOUNDARY_PRIOR = 0.10  # prior mass on "never fails here" and again on "always fails"


@dataclass
class BoundaryPosterior:
    """Posterior over the boundary location theta on a grid, marginalised over
    the nuisance floor/ceiling grid, plus the two no-boundary hypotheses."""

    low: float
    high: float
    grid_size: int = 256
    scale: float | None = None
    floors: tuple[float, ...] = FLOORS
    ceilings: tuple[float, ...] = CEILINGS
    no_boundary_prior: float = NO_BOUNDARY_PRIOR

    theta: np.ndarray = field(init=False)
    _log_post: np.ndarray = field(init=False)  # shape (T, F, C)
    _log_never_f: np.ndarray = field(init=False)  # "never fails in range", one entry per floor
    _log_always_c: np.ndarray = field(init=False)  # "always fails in range", one entry per ceiling
    observations: list[tuple[float, bool]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.high > self.low:
            raise ValueError("high must exceed low")
        self.theta = np.linspace(self.low, self.high, self.grid_size)
        if self.scale is None:
            self.scale = (self.high - self.low) / 25.0
        t, f, c = self.grid_size, len(self.floors), len(self.ceilings)
        in_range = 1.0 - 2.0 * self.no_boundary_prior
        self._log_post = np.full((t, f, c), np.log(in_range / (t * f * c)))
        self._log_never_f = np.full(f, np.log(self.no_boundary_prior / f))
        self._log_always_c = np.full(c, np.log(self.no_boundary_prior / c))

    # ------------------------------------------------------------ model

    def failure_probability(self, x: float) -> np.ndarray:
        """P(fail | x, theta, floor, ceiling) on the full grid, shape (T, F, C)."""
        z = (x - self.theta) / self.scale
        sig = 1.0 / (1.0 + np.exp(-np.clip(z, -60, 60)))
        fl = np.asarray(self.floors)[None, :, None]
        ce = np.asarray(self.ceilings)[None, None, :]
        return fl + (ce - fl) * sig[:, None, None]

    def update(self, x: float, failed: bool) -> None:
        p = self.failure_probability(x)
        like = p if failed else 1.0 - p
        self._log_post += np.log(np.clip(like, 1e-12, 1.0))
        fl = np.asarray(self.floors)
        ce = np.asarray(self.ceilings)
        self._log_never_f += np.log(np.clip(fl if failed else 1.0 - fl, 1e-12, 1.0))
        self._log_always_c += np.log(np.clip(ce if failed else 1.0 - ce, 1e-12, 1.0))
        self.observations.append((x, failed))

    # ------------------------------------------------------------ readouts

    def _normaliser(self) -> float:
        parts = np.concatenate(
            [self._log_post.ravel(), self._log_never_f, self._log_always_c]
        )
        m = parts.max()
        return float(m + np.log(np.exp(parts - m).sum()))

    def probabilities(self) -> dict[str, float]:
        """Posterior mass on: a boundary inside the range / never fails / always fails."""
        z = self._normaliser()
        return {
            "boundary_in_range": float(np.exp(self._log_post - z).sum()),
            "never_fails": float(np.exp(self._log_never_f - z).sum()),
            "always_fails": float(np.exp(self._log_always_c - z).sum()),
        }

    def density(self) -> np.ndarray:
        """Marginal posterior over theta, conditional on a boundary being in range."""
        lp = self._log_post
        m = lp.max()
        w = np.exp(lp - m).sum(axis=(1, 2))
        return w / w.sum()

    def quantile(self, q: float) -> float:
        cdf = np.cumsum(self.density())
        idx = int(np.searchsorted(cdf, q, side="left"))
        return float(self.theta[min(idx, self.grid_size - 1)])

    def median(self) -> float:
        return self.quantile(0.5)

    def credible_interval(self, mass: float = 0.9) -> tuple[float, float]:
        tail = (1.0 - mass) / 2.0
        return self.quantile(tail), self.quantile(1.0 - tail)

    def nuisance_estimate(self) -> tuple[float, float]:
        """Posterior-mean floor and ceiling, for reporting how flaky the app is."""
        lp = self._log_post
        w = np.exp(lp - lp.max())
        w /= w.sum()
        fl = float((w.sum(axis=(0, 2)) * np.asarray(self.floors)).sum())
        ce = float((w.sum(axis=(0, 1)) * np.asarray(self.ceilings)).sum())
        return fl, ce

    def dose_response(self, points: int = 40) -> list[dict]:
        """Posterior-mean P(fail | x) along the range: the curve a UI can draw."""
        lp = self._log_post
        w = np.exp(lp - lp.max())
        w /= w.sum()
        xs = np.linspace(self.low, self.high, points)
        out = []
        for x in xs:
            p_fail = float((self.failure_probability(x) * w).sum())
            out.append({"value": float(x), "failure_probability": p_fail})
        return out


def locate_boundary(
    parameter: str,
    run_at: RunAt,
    low: float,
    high: float,
    *,
    max_trials: int = 30,
    precision: float | None = None,
    credible_mass: float = 0.9,
    grid_size: int = 256,
    min_trials: int = 6,
    increasing: bool = True,
    on_event: OnEvent | None = None,
) -> ThresholdResult:
    """Probabilistic bisection for the value of ``parameter`` at which failures begin.

    ``increasing`` says which way the parameter hurts: ``True`` (latency,
    loss: more is worse) or ``False`` (a file-descriptor limit, memory: less
    is worse). A decreasing parameter is searched on its negation and every
    reported value is mapped back, so callers see real units either way.
    """
    if increasing:
        return _locate_increasing(
            parameter, run_at, low, high, max_trials=max_trials, precision=precision,
            credible_mass=credible_mass, grid_size=grid_size, min_trials=min_trials, on_event=on_event,
        )

    def flipped_event(event: TrialEvent) -> None:
        if on_event is None:
            return
        update: dict = {}
        if event.param_value is not None:
            update["param_value"] = -event.param_value
        if event.boundary_estimate is not None:
            update["boundary_estimate"] = -event.boundary_estimate
        # The credible band swaps ends when the axis is mirrored.
        lo, hi = event.safe_value, event.failure_value
        update["safe_value"] = -hi if hi is not None else None
        update["failure_value"] = -lo if lo is not None else None
        on_event(event.model_copy(update=update))

    inner = _locate_increasing(
        parameter, lambda u: run_at(-u), -high, -low, max_trials=max_trials, precision=precision,
        credible_mass=credible_mass, grid_size=grid_size, min_trials=min_trials, on_event=flipped_event,
    )
    neg = lambda v: None if v is None else -v  # noqa: E731
    return inner.model_copy(
        update={
            "boundary_estimate": neg(inner.boundary_estimate),
            "credible_low": neg(inner.credible_high),
            "credible_high": neg(inner.credible_low),
            # safe/failure keep their meaning (a value that passes / fails), only the sign flips.
            "safe_value": neg(inner.safe_value),
            "failure_value": neg(inner.failure_value),
            "search_points": [sp.model_copy(update={"value": -sp.value}) for sp in inner.search_points],
            "posterior": [{**pt, "value": -pt["value"]} for pt in reversed(inner.posterior)],
            "dose_response": [{**pt, "value": -pt["value"]} for pt in reversed(inner.dose_response)],
        }
    )


def _locate_increasing(
    parameter: str,
    run_at: RunAt,
    low: float,
    high: float,
    *,
    max_trials: int,
    precision: float | None,
    credible_mass: float,
    grid_size: int,
    min_trials: int,
    on_event: OnEvent | None,
) -> ThresholdResult:
    """Probabilistic bisection for the value of ``parameter`` at which failures begin.

    ``run_at(value)`` runs ONE trial and returns whether it passed (or a
    ``RunResult``). Stops when the ``credible_mass`` interval is narrower than
    ``precision`` (default: 2 % of the range) or after ``max_trials``.
    """
    if not high > low:
        raise ValueError(f"high ({high}) must exceed low ({low})")
    if max_trials < 1:
        raise ValueError(f"max_trials must be >= 1, got {max_trials}")
    if precision is None:
        precision = (high - low) * 0.02
    if not precision > 0:
        raise ValueError(f"precision must be > 0, got {precision}")
    post = BoundaryPosterior(low=low, high=high, grid_size=grid_size)
    emit(on_event, TrialEvent(kind="phase_start", phase="threshold", condition=parameter))
    search_points: list[SearchPoint] = []

    # Anchor the ends first: two trials at each bound tell the no-boundary
    # hypotheses apart from a genuine boundary far faster than bisection would.
    schedule = [low, high, high, low]
    trials = 0
    while trials < max_trials:
        x = schedule.pop(0) if schedule else post.median()
        passed, _result, _ms = run_valid_trial(
            lambda: run_at(x), parameter, on_event, trial_index=trials, param_value=float(x)
        )
        post.update(x, not passed)
        trials += 1

        lo, hi = post.credible_interval(credible_mass)
        med = post.median()
        probs = post.probabilities()
        search_points.append(SearchPoint(value=float(x), failure_rate=0.0 if passed else 1.0, passed=passed))
        emit(
            on_event,
            TrialEvent(
                kind="search_probe",
                phase="threshold",
                condition=parameter,
                param_value=float(x),
                failures=0 if passed else 1,
                total=1,
                failure_rate=0.0 if passed else 1.0,
                safe_value=lo,
                failure_value=hi,
                boundary_estimate=med,
                extra={"passed": passed, "trial": trials, **probs},
            ),
        )
        if trials >= min_trials and not schedule:
            if probs["boundary_in_range"] < 0.5:
                break
            if (hi - lo) <= precision:
                break

    probs = post.probabilities()
    floor, ceiling = post.nuisance_estimate()
    lo, hi = post.credible_interval(credible_mass)
    med = post.median()
    in_range = probs["boundary_in_range"] >= 0.5

    # Say what was concluded. A no-boundary verdict needs one of the two
    # no-boundary hypotheses to hold a majority on its own; otherwise the
    # evidence is split and nothing is reported as safe or failing.
    outcome: ThresholdOutcome
    if in_range:
        outcome = "boundary_found"
    elif probs["never_fails"] >= 0.5:
        outcome = "never_fails"
    elif probs["always_fails"] >= 0.5:
        outcome = "always_fails"
    else:
        outcome = "inconclusive"

    result = ThresholdResult(
        parameter=parameter,
        safe_value=lo if in_range else (high if outcome == "never_fails" else None),
        failure_value=hi if in_range else (low if outcome == "always_fails" else None),
        boundary_estimate=med if in_range else None,
        search_points=search_points,
        outcome=outcome,
        method="probabilistic_bisection",
        credible_mass=credible_mass,
        credible_low=lo if in_range else None,
        credible_high=hi if in_range else None,
        probability_boundary_in_range=probs["boundary_in_range"],
        probability_never_fails=probs["never_fails"],
        probability_always_fails=probs["always_fails"],
        floor_failure_rate=floor,
        ceiling_failure_rate=ceiling,
        trials=trials,
        posterior=[
            {"value": float(t), "density": float(d)}
            for t, d in zip(post.theta, post.density(), strict=True)
        ],
        dose_response=post.dose_response(),
    )
    emit(
        on_event,
        TrialEvent(
            kind="phase_done",
            phase="threshold",
            condition=parameter,
            safe_value=result.safe_value,
            failure_value=result.failure_value,
            boundary_estimate=result.boundary_estimate,
            extra={**probs, "trials": trials, "outcome": outcome},
        ),
    )
    return result
