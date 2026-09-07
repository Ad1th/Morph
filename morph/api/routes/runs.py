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
    # Where the run executes: "local" or "cloud". Anything else is rejected
    # outright rather than silently run locally -- a run that quietly lands on
    # the wrong machine is worse than one that refuses.
    target: str = "local"


@router.post("", response_model=RunResult)
def execute_run(req: RunRequest) -> RunResult:
    """Execute a single run of a command under an environment profile."""
    if req.target == "cloud":
        return _run_on_worker(req)

    if req.target != "local":
        raise HTTPException(
            status_code=400,
            detail=f"Run target '{req.target}' is not available. "
            "Supported targets are 'local' and 'cloud'.",
        )
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


def _run_on_worker(req: RunRequest) -> RunResult:
    """Execute this run on the configured cloud worker.

    Note this is NOT run_anywhere(): that routes to a worker only when the
    profile outgrows this host, which is the right rule when Morph is choosing.
    Here the user chose. Picking "Cloud worker" and silently getting a local run
    because the profile happened to fit would misreport where the evidence came
    from, so an explicit cloud target always goes to the worker or fails.

    `cwd` is deliberately not forwarded: it is a path on this machine, and the
    worker runs out of its own checkout (cloud.workdir).
    """
    from morph.cloud.worker import RemoteWorker, WorkerUnavailable
    from morph.config import load_config

    if req.profile is None:
        raise HTTPException(
            status_code=400,
            detail="A cloud run needs a profile: the worker reproduces conditions, "
            "and without one there is nothing to reproduce.",
        )

    worker = RemoteWorker(load_config().cloud)
    if not worker.configured:
        raise HTTPException(
            status_code=400,
            detail="No cloud worker is configured. Set cloud.host in morph.yaml, "
            "or MORPH_CLOUD_HOST in the environment.",
        )
    try:
        return worker.run(profile=req.profile, command=req.command, timeout=req.timeout)
    except WorkerUnavailable as exc:
        # 502, not 500: the worker failed, not this server. The distinction is
        # what tells the user to go look at the box rather than at Morph.
        raise HTTPException(status_code=502, detail=f"Cloud worker unavailable: {exc}")
