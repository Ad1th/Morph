"""FastAPI routes for executing processes under simulated conditions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.runtime.controller import RuntimeController
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult

router = APIRouter()


class RunRequest(BaseModel):
    command: str
    profile: EnvironmentProfile | None = None
    timeout: float = 30.0
    cwd: str | None = None
    force_proxy: bool = False
    # Only used on the no-profile path below; with a profile, env vars come
    # from profile.env_vars (the Environment Variables editor screen) via
    # RuntimeController.run().
    env_overrides: dict[str, str] = {}


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
                env_overrides=req.env_overrides,
                timeout=req.timeout,
                cwd=req.cwd,
            )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution error: {exc}")
