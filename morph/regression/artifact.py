"""Flight Recorder artifact management for .morph/ regression bundles.

Identifiers vs paths. A *regression id* is a bare name (``checkout-001``) that
is resolved INSIDE the regressions directory; it is what the HTTP API and the
TUI pass around, so it is validated strictly (`ID_RE`, never ``.``/``..``) and
the resolved directory is checked to still lie under the store. A *bundle
path* is an existing directory the user pointed the CLI at (``morph replay
./.morph/regressions/x``); it is accepted as a `Path`, or as a string that is
not a valid id and names an existing bundle. Deleting only ever works by id.
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from morph.schema.profile import EnvironmentProfile
from morph.schema.regression import RegressionArtifact

DEFAULT_REGRESSIONS_DIR = Path(".morph/regressions")

ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")


class InvalidRegressionId(ValueError):
    """The id is not a bare bundle name (contains a separator, is `.`/`..`, ...)."""


def is_valid_id(value: str) -> bool:
    return bool(ID_RE.fullmatch(value or "")) and value not in (".", "..")


def _base(base_dir: Path | str | None) -> Path:
    return Path(base_dir) if base_dir is not None else DEFAULT_REGRESSIONS_DIR


def resolve_id(regression_id: str, base_dir: Path | str | None = None) -> Path:
    """`base_dir / regression_id`, guaranteed to lie inside `base_dir`."""
    if not is_valid_id(regression_id):
        raise InvalidRegressionId(f"invalid regression id: {regression_id!r}")
    base = _base(base_dir).resolve()
    target = (base / regression_id).resolve()
    if target.parent != base and not target.is_relative_to(base):
        raise InvalidRegressionId(f"regression id escapes the store: {regression_id!r}")
    return target


def _is_bundle(path: Path) -> bool:
    return path.is_dir() and (path / "environment.json").is_file()


def _locate(path_or_id: Path | str, base_dir: Path | str | None) -> Path:
    """Bundle directory for an id (validated, inside the store) or an explicit path."""
    if isinstance(path_or_id, Path):
        return path_or_id
    text = str(path_or_id)
    if is_valid_id(text):
        by_id = resolve_id(text, base_dir)
        if by_id.is_dir():
            return by_id
        # A bare name may also be a relative directory the CLI was pointed at.
        as_path = Path(text)
        if _is_bundle(as_path):
            return as_path
        return by_id
    # Not an id: only an existing bundle directory is accepted, never fabricated.
    as_path = Path(text).expanduser()
    if _is_bundle(as_path):
        return as_path
    raise FileNotFoundError(f"Regression bundle not found at: {text}")


def save_regression(
    artifact: RegressionArtifact,
    base_dir: Path | str | None = None,
) -> Path:
    """Save a RegressionArtifact as a structured directory bundle under base_dir/regression_id."""
    target_dir = resolve_id(artifact.regression_id, base_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. environment.json
    env_json = artifact.environment.model_dump_json(indent=2)
    (target_dir / "environment.json").write_text(env_json, encoding="utf-8")

    # 2. command.json
    cmd_data = {"command": artifact.command}
    (target_dir / "command.json").write_text(json.dumps(cmd_data, indent=2), encoding="utf-8")

    # 3. expected.json
    expected_data = {
        "expected_exit_code": artifact.expected_exit_code,
        "expected_max_failure_rate": artifact.expected_max_failure_rate,
    }
    (target_dir / "expected.json").write_text(json.dumps(expected_data, indent=2), encoding="utf-8")

    # 4. metadata.json
    meta_data = {
        "regression_id": artifact.regression_id,
        "failure_signature": artifact.failure_signature,
        "created_at": artifact.created_at,
        "metadata": artifact.metadata,
    }
    (target_dir / "metadata.json").write_text(json.dumps(meta_data, indent=2), encoding="utf-8")

    return target_dir


def load_regression_path(path: Path | str) -> RegressionArtifact:
    """Load a bundle from an explicit directory (CLI convenience; no store restriction)."""
    p = Path(path)
    if not p.is_dir():
        raise FileNotFoundError(f"Regression bundle not found at: {p}")

    env_path = p / "environment.json"
    cmd_path = p / "command.json"
    exp_path = p / "expected.json"
    meta_path = p / "metadata.json"

    if not env_path.exists() or not cmd_path.exists():
        raise ValueError(f"Incomplete regression bundle at {p}: missing environment.json or command.json")

    environment = EnvironmentProfile.model_validate_json(env_path.read_text(encoding="utf-8"))
    cmd_data = json.loads(cmd_path.read_text(encoding="utf-8"))
    exp_data = json.loads(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else {}
    meta_data = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}

    return RegressionArtifact(
        regression_id=meta_data.get("regression_id", p.name),
        environment=environment,
        command=cmd_data.get("command", ""),
        expected_exit_code=exp_data.get("expected_exit_code", 0),
        expected_max_failure_rate=exp_data.get("expected_max_failure_rate", 0.0),
        failure_signature=meta_data.get("failure_signature"),
        created_at=meta_data.get("created_at", ""),
        metadata=meta_data.get("metadata", {}),
    )


def load_regression(
    path_or_id: Path | str,
    base_dir: Path | str | None = None,
) -> RegressionArtifact:
    """Load a RegressionArtifact by id (inside the store) or from a bundle directory.

    Raises FileNotFoundError for an unknown id, a malformed id (`..`, `a/b`),
    or a path that is not a bundle -- so an HTTP caller sees 404, never a read
    outside the store.
    """
    try:
        p = _locate(path_or_id, base_dir)
    except InvalidRegressionId as exc:
        raise FileNotFoundError(str(exc)) from exc
    return load_regression_path(p)


def list_regressions(
    base_dir: Path | str | None = None,
) -> list[RegressionArtifact]:
    """Scan base_dir and return all valid RegressionArtifact bundles."""
    p = _base(base_dir)
    if not p.exists() or not p.is_dir():
        return []

    results: list[RegressionArtifact] = []
    for item in sorted(p.iterdir()):
        if _is_bundle(item):
            try:
                results.append(load_regression_path(item))
            except Exception:
                continue
    return results


def delete_regression(
    regression_id: Path | str,
    base_dir: Path | str | None = None,
) -> bool:
    """Delete a regression bundle BY ID. Anything that is not a bare id inside
    the store (`..`, an absolute path, `a/b`) is refused and returns False."""
    base = _base(base_dir).resolve()
    if isinstance(regression_id, Path):
        target = regression_id.resolve()
        if target == base or not target.is_relative_to(base) or target.parent != base:
            return False
    else:
        try:
            target = resolve_id(str(regression_id), base_dir)
        except InvalidRegressionId:
            return False
    if _is_bundle(target):
        shutil.rmtree(target)
        return True
    return False
