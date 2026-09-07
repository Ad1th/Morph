"""Thin dispatch layer: merge env overrides onto os.environ, then run with telemetry."""

from __future__ import annotations

import os

from morph.schema.telemetry import RunResult
from morph.telemetry.collector import run_with_telemetry


def execute_command(
    command: str,
    env_overrides: dict | None = None,
    timeout: float = 30.0,
    cwd: str | None = None,
    max_processes: int | None = None,
    fd_limit: int | None = None,
    cgroup_path: str | None = None,
) -> RunResult:
    """Execute `command` under a copy of the current environment plus `env_overrides`.

    Override values are coerced to str (ints like ports work). A value of None
    removes that key from the child environment. Typical keys: LC_ALL, LANG, TZ,
    MORPH_PROXY_URL / MORPH_PROXY_* for the network-shaping proxy.

    `max_processes`/`fd_limit`/`cgroup_path` are POSIX-only process resource
    limits; see `morph.telemetry.collector.run_with_telemetry`.
    """
    merged = dict(os.environ)
    for key, value in (env_overrides or {}).items():
        key = str(key)
        if value is None:
            merged.pop(key, None)
        else:
            merged[key] = str(value)

    return run_with_telemetry(
        command, env=merged, timeout=timeout, cwd=cwd,
        max_processes=max_processes, fd_limit=fd_limit, cgroup_path=cgroup_path,
    )
