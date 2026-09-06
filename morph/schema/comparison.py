"""Statistical comparison results: baseline vs. treatment, and threshold search."""


from pydantic import BaseModel


class ComparisonResult(BaseModel):
    condition_label: str
    baseline_failures: int
    baseline_total: int
    treatment_failures: int
    treatment_total: int
    p_value: float | None = None
    is_significant: bool
    effect_label: str  # "no_effect" | "significant_increase" | "significant_decrease"

    @property
    def baseline_failure_rate(self) -> float:
        return self.baseline_failures / self.baseline_total if self.baseline_total else 0.0

    @property
    def treatment_failure_rate(self) -> float:
        return self.treatment_failures / self.treatment_total if self.treatment_total else 0.0


class ThresholdResult(BaseModel):
    parameter: str
    safe_value: float
    failure_value: float
    boundary_estimate: float
    search_points: list[dict]
