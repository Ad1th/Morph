"""FastAPI route for the minimal failing condition set (ddmin over conditions)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from morph.api import defaults, service
from morph.schema.profile import EnvironmentProfile

router = APIRouter()


class MinimizeRequest(BaseModel):
    """Which of the target's deviations are actually needed for the failure?

    ``conditions`` defaults to every profile field the target deviates in from
    the host (network latency/loss, CPU, memory, locale, process limits).
    Each candidate subset is run ``runs`` times; it "fails" when the failure
    rate exceeds ``failure_rate_threshold``.
    """

    command: str = Field(min_length=1)
    target_profile: EnvironmentProfile
    conditions: list[str] | None = None
    cwd: str | None = None
    timeout: float = Field(defaults.TIMEOUT_SEC, gt=0)
    runs: int = Field(3, ge=1)
    failure_rate_threshold: float = Field(0.5, ge=0, lt=1)


class MinimizeResponse(BaseModel):
    conditions: list[str]
    minimal: list[str]
    reproduced: bool
    oracle_calls: int
    history: list[dict[str, Any]]
    summary: str


@router.post(
    "",
    response_model=MinimizeResponse,
    summary="Find the minimal set of conditions that reproduces the failure",
    responses={
        400: {"description": "Unknown condition or nothing deviates from the host"},
        422: {"description": "Invalid request or the command cannot launch (setup error)"},
    },
)
def minimize(req: MinimizeRequest) -> MinimizeResponse:
    """Delta debugging (ddmin) over the target's deviating conditions: returns a
    1-minimal subset that still fails, plus every subset tried."""
    spec = service.MinimizeSpec(
        command=req.command,
        target_profile=req.target_profile,
        conditions=req.conditions,
        cwd=req.cwd,
        timeout=req.timeout,
        runs=req.runs,
        failure_rate_threshold=req.failure_rate_threshold,
    )
    try:
        outcome = service.run_minimize(spec)
    except service.setup_error_types() as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return MinimizeResponse(**outcome.to_dict())
