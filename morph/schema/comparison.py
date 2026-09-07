"""Statistical comparison results: baseline vs. treatment, and threshold search."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from morph.schema.trials import TrialBatch

EffectLabel = Literal["no_effect", "significant_increase", "significant_decrease"]

# How a ComparisonResult's decision was reached.
#   "fisher":         one one-sided Fisher exact test on a fixed batch.
#   "fisher_holm":    the same, with Holm-Bonferroni across every candidate in the
#                     experiment (is_significant is then family-wise honest).
#   "paired_e_value": sequential, anytime-valid (morph.engine.anytime).
ComparisonMethod = Literal["fisher", "fisher_holm", "paired_e_value"]

# What a threshold search concluded about the range it was given.
ThresholdOutcome = Literal["boundary_found", "never_fails", "always_fails", "inconclusive"]
ThresholdMethod = Literal["bisection", "probabilistic_bisection"]


class ComparisonResult(BaseModel):
    """One treatment condition against the baseline.

    ``p_value`` is always the one-sided Fisher p for H1 "the treatment fails
    MORE often than baseline" (or the anytime-valid p in sequential mode);
    ``p_value_decrease`` is the mirror-image one-sided p, used only to label a
    ``significant_decrease`` (fix verification). ``risk_difference`` is
    ``treatment rate - baseline rate`` with a 95 % Newcombe hybrid-score
    interval in ``risk_difference_ci``.
    """

    condition_label: str = ""
    baseline_failures: int = 0
    baseline_total: int = 0
    treatment_failures: int = 0
    treatment_total: int = 0
    p_value: float | None = None
    is_significant: bool = False
    effect_label: EffectLabel = "no_effect"
    baseline: TrialBatch | None = None
    treatment: TrialBatch | None = None

    method: ComparisonMethod = "fisher"
    alpha: float = 0.05
    p_value_decrease: float | None = None    # one-sided p for "treatment fails less"
    p_value_adjusted: float | None = None    # Holm-adjusted p, when method == "fisher_holm"
    e_value: float | None = None             # final e-value, when method == "paired_e_value"
    pairs: int | None = None                 # matched pairs run, when sequential
    stopped_early: bool | None = None        # sequential mode stopped before its budget
    risk_difference: float | None = None     # treatment rate - baseline rate
    risk_difference_ci: tuple[float, float] | None = None  # 95 % Newcombe interval

    def model_post_init(self, __context: Any) -> None:
        # Convenience: counts default to the embedded batches when the caller
        # gave batches but no explicit counts.
        if self.baseline is not None and "baseline_total" not in self.model_fields_set:
            self.baseline_failures = self.baseline.failures
            self.baseline_total = self.baseline.total_runs
        if self.treatment is not None and "treatment_total" not in self.model_fields_set:
            self.treatment_failures = self.treatment.failures
            self.treatment_total = self.treatment.total_runs
            if not self.condition_label:
                self.condition_label = self.treatment.condition_label

    @property
    def baseline_failure_rate(self) -> float:
        return self.baseline_failures / self.baseline_total if self.baseline_total else 0.0

    @property
    def treatment_failure_rate(self) -> float:
        return self.treatment_failures / self.treatment_total if self.treatment_total else 0.0


class SearchPoint(BaseModel):
    """One value a threshold search evaluated."""

    value: float
    failure_rate: float | None = None
    passed: bool | None = None


class ThresholdResult(BaseModel):
    """Where along one parameter failures begin.

    ``method`` is ``"bisection"`` (deterministic halving, majority vote per
    probe; :func:`morph.engine.threshold.search_threshold`) or
    ``"probabilistic_bisection"`` (Bayesian, noise-aware;
    :func:`morph.engine.boundary.locate_boundary`). For the latter
    ``safe_value`` / ``failure_value`` are the bounds of the ``credible_mass``
    interval and ``boundary_estimate`` its posterior median.

    ``outcome`` says what the search concluded: ``boundary_found`` (a boundary
    lies inside ``[low, high]``), ``never_fails`` / ``always_fails`` (the whole
    range passed / failed, so no boundary is reported), or ``inconclusive``.
    ``boundary_estimate`` is ``None`` unless ``outcome == "boundary_found"``.
    For plain bisection the bracket ``failure_value - safe_value <= precision``
    is only as trustworthy as the majority vote at each probe: on a flaky
    application it fabricates precision (see ``morph.engine.boundary``).
    """

    parameter: str
    safe_value: float | None = None
    failure_value: float | None = None
    boundary_estimate: float | None = None
    search_points: list[SearchPoint] = Field(default_factory=list)

    outcome: ThresholdOutcome = "inconclusive"
    method: ThresholdMethod = "bisection"
    trials: int | None = None                 # bisection: trials per probe; PB: total trials
    credible_mass: float | None = None
    credible_low: float | None = None
    credible_high: float | None = None
    probability_boundary_in_range: float | None = None
    probability_never_fails: float | None = None
    probability_always_fails: float | None = None
    floor_failure_rate: float | None = None
    ceiling_failure_rate: float | None = None
    posterior: list[dict] = Field(default_factory=list)
    dose_response: list[dict] = Field(default_factory=list)
