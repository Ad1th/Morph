"""FastAPI route exposing the parameter metadata catalog.

The UI renders every parameter control from this metadata rather than
hardcoding widgets per field (docs/ui-spec.md section 6) -- so the frontend
fetches it from here instead of duplicating morph/schema/parameters.py.
"""

from __future__ import annotations

from fastapi import APIRouter

from morph.schema.parameters import PARAMETER_CATALOG, ParameterMetadata

router = APIRouter()


@router.get("", response_model=dict[str, ParameterMetadata])
def get_parameter_catalog() -> dict[str, ParameterMetadata]:
    """Return the full parameter metadata catalog (MVP + Phase 2)."""
    return PARAMETER_CATALOG
