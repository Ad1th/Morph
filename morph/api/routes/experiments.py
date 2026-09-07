"""FastAPI routes for running, streaming, listing and cancelling causal experiments.

All orchestration is in :mod:`morph.api.service`; this module is HTTP glue.
Results are kept in a bounded LRU (``MAX_CACHED_EXPERIMENTS``) shared with the
WebSocket replay log, so a dashboard that runs experiments all day does not
grow the process without bound.
"""

from __future__ import annotations

import uuid
from collections import OrderedDict
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import Field, field_validator, model_validator

from morph.api import defaults, service
from morph.api.routes.ws import manager
from morph.api.validation import IdPath
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentConfig, ExperimentResult

router = APIRouter()
jobs = service.JobRegistry()

_CACHE: OrderedDict[str, ExperimentResult] = OrderedDict()


def _cache_put(exp_id: str, result: ExperimentResult) -> None:
    _CACHE[exp_id] = result
    _CACHE.move_to_end(exp_id)
    while len(_CACHE) > defaults.MAX_CACHED_EXPERIMENTS:
        old, _ = _CACHE.popitem(last=False)
        manager.drop(old)
        jobs.forget(old)


def _on_evicted(exp_id: str) -> None:
    _CACHE.pop(exp_id, None)
    jobs.forget(exp_id)


manager.on_evict(_on_evicted)


class ExperimentRequest(ExperimentConfig):
    """`ExperimentConfig` plus the sequential-mode knobs, with validation.

    ``mode="sequential"`` (default) runs paired round-robin trials with an
    anytime-valid e-value and stops each condition early once the evidence is
    decisive; ``max_rounds`` bounds the trials per condition. ``mode="batch"``
    runs ``trials`` per condition and one Fisher test at the end.
    """

    trials: int = Field(defaults.TRIALS, ge=1, description="Trials per condition (batch mode)")
    timeout_sec: float = Field(defaults.TIMEOUT_SEC, gt=0, description="Per-trial timeout, seconds")
    mode: Literal["sequential", "batch"] = defaults.DEFAULT_EXPERIMENT_MODE
    max_rounds: int = Field(
        defaults.SEQUENTIAL_MAX_ROUNDS, ge=1, description="Round budget (sequential mode)"
    )
    alpha: float = Field(defaults.ALPHA, gt=0, lt=1, description="Family-wise error rate")
    cwd: str | None = Field(None, description="Working directory for every trial")

    @field_validator("command")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("command must not be empty")
        return value

    @model_validator(mode="after")
    def _needs_target(self) -> ExperimentRequest:
        if self.target_profile is None:
            raise ValueError(
                "target_profile is required: without a target there is no condition to isolate"
            )
        return self

    def to_spec(self) -> service.IsolationSpec:
        return service.IsolationSpec(
            command=self.command,
            target_profile=self.target_profile,
            cwd=self.cwd,
            timeout=self.timeout_sec,
            mode=self.mode,
            trials=self.trials,
            max_rounds=self.max_rounds,
            alpha=self.alpha,
        )


class ExperimentSummary(ExperimentResult):
    """Listing shape: the result without its per-trial run output."""


def _new_experiment_id() -> str:
    return f"exp-{uuid.uuid4().hex[:8]}"


def _setup_error(exc: BaseException) -> HTTPException:
    return HTTPException(status_code=422, detail=str(exc))


@router.post(
    "",
    response_model=ExperimentResult,
    summary="Run an isolation experiment (blocking)",
    responses={422: {"description": "Invalid request or the command cannot launch (setup error)"}},
)
def create_experiment(config: ExperimentRequest) -> ExperimentResult:
    """Run the full isolation experiment and return the verdict.

    Blocks for the whole run; prefer ``POST /experiments/stream`` from a UI.
    A command that cannot launch (missing binary, bad ``cwd``) is a **422**,
    never a verdict.
    """
    spec = config.to_spec()
    try:
        result = service.run_isolation(spec)
    except service.setup_error_types() as exc:
        raise _setup_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    exp_id = _new_experiment_id()
    result.experiment_id = exp_id
    _cache_put(exp_id, result)
    return result


@router.post(
    "/stream",
    response_model=dict,
    summary="Start an experiment and stream progress over WebSocket",
    responses={422: {"description": "Invalid request or the command cannot launch (setup error)"}},
)
async def create_experiment_stream(config: ExperimentRequest) -> dict:
    """Start the experiment in the background; subscribe to
    ``/ws/experiment/{experiment_id}`` for progress.

    Every engine :class:`TrialEvent` is forwarded as ``{"type": "event", ...}``
    (including ``kind="evidence"`` frames in sequential mode, carrying
    ``e_value``, ``evidence_threshold``, ``pairs`` and ``decisive``). The run
    ends with ``{"type": "done", "result": ExperimentResult}`` or
    ``{"type": "error", "message": ..., "setup_error": bool, "cancelled": bool}``.
    The result is also available from ``GET /experiments/{experiment_id}``.

    The command is probed once *before* this returns, so a setup error is a
    synchronous **422** instead of an error frame.
    """
    manager.bind_loop()
    spec = config.to_spec()
    try:
        spec.validate()
        service.probe_setup(spec.command, spec.timeout, spec.cwd)
    except service.setup_error_types() as exc:
        raise _setup_error(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    spec.probe = False

    from morph.runtime.controller import RuntimeController

    exp_id = _new_experiment_id()
    manager.open_log(exp_id)
    job = jobs.create(exp_id, "experiment", controller=RuntimeController())

    def _emit(event: TrialEvent) -> None:
        manager.emit_threadsafe(exp_id, {"type": "event", **event.model_dump()})

    def _worker() -> None:
        try:
            result = service.run_isolation(
                spec, on_event=_emit, stop_event=job.stop_event, controller=job.controller
            )
            result.experiment_id = exp_id
            _cache_put(exp_id, result)
            payload = {"type": "done", "result": result.model_dump(mode="json")}
        except service.Cancelled:
            payload = {"type": "error", "message": "cancelled", "cancelled": True}
        except service.setup_error_types() as exc:
            payload = {"type": "error", "message": str(exc), "setup_error": True}
        except Exception as exc:
            payload = {"type": "error", "message": f"{exc.__class__.__name__}: {exc}"}
        manager.emit_threadsafe(exp_id, payload)

    jobs.start(job, _worker)
    return {"experiment_id": exp_id, "status": "running", "mode": spec.mode}


@router.get("", response_model=list[dict], summary="List cached experiments")
def list_experiments() -> list[dict]:
    """Ids, classification and status of every experiment still in memory (newest last)."""
    out = []
    for exp_id in manager.event_log:
        result = _CACHE.get(exp_id)
        job = jobs.get(exp_id)
        out.append({
            "experiment_id": exp_id,
            "status": "running" if job is not None and job.running else (
                "done" if result is not None else "error"
            ),
            "classification": result.classification if result else None,
            "strongest_condition": result.strongest_condition if result else None,
        })
    for exp_id, result in _CACHE.items():
        if exp_id not in manager.event_log:
            out.append({
                "experiment_id": exp_id,
                "status": "done",
                "classification": result.classification,
                "strongest_condition": result.strongest_condition,
            })
    return out


@router.get(
    "/{experiment_id}",
    response_model=ExperimentResult,
    summary="Fetch a completed experiment",
    responses={404: {"description": "Unknown or evicted experiment id"}},
)
def get_experiment(experiment_id: IdPath) -> ExperimentResult:
    """Retrieve the result of a previously executed experiment."""
    if experiment_id not in _CACHE:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return _CACHE[experiment_id]


@router.delete(
    "/{experiment_id}",
    summary="Cancel a running experiment (or forget a finished one)",
    responses={404: {"description": "Unknown experiment id"}},
)
def delete_experiment(experiment_id: IdPath) -> dict:
    """Ask a running experiment to stop after its current trial, or drop a
    finished one from the cache. Cleanup of any applied shaping happens in the
    worker's own ``finally``."""
    if experiment_id not in _CACHE and not manager.known(experiment_id):
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    cancelled = jobs.cancel(experiment_id)
    if not cancelled:
        _CACHE.pop(experiment_id, None)
        manager.drop(experiment_id)
        jobs.forget(experiment_id)
    return {"experiment_id": experiment_id, "cancelled": cancelled, "deleted": not cancelled}
