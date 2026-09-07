"""FastAPI routes for Environment Profile capture, management, and reconciliation."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from morph.api.validation import IdPath, IdStr
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import FidelityEntry

router = APIRouter()
PROFILES_DIR = Path(".morph/profiles")


class SaveProfileRequest(BaseModel):
    id: IdStr
    profile: EnvironmentProfile
    description: str | None = None


def _profile_path(profile_id: str) -> Path:
    # `IdStr` / `IdPath` already reject separators and `..`; the resolve check
    # is belt and braces so a future loosening of the pattern cannot escape.
    path = (PROFILES_DIR / f"{profile_id}.json")
    root = PROFILES_DIR.resolve()
    if root not in path.resolve().parents:
        raise HTTPException(status_code=422, detail=f"Invalid profile id {profile_id!r}")
    return path


@router.post("/capture", response_model=EnvironmentProfile, summary="Capture this machine's profile")
def capture_current_profile() -> EnvironmentProfile:
    """Capture the physical environment of the current machine."""
    from morph.profiler.capture import capture_environment

    try:
        return capture_environment()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to capture environment: {exc}") from exc


@router.post(
    "",
    response_model=dict[str, str],
    summary="Save a profile",
    responses={422: {"description": "Invalid id (must match ^[A-Za-z0-9._-]{1,64}$)"}},
)
def save_profile(req: SaveProfileRequest) -> dict[str, str]:
    """Save an environment profile to disk under ``.morph/profiles/<id>.json``."""
    target_file = _profile_path(req.id)
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    target_file.write_text(req.profile.model_dump_json(indent=2), encoding="utf-8")
    return {"id": req.id, "status": "saved", "path": str(target_file)}


@router.get("", response_model=list[dict[str, str]], summary="List saved profiles")
def list_profiles() -> list[dict[str, str]]:
    """List all saved profiles in .morph/profiles."""
    if not PROFILES_DIR.exists():
        return []
    return [
        {"id": item.stem, "filename": item.name, "path": str(item)}
        for item in sorted(PROFILES_DIR.glob("*.json"))
    ]


@router.get(
    "/{profile_id}",
    response_model=EnvironmentProfile,
    summary="Load a saved profile",
    responses={404: {"description": "No such profile"}, 422: {"description": "Invalid id"}},
)
def get_profile(profile_id: IdPath) -> EnvironmentProfile:
    """Get a saved profile by ID."""
    target_file = _profile_path(profile_id)
    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    try:
        return EnvironmentProfile.model_validate_json(target_file.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=500, detail=f"Failed to parse profile '{profile_id}': {exc}"
        ) from exc


@router.delete(
    "/{profile_id}",
    summary="Delete a saved profile",
    responses={404: {"description": "No such profile"}, 422: {"description": "Invalid id"}},
)
def delete_profile(profile_id: IdPath) -> dict[str, str]:
    target_file = _profile_path(profile_id)
    if not target_file.exists():
        raise HTTPException(status_code=404, detail=f"Profile '{profile_id}' not found")
    target_file.unlink()
    return {"id": profile_id, "status": "deleted"}


@router.post(
    "/reconcile", response_model=EnvironmentProfile, summary="Reconcile a profile with this host"
)
def reconcile_profile(profile: EnvironmentProfile) -> EnvironmentProfile:
    """Reconcile profile fields against host adapter capabilities.

    Sets field statuses to REPRODUCED, APPROXIMATED, or UNAVAILABLE.
    """
    from morph.runtime.controller import reconcile_profile_statuses

    try:
        return reconcile_profile_statuses(profile)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to reconcile profile: {exc}") from exc


@router.post(
    "/fidelity",
    response_model=dict[str, FidelityEntry],
    summary="How faithfully this host would apply each field of a profile",
)
def profile_fidelity(profile: EnvironmentProfile) -> dict[str, FidelityEntry]:
    """Per-field plan from the active adapter: ``reproduced`` (a native
    mechanism enforces it), ``approximated`` (applied only partly, e.g. the
    user-space proxy), or ``unavailable`` (nothing on this host enforces it),
    each with the mechanism and a detail string. Runs nothing."""
    from morph.engine.runners import with_unconstrained_network
    from morph.runtime.controller import fidelity_report

    report = fidelity_report(with_unconstrained_network(profile))
    return {name: FidelityEntry(**f.as_dict()) for name, f in report.items()}
