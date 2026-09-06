"""FastAPI routes for Environment Profile capture, management, and reconciliation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.profiler.capture import capture_environment
from morph.runtime.controller import reconcile_profile_statuses
from morph.schema.profile import EnvironmentProfile

router = APIRouter()
PROFILES_DIR = Path(".morph/profiles")


class SaveProfileRequest(BaseModel):
    id: str
    profile: EnvironmentProfile
    description: str | None = None


@router.post("/capture", response_model=EnvironmentProfile)
def capture_current_profile() -> EnvironmentProfile:
    """Capture the physical environment of the current machine."""
    try:
        return capture_environment()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to capture environment: {exc}")


@router.post("", response_model=dict[str, str])
def save_profile(req: SaveProfileRequest) -> dict[str, str]:
    """Save an environment profile to disk."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target_file = PROFILES_DIR / f"{req.id}.json"
    target_file.write_text(req.profile.model_dump_json(indent=2), encoding="utf-8")
    return {"id": req.id, "status": "saved", "path": str(target_file)}


@router.get("", response_model=list[dict[str, str]])
def list_profiles() -> list[dict[str, str]]:
    """List all saved profiles in .morph/profiles."""
    if not PROFILES_DIR.exists():
        return []
    profiles = []
    for item in sorted(PROFILES_DIR.glob("*.json")):
        profiles.append({"id": item.stem, "filename": item.name, "path": str(item)})
    return profiles


@router.get("/{profile_id}", response_model=EnvironmentProfile)
def get_profile(profile_id: str) -> EnvironmentProfile:
    """Get a saved profile by ID."""
    target_file = PROFILES_DIR / f"{profile_id}.json"
    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    try:
        return EnvironmentProfile.model_validate_json(target_file.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to parse profile '{profile_id}': {exc}")


@router.post("/reconcile", response_model=EnvironmentProfile)
def reconcile_profile(profile: EnvironmentProfile) -> EnvironmentProfile:
    """Reconcile profile fields against host adapter capabilities.

    Sets field statuses to REPRODUCED, APPROXIMATED, or UNAVAILABLE.
    """

    try:
        return reconcile_profile_statuses(profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reconcile profile: {exc}")
