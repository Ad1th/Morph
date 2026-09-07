"""FastAPI router for 2D Failure Surface Heatmap, Differential Blame, and Invariant Exporter."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import morph
from morph.schema.blame import DifferentialBlameResult
from morph.schema.surface import SurfaceRequest, SurfaceResult

router = APIRouter()
REPO_ROOT = Path(morph.__file__).resolve().parent.parent

#: Every grid point runs `runs_per_point` subprocesses synchronously in the
#: request thread; cap the grid so one request cannot pin the server.
MAX_STEPS = 20
MAX_RUNS_PER_POINT = 10
MAX_GRID_RUNS = 400


class BlameRequest(BaseModel):
    pass_output: str = Field(min_length=1)
    fail_output: str = Field(min_length=1)
    pass_param_label: str = "170ms"
    fail_param_label: str = "185ms"
    project_path: str | None = None


class ExportInvariantRequest(BaseModel):
    project_name: str = "service"
    command: str = Field(min_length=1)
    safe_latency_ms: float = 160.0
    safe_packet_loss: float = Field(1.0, ge=0, le=100, description="Percent")
    safe_cpu_quota: float = 1.0
    param_name: str = "network.latency_ms"
    boundary_estimate: float | None = None
    divergence_summary: str | None = None


class ExportInvariantResponse(BaseModel):
    filename: str = "test_morph_invariant.py"
    code: str
    summary: str


def _check_grid(req: SurfaceRequest) -> None:
    xs = len(req.x_values) if req.x_values else (req.x_steps or 0)
    ys = len(req.y_values) if req.y_values else (req.y_steps or 0)
    if xs < 1 or ys < 1:
        raise HTTPException(status_code=422, detail="the grid needs at least one x and one y value")
    if xs > MAX_STEPS or ys > MAX_STEPS:
        raise HTTPException(status_code=422, detail=f"at most {MAX_STEPS} steps per axis")
    if req.runs_per_point < 1 or req.runs_per_point > MAX_RUNS_PER_POINT:
        raise HTTPException(
            status_code=422, detail=f"runs_per_point must be in 1..{MAX_RUNS_PER_POINT}"
        )
    if xs * ys * req.runs_per_point > MAX_GRID_RUNS:
        total = xs * ys * req.runs_per_point
        raise HTTPException(
            status_code=422, detail=f"grid would run {total} trials; max {MAX_GRID_RUNS}"
        )


@router.post(
    "/surface",
    response_model=SurfaceResult,
    summary="Compute a 2D failure surface",
    responses={422: {"description": "Grid too large or empty"}},
)
def run_surface_heatmap(req: SurfaceRequest) -> SurfaceResult:
    """Compute the failure-rate grid across two environment dimensions
    (at most 20x20 points, 400 trials per request)."""
    from morph.engine.surface import compute_failure_surface

    _check_grid(req)
    try:
        return compute_failure_surface(req, repo_root=REPO_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/blame",
    response_model=DifferentialBlameResult,
    summary="Differential blame between a passing and a failing trace",
)
def run_differential_blame(req: BlameRequest) -> DifferentialBlameResult:
    """Diff a passing and a failing trace to point at the first divergent frame.
    Both traces are required: nothing is invented from empty input."""
    from morph.engine.blame import analyze_differential_blame

    proj_dir = Path(req.project_path) if req.project_path else None
    if proj_dir and not proj_dir.is_absolute():
        proj_dir = (REPO_ROOT / proj_dir).resolve()
    try:
        return analyze_differential_blame(
            pass_output=req.pass_output,
            fail_output=req.fail_output,
            pass_param_label=req.pass_param_label,
            fail_param_label=req.fail_param_label,
            project_dir=proj_dir,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/export/invariant",
    response_model=ExportInvariantResponse,
    summary="Generate a pytest guardrail from a safe operating point",
)
def export_invariant_guardrail(req: ExportInvariantRequest) -> ExportInvariantResponse:
    """Generate an executable ``test_morph_invariant.py`` regression test file."""
    from morph.engine.exporter import generate_invariant_test_code

    code = generate_invariant_test_code(
        project_name=req.project_name,
        command=req.command,
        safe_latency_ms=req.safe_latency_ms,
        safe_packet_loss=req.safe_packet_loss,
        safe_cpu_quota=req.safe_cpu_quota,
        param_name=req.param_name,
        boundary_estimate=req.boundary_estimate,
        divergence_summary=req.divergence_summary,
    )
    return ExportInvariantResponse(
        filename="test_morph_invariant.py",
        code=code,
        summary=f"Generated executable invariant guardrail for {req.project_name}.",
    )
