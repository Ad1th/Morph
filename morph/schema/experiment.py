"""TrialBatch and ExperimentResult: aggregated outcomes of a full experiment run."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from morph.schema.comparison import ComparisonResult, ThresholdResult
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult


class TrialBatch(BaseModel):
    condition_label: str
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    total_runs: int
    failures: int
    failure_rate: float | None = None
    run_results: list[RunResult] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if self.failure_rate is None:
            self.failure_rate = self.failures / self.total_runs if self.total_runs else 0.0


class ExperimentConfig(BaseModel):
    profile_id: str | None = None
    target_profile: EnvironmentProfile | None = None
    command: str
    trials: int = 5
    parameters: list[str] | None = None
    timeout_sec: float = 30.0


class ExperimentResult(BaseModel):
    experiment_id: str = ""
    target_profile: EnvironmentProfile | None = None
    baseline: TrialBatch | None = None
    comparisons: list[ComparisonResult] = Field(default_factory=list)
    interactions: list[ComparisonResult] = Field(default_factory=list)
    thresholds: list[ThresholdResult] = Field(default_factory=list)
    classification: str = "unknown"  # "environment_caused" | "environment_exposed" | "application_internal"
    strongest_condition: str = ""
    summary: str = ""
