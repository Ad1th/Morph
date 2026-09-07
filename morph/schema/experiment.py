"""ExperimentConfig and ExperimentResult: aggregated outcomes of a full experiment run.

``TrialBatch`` is defined in :mod:`morph.schema.trials` and re-exported here.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from morph.schema.comparison import ComparisonResult, ThresholdResult
from morph.schema.profile import EnvironmentProfile
from morph.schema.trials import TrialBatch

Classification = Literal[
    "environment_caused",     # baseline clean, treatment significantly worse
    "environment_exposed",    # baseline has some failures, treatment amplifies them
    "application_internal",   # baseline already fails often regardless of environment
    "no_effect",              # no candidate produced a significant increase
    "unknown",
]


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
    classification: Classification = "unknown"
    strongest_condition: str = ""
    summary: str = ""
    # Honesty notes a UI must show next to the verdict, e.g. "n=3 can never
    # reach significance". Empty when nothing needs saying.
    warnings: list[str] = Field(default_factory=list)


__all__ = ["Classification", "ExperimentConfig", "ExperimentResult", "TrialBatch"]
