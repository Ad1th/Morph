"""FastAPI routes for running and querying causal experiments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from morph.engine.experiment import run_experiment
from morph.engine.runners import build_baseline_and_candidates, make_run_fn
from morph.runtime.controller import RuntimeController
from morph.schema.experiment import ExperimentConfig, ExperimentResult

router = APIRouter()
_EXPERIMENTS_CACHE: dict[str, ExperimentResult] = {}


@router.post("", response_model=ExperimentResult)
def create_experiment(config: ExperimentConfig) -> ExperimentResult:
    """Run an automated causal isolation experiment."""
    controller = RuntimeController()
    baseline_fn, candidates = build_baseline_and_candidates(
        config.target_profile, config.command, config.timeout_sec, controller
    )

    if not candidates:
        # Nothing to isolate: compare the command against itself so the engine
        # still reports a baseline classification.
        fallback_profile = config.target_profile
        candidates = {
            "treatment": make_run_fn(
                config.command, fallback_profile, config.timeout_sec, controller
            )
        }

    try:
        exp_result = run_experiment(
            baseline_run_fn=baseline_fn,
            candidates=candidates,
            n=config.trials,
        )
        exp_id = f"exp-{uuid.uuid4().hex[:8]}"
        exp_result.experiment_id = exp_id
        if config.target_profile:
            exp_result.target_profile = config.target_profile

        _EXPERIMENTS_CACHE[exp_id] = exp_result
        return exp_result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Experiment execution error: {exc}")


@router.get("/{experiment_id}", response_model=ExperimentResult)
def get_experiment(experiment_id: str) -> ExperimentResult:
    """Retrieve the results of a previously executed experiment."""
    if experiment_id not in _EXPERIMENTS_CACHE:
        raise HTTPException(status_code=404, detail=f"Experiment '{experiment_id}' not found")
    return _EXPERIMENTS_CACHE[experiment_id]
