"""FastAPI routes for the parameter threshold search (blocking and streaming).

Thin glue only: :func:`morph.api.service.run_threshold` builds the runner and
picks the engine (``bayes`` -> :func:`morph.engine.boundary.locate_boundary`,
``bisect`` -> :func:`morph.engine.threshold.search_threshold`), and the
`morph threshold` CLI command calls the same function, so both entry points
search identically.
"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator, model_validator

from morph.api import defaults, service
from morph.api.routes.experiments import jobs
from morph.api.routes.ws import manager
from morph.api.validation import IdPath
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent
from morph.schema.profile import EnvironmentProfile

router = APIRouter()


class ThresholdRequest(BaseModel):
    """Where along ``parameter`` does ``command`` start failing?

    ``method="bayes"`` (default) is probabilistic bisection: noise-aware, returns
    a credible interval and the probability that a boundary lies in the range
    at all. ``method="bisect"`` is deterministic halving with ``trials`` runs
    per probe. ``precision`` defaults to 2 % of ``high - low``.
    """

    command: str = Field(min_length=1)
    parameter: str = Field(description="Dotted profile field, e.g. network.latency_ms")
    low: float = defaults.THRESHOLD_LOW
    high: float = defaults.THRESHOLD_HIGH
    method: Literal["bayes", "bisect"] = defaults.DEFAULT_THRESHOLD_METHOD
    trials: int = Field(defaults.THRESHOLD_TRIALS, ge=1, description="Trials per probe (bisect)")
    max_trials: int = Field(
        defaults.THRESHOLD_MAX_TRIALS, ge=1, description="Total trial budget (bayes)"
    )
    precision: float | None = Field(None, gt=0, description="Stop width; default 2 % of range")
    credible_mass: float = Field(defaults.THRESHOLD_CREDIBLE_MASS, gt=0, lt=1)
    profile: EnvironmentProfile | None = None
    cwd: str | None = None
    timeout: float = Field(defaults.TIMEOUT_SEC, gt=0)
    target: str = "local"

    @field_validator("command")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command must not be empty")
        return value

    @model_validator(mode="after")
    def _range(self) -> ThresholdRequest:
        if self.high <= self.low:
            raise ValueError("'high' must be greater than 'low'")
        return self

    def to_spec(self) -> service.ThresholdSpec:
        return service.ThresholdSpec(
            command=self.command,
            parameter=self.parameter,
            low=self.low,
            high=self.high,
            profile=self.profile,
            cwd=self.cwd,
            timeout=self.timeout,
            method=self.method,
            trials=self.trials,
            precision=self.precision,
            max_trials=self.max_trials,
            credible_mass=self.credible_mass,
        )


def _check_target(req: ThresholdRequest) -> None:
    if req.target != "local":
        raise HTTPException(
            status_code=400,
            detail=f"Run target '{req.target}' is not available. Only 'local' is supported "
            "until a remote host is configured.",
        )


def _prepare(req: ThresholdRequest) -> service.ThresholdSpec:
    """Validate the spec and the parameter name before any trial is spent."""
    _check_target(req)
    spec = req.to_spec()
    try:
        spec.validate()
        base = service.with_unconstrained_network(req.profile) if req.profile else None
        if base is not None:
            service.set_profile_parameter(base, spec.parameter, spec.low)
        else:
            # No profile: the search captures the host; check the parameter
            # against a captured profile so an unknown name is a 400 not a run.
            from morph.profiler.capture import capture_environment

            service.set_profile_parameter(
                service.with_unconstrained_network(capture_environment()), spec.parameter, spec.low
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return spec


@router.post(
    "",
    response_model=ThresholdResult,
    summary="Locate the failure boundary of one parameter (blocking)",
    responses={
        400: {"description": "Unknown parameter or bad range"},
        422: {"description": "Invalid request or the command cannot launch (setup error)"},
    },
)
def find_threshold(req: ThresholdRequest) -> ThresholdResult:
    """Search ``[low, high]`` for the value at which failures begin.

    Returns the full :class:`ThresholdResult`: ``outcome`` says whether a
    boundary was found in range (``boundary_found``), or the whole range
    passed (``never_fails``) / failed (``always_fails``). In ``bayes`` mode
    ``credible_low`` / ``credible_high`` bracket the boundary with
    ``credible_mass`` probability and ``probability_boundary_in_range`` is
    reported honestly (a range with no boundary gives ``boundary_estimate: null``).
    """
    spec = _prepare(req)
    try:
        return service.run_threshold(spec)
    except service.setup_error_types() as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/stream",
    response_model=dict,
    summary="Start a threshold search and stream probes over WebSocket",
    responses={
        400: {"description": "Unknown parameter or bad range"},
        422: {"description": "Invalid request or the command cannot launch (setup error)"},
    },
)
async def find_threshold_stream(req: ThresholdRequest) -> dict:
    """Start the search in the background; subscribe to
    ``/ws/threshold/{threshold_id}`` for ``search_probe`` events, then
    ``{"type": "done", "result": ThresholdResult}`` or an ``error`` frame.
    The command is probed synchronously first, so a setup error is a **422**.
    """
    manager.bind_loop()
    spec = _prepare(req)
    try:
        service.probe_setup(spec.command, spec.timeout, spec.cwd)
    except service.setup_error_types() as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    spec.probe = False

    from morph.runtime.controller import RuntimeController

    thr_id = f"thr-{uuid.uuid4().hex[:8]}"
    manager.open_log(thr_id)
    job = jobs.create(thr_id, "threshold", controller=RuntimeController())

    def _emit(event: TrialEvent) -> None:
        manager.emit_threadsafe(thr_id, {"type": "event", **event.model_dump()})

    def _worker() -> None:
        try:
            result = service.run_threshold(
                spec, on_event=_emit, stop_event=job.stop_event, controller=job.controller
            )
            payload = {"type": "done", "result": result.model_dump(mode="json")}
        except service.Cancelled:
            payload = {"type": "error", "message": "cancelled", "cancelled": True}
        except service.setup_error_types() as exc:
            payload = {"type": "error", "message": str(exc), "setup_error": True}
        except Exception as exc:
            payload = {"type": "error", "message": f"{exc.__class__.__name__}: {exc}"}
        manager.emit_threadsafe(thr_id, payload)

    jobs.start(job, _worker)
    return {"threshold_id": thr_id, "status": "running", "method": spec.method}


@router.delete(
    "/{threshold_id}",
    summary="Cancel a running threshold search (or forget a finished one)",
    responses={404: {"description": "Unknown threshold id"}},
)
def delete_threshold(threshold_id: IdPath) -> dict:
    """Ask a running search to stop after its current probe, or drop a
    finished one so late subscribers no longer get its replay."""
    if not manager.known(threshold_id):
        raise HTTPException(status_code=404, detail=f"Threshold search '{threshold_id}' not found")
    cancelled = jobs.cancel(threshold_id)
    if not cancelled:
        manager.drop(threshold_id)
        jobs.forget(threshold_id)
    return {"threshold_id": threshold_id, "cancelled": cancelled, "deleted": not cancelled}
