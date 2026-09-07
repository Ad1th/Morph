"""FastAPI routes for running and querying causal experiments."""

from __future__ import annotations

import threading
import uuid

from fastapi import APIRouter, HTTPException

from morph.api.routes.ws import manager
from morph.engine.experiment import run_experiment
from morph.engine.runners import build_baseline_and_candidates, make_run_fn
from morph.runtime.controller import RuntimeController
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentConfig, ExperimentResult

router = APIRouter()
_EXPERIMENTS_CACHE: dict[str, ExperimentResult] = {}


def _new_experiment_id() -> str:
    return f"exp-{uuid.uuid4().hex[:8]}"


def _run_experiment_for(config: ExperimentConfig, on_event=None) -> ExperimentResult:
    """Build the isolation runners for `config` and run the engine once."""
    controller = RuntimeController()
    baseline_fn, candidates = build_baseline_and_candidates(
        config.target_profile, config.command, config.timeout_sec, controller
    )
    if not candidates:
        # Nothing to isolate: compare the command against itself so the engine
        # still reports a baseline classification.
        candidates = {
            "treatment": make_run_fn(
                config.command, config.target_profile, config.timeout_sec, controller
            )
        }
    return run_experiment(
        baseline_run_fn=baseline_fn,
        candidates=candidates,
        n=config.trials,
        on_event=on_event,
    )


@router.post("", response_model=ExperimentResult)
def create_experiment(config: ExperimentConfig) -> ExperimentResult:
    """Run an automated causal isolation experiment (blocking)."""
    try:
        exp_result = _run_experiment_for(config)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Experiment execution error: {exc}")

    exp_id = _new_experiment_id()
    exp_result.experiment_id = exp_id
    if config.target_profile:
        exp_result.target_profile = config.target_profile
    _EXPERIMENTS_CACHE[exp_id] = exp_result
    return exp_result


@router.post("/stream", response_model=dict)
async def create_experiment_stream(config: ExperimentConfig) -> dict:
    """Start an experiment in the background and stream progress over
    ``/ws/experiment/{experiment_id}``.

    Returns immediately with the id to subscribe to. Every engine
    :class:`TrialEvent` is forwarded to the WebSocket as ``{"type": "event",
    ...}``; a final ``{"type": "done", "result": ...}`` or ``{"type": "error",
    ...}`` closes the run. The completed result is also retrievable from
    ``GET /experiments/{experiment_id}``.
    """
    # This handler runs on the server event loop; record it so the worker
    # thread can post progress events back (idempotent, self-healing across
    # test clients that each stand up a fresh loop).
    manager.bind_loop()

    exp_id = _new_experiment_id()
    manager.open_log(exp_id)

    def _emit(event: TrialEvent) -> None:
        manager.emit_threadsafe(exp_id, {"type": "event", **event.model_dump()})

    def _worker() -> None:
        try:
            result = _run_experiment_for(config, on_event=_emit)
            result.experiment_id = exp_id
            if config.target_profile:
                result.target_profile = config.target_profile
            _EXPERIMENTS_CACHE[exp_id] = result
            payload = {"type": "done", "result": result.model_dump(mode="json")}
        except Exception as exc:
            # Any failure in the worker is surfaced to the client as an error event.
            payload = {"type": "error", "message": str(exc)}
        manager.emit_threadsafe(exp_id, payload)

    threading.Thread(target=_worker, name=f"experiment-{exp_id}", daemon=True).start()
    return {"experiment_id": exp_id, "status": "running"}


@router.get("/{experiment_id}", response_model=ExperimentResult)
def get_experiment(experiment_id: str) -> ExperimentResult:
    """Retrieve the results of a previously executed experiment."""
    if experiment_id not in _EXPERIMENTS_CACHE:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return _EXPERIMENTS_CACHE[experiment_id]
