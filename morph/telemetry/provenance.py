"""Run provenance: who produced a RunResult, on what, from which profile.

Everything here is cheap and deterministic so it can be stamped on every trial.
The comparison engine can refuse to compare results whose `host_fingerprint`
or `morph_version` differ, and a regression bundle can say which machine
produced its expected values.
"""

from __future__ import annotations

import functools
import hashlib
import os
import platform
import subprocess
from pathlib import Path

from morph.schema.profile import EnvironmentProfile


@functools.lru_cache(maxsize=1)
def morph_version() -> str:
    """`<package version>+<short git sha>` when run from a checkout, else the version."""
    try:
        from morph import __version__
    except Exception:  # pragma: no cover - defensive
        __version__ = "unknown"
    root = Path(__file__).resolve().parent.parent.parent
    if (root / ".git").exists():
        try:
            sha = subprocess.run(
                ["git", "-C", str(root), "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if sha:
                return f"{__version__}+{sha}"
        except (OSError, subprocess.SubprocessError):
            pass
    return __version__


@functools.lru_cache(maxsize=1)
def host_fingerprint() -> str:
    """Stable hash of (os, arch, logical cores, RAM MB) -- the things that make
    two results comparable. Deliberately excludes the hostname."""
    try:
        import psutil

        ram_mb = int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        ram_mb = 0
    raw = f"{platform.system().lower()}|{platform.machine().lower()}|{os.cpu_count() or 0}|{ram_mb}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def profile_hash(profile: EnvironmentProfile) -> str:
    """sha256 of the canonical (sorted-key) profile JSON, statuses included."""
    import json

    canonical = json.dumps(profile.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def seed_from_env() -> int | None:
    raw = os.environ.get("MORPH_SEED")
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        return None
