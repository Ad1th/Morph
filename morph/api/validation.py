"""Identifier validation shared by the API routes and the CLI.

Profile ids, regression ids, experiment ids and project ids all end up in a
filesystem path (``.morph/profiles/<id>.json``, ``.morph/regressions/<id>/``).
An unvalidated id such as ``../../tmp/evil`` or ``/tmp/evil`` therefore writes
wherever the caller likes. One pattern, applied everywhere an id enters.
"""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import HTTPException
from fastapi import Path as PathParam
from pydantic import AfterValidator, StringConstraints

ID_PATTERN = r"^[A-Za-z0-9._-]{1,64}$"
_ID_RE = re.compile(ID_PATTERN)



def _not_dots(value: str) -> str:
    if value in (".", ".."):
        raise ValueError("id must not be '.' or '..'")
    return value


#: Pydantic type for an id carried in a request body.
IdStr = Annotated[
    str, StringConstraints(pattern=ID_PATTERN, min_length=1, max_length=64), AfterValidator(_not_dots)
]

#: FastAPI type for an id carried in a URL path segment.
IdPath = Annotated[str, PathParam(pattern=ID_PATTERN, min_length=1, max_length=64)]


def is_valid_id(value: str) -> bool:
    """True when ``value`` is a safe identifier: 1-64 of ``[A-Za-z0-9._-]``, not ``.``/``..``."""
    return bool(value) and bool(_ID_RE.match(value)) and value not in (".", "..")


def validate_id(value: str, *, what: str = "id") -> str:
    """Return ``value`` or raise ``ValueError`` with a message safe to show a user."""
    if not is_valid_id(value):
        raise ValueError(
            f"Invalid {what} {value!r}: use 1-64 letters, digits, '.', '_' or '-' "
            "(no path separators)."
        )
    return value


def require_id(value: str, *, what: str = "id") -> str:
    """Route helper: ``validate_id`` mapped to a 422 response."""
    try:
        return validate_id(value, what=what)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
