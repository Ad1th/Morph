"""FastAPI router for 2D Failure Surface Heatmap, Differential Blame, and Invariant Exporter."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import morph
from morph.engine.blame import analyze_differential_blame
from morph.engine.exporter import generate_invariant_test_code
from morph.engine.surface import compute_failure_surface
from morph.schema.blame import DifferentialBlameResult
from morph.schema.surface import SurfaceRequest, SurfaceResult

router = APIRouter()
REPO_ROOT = Path(morph.__file__).resolve().parent.parent


class BlameRequest(BaseModel):
    pass_output: str
    fail_output: str
    pass_param_label: str = "170ms"
    fail_param_label: str = "185ms"
    project_path: str | None = None


class ExportInvariantRequest(BaseModel):
    project_name: str = "service"
    command: str = "py -3 -m apps.timeout test"
    safe_latency_ms: float = 160.0
    safe_packet_loss: float = 0.01
    safe_cpu_quota: float = 1.0
    param_name: str = "network.latency_ms"
    boundary_estimate: float | None = 180.0
    divergence_summary: str | None = None


class ExportInvariantResponse(BaseModel):
    filename: str = "test_morph_invariant.py"
    code: str
    summary: str


@router.post("/surface", response_model=SurfaceResult)
def run_surface_heatmap(req: SurfaceRequest) -> SurfaceResult:
    """Compute 2D failure surface grid matrix across two environment dimensions."""
    try:
        return compute_failure_surface(req, repo_root=REPO_ROOT)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to generate 2D failure surface: {exc}")


@router.post("/blame", response_model=DifferentialBlameResult)
def run_differential_blame(req: BlameRequest) -> DifferentialBlameResult:
    """Analyze differential code blame between passing and failing traces."""
    try:
        proj_dir = Path(req.project_path) if req.project_path else None
        if proj_dir and not proj_dir.is_absolute():
            proj_dir = (REPO_ROOT / proj_dir).resolve()
        return analyze_differential_blame(
            pass_output=req.pass_output,
            fail_output=req.fail_output,
            pass_param_label=req.pass_param_label,
            fail_param_label=req.fail_param_label,
            project_dir=proj_dir,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to analyze differential blame: {exc}")


@router.post("/export/invariant", response_model=ExportInvariantResponse)
def export_invariant_guardrail(req: ExportInvariantRequest) -> ExportInvariantResponse:
    """Generate an executable test_morph_invariant.py regression test file."""
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
