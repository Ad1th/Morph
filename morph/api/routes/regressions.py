"""FastAPI routes for Flight Recorder regression artifact management and replay."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from morph.api import defaults, service
from morph.api.validation import IdPath, require_id
from morph.regression import (
    delete_regression,
    list_regressions,
    load_regression,
    replay_regression,
    save_regression,
)
from morph.regression.replay import ReplayResult
from morph.schema.regression import RegressionArtifact

router = APIRouter()


class ReplayRequest(BaseModel):
    trials: int = Field(1, ge=1)
    timeout: float = Field(defaults.TIMEOUT_SEC, gt=0)


@router.get("", response_model=list[RegressionArtifact], summary="List saved regressions")
def get_all_regressions() -> list[RegressionArtifact]:
    """List all saved regression artifacts."""
    return list_regressions()


@router.post(
    "",
    response_model=dict,
    summary="Save a regression bundle",
    responses={422: {"description": "Invalid regression_id (must match ^[A-Za-z0-9._-]{1,64}$)"}},
)
def create_regression(artifact: RegressionArtifact) -> dict:
    """Save a new regression artifact under ``.morph/regressions/<regression_id>/``."""
    require_id(artifact.regression_id, what="regression_id")
    try:
        path = save_regression(artifact)
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save regression: {exc}") from exc
    return {"status": "created", "regression_id": artifact.regression_id, "path": str(path)}


@router.get(
    "/{regression_id}",
    response_model=RegressionArtifact,
    summary="Load a regression bundle",
    responses={404: {"description": "No such regression"}},
)
def get_regression_by_id(regression_id: IdPath) -> RegressionArtifact:
    """Load a specific regression artifact."""
    try:
        return load_regression(regression_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post(
    "/{regression_id}/replay",
    response_model=ReplayResult,
    summary="Replay a regression bundle",
    responses={
        404: {"description": "No such regression"},
        422: {"description": "The bundle's command cannot launch (setup error)"},
    },
)
def replay_regression_by_id(regression_id: IdPath, req: ReplayRequest | None = None) -> ReplayResult:
    """Replay a saved regression artifact and verify against expected tolerances."""
    req = req or ReplayRequest()
    try:
        result = replay_regression(regression_id, trials=req.trials, timeout=req.timeout)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found") from exc
    except service.setup_error_types() as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result.runs and all(service.is_setup_error(r) for r in result.runs):
        raise HTTPException(
            status_code=422,
            detail=service.setup_error_message(result.runs[0], result.regression.command),
        )
    return result


@router.delete(
    "/{regression_id}",
    response_model=dict,
    summary="Delete a regression bundle",
    responses={404: {"description": "No such regression"}},
)
def remove_regression_by_id(regression_id: IdPath) -> dict:
    """Delete a regression artifact from disk."""
    if not delete_regression(regression_id):
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found")
    return {"status": "deleted", "regression_id": regression_id}
