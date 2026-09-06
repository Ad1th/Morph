"""Flight Recorder artifact management for .morph/ regression bundles."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import List, Optional, Union

from morph.schema.profile import EnvironmentProfile
from morph.schema.regression import RegressionArtifact

DEFAULT_REGRESSIONS_DIR = Path(".morph/regressions")


def save_regression(
    artifact: RegressionArtifact,
    base_dir: Union[Path, str] = DEFAULT_REGRESSIONS_DIR,
) -> Path:
    """Save a RegressionArtifact as a structured directory bundle under base_dir/regression_id."""
    target_dir = Path(base_dir) / artifact.regression_id
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


def load_regression(
    path_or_id: Union[Path, str],
    base_dir: Union[Path, str] = DEFAULT_REGRESSIONS_DIR,
) -> RegressionArtifact:
    """Load and reconstruct a RegressionArtifact from a bundle directory or regression ID."""
    p = Path(path_or_id)
    if not p.is_dir():
        p = Path(base_dir) / path_or_id

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


def list_regressions(
    base_dir: Union[Path, str] = DEFAULT_REGRESSIONS_DIR,
) -> List[RegressionArtifact]:
    """Scan base_dir and return all valid RegressionArtifact bundles."""
    p = Path(base_dir)
    if not p.exists() or not p.is_dir():
        return []

    results: List[RegressionArtifact] = []
    for item in sorted(p.iterdir()):
        if item.is_dir() and (item / "environment.json").exists():
            try:
                results.append(load_regression(item))
            except Exception:
                continue
    return results


def delete_regression(
    path_or_id: Union[Path, str],
    base_dir: Union[Path, str] = DEFAULT_REGRESSIONS_DIR,
) -> bool:
    """Delete a regression bundle directory."""
    p = Path(path_or_id)
    if not p.is_dir():
        p = Path(base_dir) / path_or_id
    if p.is_dir():
        shutil.rmtree(p)
        return True
    return False
