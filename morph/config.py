"""Project configuration management for morph.yaml."""

from __future__ import annotations

import warnings
from pathlib import Path

import yaml

from morph.schema.config import MorphConfig

DEFAULT_CONFIG_FILENAMES = ["morph.yaml", "morph.yml"]


def find_config_path(start_dir: Path | str | None = None) -> Path | None:
    """Find morph.yaml in start_dir or parent directories.

    The walk stops at a git root or the home directory, so a stray
    ``~/morph.yaml`` cannot silently configure every project below it.
    """
    current = Path(start_dir or Path.cwd()).resolve()
    home = Path.home().resolve()
    while True:
        for name in DEFAULT_CONFIG_FILENAMES:
            candidate = current / name
            if candidate.is_file():
                return candidate
        if (current / ".git").exists() or current == home or current.parent == current:
            break
        current = current.parent
    return None


def load_config(path_or_dir: Path | str | None = None) -> MorphConfig:
    """Load MorphConfig from a file, directory, or search path.

    If no config file is found, returns default MorphConfig.
    """

    if path_or_dir is not None:
        p = Path(path_or_dir)
        if p.is_file():
            config_file = p
        elif p.is_dir():
            config_file = find_config_path(p)
        else:
            config_file = None
    else:
        config_file = find_config_path()

    if config_file and config_file.exists():
        try:
            content = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(content) or {}
            return MorphConfig.model_validate(data)
        except Exception as exc:
            # A typo in morph.yaml used to yield defaults in silence; the user
            # lost their worker without a word.
            warnings.warn(f"ignoring malformed {config_file}: {exc}", stacklevel=2)
            return MorphConfig()

    return MorphConfig()


def save_config(config: MorphConfig, path: Path | str = "morph.yaml") -> Path:
    """Save MorphConfig as YAML."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    yaml_str = yaml.dump(config.model_dump(), sort_keys=False)
    p.write_text(yaml_str, encoding="utf-8")
    return p
