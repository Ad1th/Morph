"""Shared test fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_morph_home(tmp_path, monkeypatch):
    """Keep the project registry, cloned checkouts, per-project venvs and the
    shaping state file out of the developer's real ``~/.morph`` during tests."""
    import morph.project_setup as project_setup
    import morph.projects as projects
    import morph.runtime.state as state

    home = tmp_path / "morph-home"
    monkeypatch.setattr(projects, "REGISTRY_DIR", home / "projects")
    monkeypatch.setattr(project_setup, "CHECKOUTS_DIR", home / "checkouts")
    monkeypatch.setattr(project_setup, "VENVS_DIR", home / "venvs")
    monkeypatch.setattr(state, "STATE_DIR", home / "state")
    try:
        import morph.api.routes.projects as api_projects
    except Exception:  # the API package is optional for non-API tests
        api_projects = None
    if api_projects is not None:
        monkeypatch.setattr(api_projects, "VENVS_DIR", home / "venvs")
    yield


@pytest.fixture(autouse=True)
def _never_touch_the_network_or_the_host(monkeypatch):
    """No unit test may SSH to a worker or run tc/dnctl/sudo/cgroup writes.

    `MORPH_NO_NETWORK` is honoured by RemoteWorker (every SSH attempt raises
    WorkerUnavailable before a socket opens) and `MORPH_NO_NATIVE` by the OS
    adapters (they take the proxy/env-hint path). Any worker config a
    developer has in their shell is dropped too.
    """
    monkeypatch.setenv("MORPH_NO_NETWORK", "1")
    monkeypatch.setenv("MORPH_NO_NATIVE", "1")
    for var in ("MORPH_CLOUD_HOST", "MORPH_CLOUD_USER", "MORPH_CLOUD_SSH_KEY",
                "MORPH_WORKER_HOST", "MORPH_WORKER_USER", "MORPH_WORKER_SSH_KEY",
                "MORPH_CGROUP_PATH", "MORPH_SEED"):
        monkeypatch.delenv(var, raising=False)
    yield
