"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_morph_home(tmp_path, monkeypatch):
    """Keep the project registry, cloned checkouts, and per-project venvs out of
    the developer's real ``~/.morph`` during tests."""
    import morph.api.routes.projects as api_projects
    import morph.project_setup as project_setup
    import morph.projects as projects

    home = tmp_path / "morph-home"
    monkeypatch.setattr(projects, "REGISTRY_DIR", home / "projects")
    monkeypatch.setattr(project_setup, "CHECKOUTS_DIR", home / "checkouts")
    monkeypatch.setattr(project_setup, "VENVS_DIR", home / "venvs")
    monkeypatch.setattr(api_projects, "VENVS_DIR", home / "venvs")
    yield
