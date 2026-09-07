"""Pydantic schemas for 2D failure surface mapping."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from morph.schema.blame import DifferentialBlameResult


class SurfaceGridPoint(BaseModel):
    x: float
    y: float
    passed: bool
    failure_rate: float = 0.0
    runs: int = 1
    exit_code: int | None = 0
    duration_ms: float | None = None
    stdout: str | None = None
    stderr: str | None = None


class SurfaceRequest(BaseModel):
    project_path: str
    command: str | None = None
    cwd: str | None = None
    param_x: str = "network.latency_ms"
    param_y: str = "network.packet_loss_percent"
    x_values: list[float] | None = None
    y_values: list[float] | None = None
    x_min: float | None = 50.0
    x_max: float | None = 300.0
    x_steps: int | None = 6
    y_min: float | None = 0.0
    y_max: float | None = 5.0
    y_steps: int | None = 6
    runs_per_point: int = 1
    # A point "passes" when its failure rate is <= this (same rule as the
    # threshold search), so the two tools agree on what passing means.
    failure_rate_threshold: float = 0.5
    # "proxy" (environment variables only), "system" (host-native adapter),
    # or an explicit "macos" / "linux" / "windows".
    adapter_name: str = "proxy"
    timeout: float = 30.0
    supplied_profile: dict[str, Any] | None = None


class SafeBoundaryPoint(BaseModel):
    x: float
    y: float
    status: Literal["safe", "boundary", "failing"] = "boundary"


class SurfaceResult(BaseModel):
    param_x: str
    param_y: str
    param_x_label: str
    param_y_label: str
    param_x_unit: str = ""
    param_y_unit: str = ""
    x_values: list[float]
    y_values: list[float]
    grid: list[list[SurfaceGridPoint]] = Field(default_factory=list)
    points: list[SurfaceGridPoint] = Field(default_factory=list)
    safe_boundary: list[SafeBoundaryPoint] = Field(default_factory=list)
    passing_count: int = 0
    failing_count: int = 0
    total_points: int = 0
    highest_passing_point: SurfaceGridPoint | None = None
    lowest_failing_point: SurfaceGridPoint | None = None
    blame: DifferentialBlameResult | None = None
    summary: str = ""
