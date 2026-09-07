"""Statistical comparison results: baseline vs. treatment, and threshold search."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ComparisonResult(BaseModel):
    condition_label: str = ""
    baseline_failures: int = 0
    baseline_total: int = 0
    treatment_failures: int = 0
    treatment_total: int = 0
    p_value: float | None = None
    is_significant: bool = False
    effect_label: str = "no_effect"  # "no_effect" | "significant_increase" | "significant_decrease"
    baseline: Any = None
    treatment: Any = None

    def model_post_init(self, __context: Any) -> None:
        if self.baseline is not None and hasattr(self.baseline, "failures") and self.baseline_total == 0:
            self.baseline_failures = self.baseline.failures
            self.baseline_total = self.baseline.total_runs
        if self.treatment is not None and hasattr(self.treatment, "failures") and self.treatment_total == 0:
            self.treatment_failures = self.treatment.failures
            self.treatment_total = self.treatment.total_runs
            if not self.condition_label and hasattr(self.treatment, "condition_label"):
                self.condition_label = self.treatment.condition_label

    @property
    def baseline_failure_rate(self) -> float:
        return self.baseline_failures / self.baseline_total if self.baseline_total else 0.0

    @property
    def treatment_failure_rate(self) -> float:
        return self.treatment_failures / self.treatment_total if self.treatment_total else 0.0


class ThresholdResult(BaseModel):
    parameter: str
    safe_value: float | None = None
    failure_value: float | None = None
    boundary_estimate: float | None = None
    search_points: list[dict] = []

