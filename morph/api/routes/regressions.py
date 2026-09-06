"""FastAPI routes for Flight Recorder regression artifact management and replay."""

from __future__ import annotations

from typing import List
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
    trials: int = 1
    timeout: float = 30.0


@router.get("", response_model=List[RegressionArtifact])
def get_all_regressions() -> List[RegressionArtifact]:
    """List all saved regression artifacts."""
    return list_regressions()


@router.post("", response_model=dict)
def create_regression(artifact: RegressionArtifact) -> dict:
    """Save a new regression artifact."""
    try:
        path = save_regression(artifact)
        return {"status": "created", "regression_id": artifact.regression_id, "path": str(path)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save regression: {exc}")


@router.get("/{regression_id}", response_model=RegressionArtifact)
def get_regression_by_id(regression_id: str) -> RegressionArtifact:
    """Load a specific regression artifact."""
    try:
        return load_regression(regression_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/{regression_id}/replay", response_model=ReplayResult)
def replay_regression_by_id(regression_id: str, req: ReplayRequest = ReplayRequest()) -> ReplayResult:
    """Replay a saved regression artifact and verify against expected tolerances."""
    try:
        return replay_regression(regression_id, trials=req.trials, timeout=req.timeout)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Replay failed: {exc}")


@router.delete("/{regression_id}", response_model=dict)
def remove_regression_by_id(regression_id: str) -> dict:
    """Delete a regression artifact from disk."""
    success = delete_regression(regression_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Regression '{regression_id}' not found")
    return {"status": "deleted", "regression_id": regression_id}
