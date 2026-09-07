"""FastAPI route for the parameter threshold search.

Thin glue only: the binary search lives in `morph.engine.threshold` and the
per-trial runner in `morph.engine.runners`, and both are shared with the
`morph threshold` CLI command so the two entry points search identically.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.engine.runners import (
    make_threshold_run_fn,
    set_profile_parameter,
    with_unconstrained_network,
)
from morph.engine.threshold import search_threshold
from morph.profiler.capture import capture_environment
from morph.schema.comparison import ThresholdResult
from morph.schema.profile import EnvironmentProfile

router = APIRouter()


class ThresholdRequest(BaseModel):
    command: str
    parameter: str
    low: float = 0.0
    high: float = 500.0
    trials: int = 3
    precision: float = 10.0
    profile: EnvironmentProfile | None = None
    cwd: str | None = None
    timeout: float = 30.0
    target: str = "local"


@router.post("", response_model=ThresholdResult)
def find_threshold(req: ThresholdRequest) -> ThresholdResult:
    """Binary-search the failure boundary of one environment parameter."""
    if req.target != "local":
        raise HTTPException(
            status_code=400,
            detail=f"Run target '{req.target}' is not available. Only 'local' is supported "
            "until a remote host is configured.",
        )
    if req.trials < 1:
        raise HTTPException(status_code=400, detail="'trials' must be at least 1")
    if req.precision <= 0:
        raise HTTPException(status_code=400, detail="'precision' must be greater than 0")
    if req.high <= req.low:
        raise HTTPException(status_code=400, detail="'high' must be greater than 'low'")

    base = req.profile
    if base is None:
        try:
            base = capture_environment()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Failed to capture host profile: {exc}")

    # Same treatment either way: a profile edited in the UI comes back with the
    # same `network: null` the capture produced, so filling the absent section
    # here is what lets a user-supplied profile drive the search at all.
    base = with_unconstrained_network(base)

    # Fail on an unknown parameter before spending any trial runs on it.
    try:
        set_profile_parameter(base, req.parameter, req.low)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    run_at = make_threshold_run_fn(
        command=req.command,
        profile=base,
        parameter=req.parameter,
        timeout=req.timeout,
        cwd=req.cwd,
    )

    try:
        return search_threshold(
            parameter=req.parameter,
            run_at=run_at,
            low=req.low,
            high=req.high,
            trials=req.trials,
            precision=req.precision,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Threshold search error: {exc}")
