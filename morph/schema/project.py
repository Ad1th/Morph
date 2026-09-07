"""Descriptor for a project the user pointed Morph at (uploaded, local, or GitHub).

The `/projects/*` routes return this; the frontend feeds `suggested_command`
and `suggested_cwd` straight into `/run`, so a user never has to type the
invocation for a project Morph can recognise. When nothing is recognised both
stay `None` rather than guessing a command that would not run; the UI then
asks the user and persists the answer with ``PUT /projects/{id}``.

This is the API view of :class:`morph.projects.Project` (the registry record
the CLI table shows); the provenance fields are carried through so the two
agree on what a project is.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProjectInfo(BaseModel):
    project_id: str
    name: str
    path: str
    file_count: int
    entrypoints: list[str] = Field(default_factory=list)
    suggested_command: str | None = None
    suggested_cwd: str | None = None
    # Install steps that failed (empty = clean, or nothing to install).
    deps_failed: list[str] = Field(default_factory=list)
    # Provenance, mirrored from the registry record.
    source: str = "local"  # "local" | "github" | "upload"
    repo: str | None = None  # "owner/repo" for github sources
    branch: str | None = None
    commit: str | None = None
    venv: str | None = None
    created_at: str | None = None
