"""Pydantic schemas for 2D failure surface mapping."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


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
    adapter_name: str = "proxy"
    supplied_profile: dict[str, Any] | None = None


class SafeBoundaryPoint(BaseModel):
    x: float
    y: float
    status: str = "boundary"  # "safe" | "boundary" | "failing"


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
    blame: Any | None = None
    summary: str = ""
