"""FastAPI routes for executing processes under simulated conditions."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from morph.api import defaults, service
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult

router = APIRouter()


class RunRequest(BaseModel):
    command: str = Field(min_length=1, description="Shell-style command line")
    profile: EnvironmentProfile | None = None
    timeout: float = Field(defaults.TIMEOUT_SEC, gt=0)
    cwd: str | None = None
    force_proxy: bool = False
    # Only used on the no-profile path below; with a profile, env vars come
    # from profile.env_vars (the Environment Variables editor screen) via
    # RuntimeController.run().
    env_overrides: dict[str, str] = Field(default_factory=dict)
    # Where the run executes. Only the host machine is wired up; a remote
    # target is rejected outright rather than silently run locally.
    target: str = "local"


@router.post(
    "",
    response_model=RunResult,
    summary="Run a command once under a profile",
    responses={
        400: {"description": "Unsupported run target or empty command"},
        422: {"description": "The command cannot launch (setup error): missing binary, bad cwd"},
    },
)
def execute_run(req: RunRequest) -> RunResult:
    """Execute a single run of a command under an environment profile.

    A run that *fails* returns 200 with ``passed: false``; a run that never
    starts (``exit_code`` 126/127, ``FileNotFoundError``) is a **422** so it is
    never mistaken for an application failure.
    """
    if req.target != "local":
        raise HTTPException(
            status_code=400,
            detail=f"Run target '{req.target}' is not available. Only 'local' is supported "
            "until a remote host is configured.",
        )
    if not req.command.strip():
        raise HTTPException(status_code=400, detail="command is empty")

    from morph.runtime.controller import RuntimeController

    controller = RuntimeController(force_proxy=req.force_proxy)
    try:
        if req.profile is not None:
            result = controller.run(
                profile=req.profile, command=req.command, timeout=req.timeout, cwd=req.cwd
            )
        else:
            from morph.runtime.runner import execute_command

            result = execute_command(
                command=req.command,
                env_overrides=req.env_overrides,
                timeout=req.timeout,
                cwd=req.cwd,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if service.is_setup_error(result):
        raise HTTPException(
            status_code=422, detail=service.setup_error_message(result, req.command, req.cwd)
        )
    return result
