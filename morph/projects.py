"""On-disk registry of projects Morph has been pointed at.

A *project* is a directory plus the command that runs it, remembered across
sessions under ``~/.morph/projects/``. ``morph connect`` writes one;
``morph run --project <id>``, the TUI, and the dashboard read it back.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field

REGISTRY_DIR = Path.home() / ".morph" / "projects"


class Project(BaseModel):
    id: str = Field(default_factory=lambda: f"proj-{uuid.uuid4().hex[:8]}")
    name: str
    source: str = "local"  # "local" | "github" | "upload"
    path: str  # working directory on disk
    command: str | None = None
    cwd: str | None = None
    repo: str | None = None  # "owner/repo" for github sources
    branch: str | None = None
    commit: str | None = None
    venv: str | None = None  # isolated env prepared for it, if any
    entrypoints: list[str] = Field(default_factory=list)
    file_count: int = 0
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


def _registry(base: Path | str | None = None) -> Path:
    directory = Path(base) if base is not None else REGISTRY_DIR
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save(project: Project, *, base: Path | str | None = None) -> Path:
    path = _registry(base) / f"{project.id}.json"
    path.write_text(project.model_dump_json(indent=2), encoding="utf-8")
    return path


def list_projects(*, base: Path | str | None = None) -> list[Project]:
    out: list[Project] = []
    for file in _registry(base).glob("*.json"):
        try:
            out.append(Project.model_validate_json(file.read_text(encoding="utf-8")))
        except Exception:
            continue
    return sorted(out, key=lambda p: p.created_at, reverse=True)


def load(id_or_name: str, *, base: Path | str | None = None) -> Project:
    directory = _registry(base)
    direct = directory / f"{id_or_name}.json"
    if direct.is_file():
        return Project.model_validate_json(direct.read_text(encoding="utf-8"))
    for project in list_projects(base=base):
        if project.name == id_or_name:
            return project
    raise KeyError(f"No project {id_or_name!r} in {directory}")


def delete(id_or_name: str, *, base: Path | str | None = None) -> bool:
    try:
        project = load(id_or_name, base=base)
    except KeyError:
        return False
    file = _registry(base) / f"{project.id}.json"
    if file.is_file():
        file.unlink()
        return True
    return False
