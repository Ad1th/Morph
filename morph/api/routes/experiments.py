"""FastAPI routes for running and querying causal experiments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from morph.engine.experiment import run_experiment
from morph.runtime.controller import RuntimeController
from morph.schema.experiment import ExperimentConfig, ExperimentResult

router = APIRouter()
_EXPERIMENTS_CACHE: dict[str, ExperimentResult] = {}


@router.post("", response_model=ExperimentResult)
def create_experiment(config: ExperimentConfig) -> ExperimentResult:
    """Run an automated causal isolation experiment."""
    controller = RuntimeController()

    # Function to execute command under a given profile or condition
    def _make_runner(profile=None):
        def _runner() -> bool:
            if profile is not None:
                res = controller.run(profile=profile, command=config.command, timeout=config.timeout_sec)
            else:
                from morph.runtime.runner import execute_command
                res = execute_command(command=config.command, timeout=config.timeout_sec)
            return res.passed
        return _runner

    # Baseline runner
    baseline_fn = _make_runner(config.target_profile)

    # Candidate treatments
    candidates = {}
    if config.target_profile is not None:
        target = config.target_profile
        # Test latency only
        if target.network and float(target.network.latency_ms.value or 0.0) > 0:
            lat_profile = target.model_copy(deep=True)
            lat_profile.network.packet_loss_percent.value = 0.0
            candidates["latency_only"] = _make_runner(lat_profile)

        # Test packet loss only
        if target.network and float(target.network.packet_loss_percent.value or 0.0) > 0:
            loss_profile = target.model_copy(deep=True)
            loss_profile.network.latency_ms.value = 0.0
            candidates["loss_only"] = _make_runner(loss_profile)

        # Full target profile
        candidates["full_treatment"] = _make_runner(target)

    if not candidates:
        candidates["treatment"] = baseline_fn

    try:
        exp_result = run_experiment(
            baseline_run_fn=_make_runner(None),
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
