"""Descriptor for a project the user pointed Morph at (uploaded or local).

The `/projects/*` routes return this; the frontend feeds `suggested_command`
and `suggested_cwd` straight into `/run`, so a user never has to type the
invocation for a project Morph can recognise. When nothing is recognised both
stay `None` rather than guessing a command that would not run.
"""

from __future__ import annotations

from pydantic import BaseModel


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    path: str
    file_count: int
    entrypoints: list[str] = []
    suggested_command: str | None = None
    suggested_cwd: str | None = None
