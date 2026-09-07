"""Load the nearest ``.env`` file once, before anything reads ``os.environ``.

Morph keeps two kinds of configuration apart:

* ``morph.yaml`` is committed: trial counts, adapters, the worker's provider,
  the public GitHub client id. Nothing secret.
* ``.env`` is gitignored: tokens, SSH hosts and keys, deployment origins. See
  ``.env.example`` for every variable Morph reads.

The search starts in the current directory and walks up, stopping at a git
root or the home directory, so running ``morph`` from a subdirectory of a
project still finds the project's ``.env``. Values already present in the
environment always win, which is what a container or CI runner expects.
"""

from __future__ import annotations

import os
from pathlib import Path

_LOADED: set[Path] = set()


def find_env_file(start: Path | str | None = None) -> Path | None:
    """The nearest ``.env`` at or above ``start`` (default: the working directory)."""
    explicit = os.environ.get("MORPH_ENV_FILE")
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.is_file() else None
    here = Path(start or os.getcwd()).resolve()
    home = Path.home().resolve()
    for directory in (here, *here.parents):
        candidate = directory / ".env"
        if candidate.is_file():
            return candidate
        if (directory / ".git").exists() or directory == home:
            break
    return None


def load_env_file(start: Path | str | None = None, *, override: bool = False) -> Path | None:
    """Load the nearest ``.env`` into ``os.environ``; returns its path, or ``None``.

    Idempotent per file. Silently does nothing when ``python-dotenv`` is not
    installed, so a minimal install still works with plain environment variables.
    """
    path = find_env_file(start)
    if path is None or (path in _LOADED and not override):
        return path
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional at runtime
        return None
    load_dotenv(path, override=override)
    _LOADED.add(path)
    return path
