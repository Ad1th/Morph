from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult


class TrialBatch(BaseModel):
    condition_label: str          # e.g. "baseline", "latency_180ms", "loss_2pct", "latency+loss"
    profile_overrides: Dict[str, Any] = Field(default_factory=dict)
    total_runs: int
    failures: int
    failure_rate: float
    run_results: List[RunResult] = Field(default_factory=list)


class ComparisonResult(BaseModel):
    baseline: TrialBatch
    treatment: TrialBatch
    p_value: Optional[float] = None
    is_significant: bool = False
    effect_label: str = "no_effect" # "no_effect" | "significant_increase" | "significant_decrease"


class ThresholdResult(BaseModel):
    parameter: str                # e.g. "network.latency_ms"
    safe_value: float             # Highest value that passes
    failure_value: float          # Lowest value that fails
    boundary_estimate: float      # Estimated boundary
    search_points: List[Dict[str, Any]] = Field(default_factory=list)


class ExperimentConfig(BaseModel):
    profile_id: Optional[str] = None
    target_profile: Optional[EnvironmentProfile] = None
    command: str
    trials: int = 5
    parameters: Optional[List[str]] = None
    timeout_sec: float = 30.0


class ExperimentResult(BaseModel):
    experiment_id: str
    target_profile: EnvironmentProfile
    comparisons: List[ComparisonResult] = Field(default_factory=list)
    interactions: List[ComparisonResult] = Field(default_factory=list)
    thresholds: List[ThresholdResult] = Field(default_factory=list)
    classification: str = "unknown" # "environment_caused" | "environment_exposed" | "application_internal"
    strongest_condition: str = ""
    summary: str = ""
