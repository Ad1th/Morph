"""TrialBatch and ExperimentResult: aggregated outcomes of a full experiment run."""

from pydantic import BaseModel

from morph.schema.comparison import ComparisonResult, ThresholdResult
from morph.schema.telemetry import RunResult


class TrialBatch(BaseModel):
    condition_label: str
    profile_overrides: dict = {}
    total_runs: int
    failures: int
    run_results: list[RunResult] = []

    @property
    def failure_rate(self) -> float:
        return self.failures / self.total_runs if self.total_runs else 0.0


class ExperimentResult(BaseModel):
    baseline: TrialBatch
    comparisons: list[ComparisonResult] = []
    interactions: list[ComparisonResult] = []
    thresholds: list[ThresholdResult] = []
    classification: str  # "environment_caused" | "environment_exposed" | "application_internal"
    strongest_condition: str
    summary: str
