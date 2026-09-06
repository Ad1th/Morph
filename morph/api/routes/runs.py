"""FastAPI routes for executing processes under simulated conditions."""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.runtime.controller import RuntimeController
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult

router = APIRouter()


class RunRequest(BaseModel):
    command: str
    profile: Optional[EnvironmentProfile] = None
    timeout: float = 30.0
    cwd: Optional[str] = None
    force_proxy: bool = False


@router.post("", response_model=RunResult)
def execute_run(req: RunRequest) -> RunResult:
    """Execute a single run of a command under an environment profile."""
    controller = RuntimeController(force_proxy=req.force_proxy)
    try:
        if req.profile is not None:
            return controller.run(
                profile=req.profile,
                command=req.command,
                timeout=req.timeout,
                cwd=req.cwd,
            )
        else:
            from morph.runtime.runner import execute_command
            return execute_command(
                command=req.command,
                timeout=req.timeout,
                cwd=req.cwd,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution error: {exc}")
