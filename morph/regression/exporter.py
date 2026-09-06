"""CI Invariant Exporter: generate standalone pytest suites from regressions."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Union

from morph.regression.artifact import load_regression
from morph.schema.regression import RegressionArtifact


def _safe_identifier(name: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_]", "_", name).lower()


def export_ci_test(
    regression: Union[RegressionArtifact, Path, str],
    output_path: Union[Path, str] = "test_morph_invariant.py",
) -> Path:
    """Generate a standalone pytest file that verifies an environment regression invariant."""
    if isinstance(regression, (str, Path)):
        artifact = load_regression(regression)
    else:
        artifact = regression

    out = Path(output_path)
    safe_name = _safe_identifier(artifact.regression_id)

    code = f'''"""Standalone Morph Invariant CI Test.

Generated automatically by Morph Flight Recorder.
Verifies that the application survives environment constraints:
- Regression ID: {artifact.regression_id}
- Target Command: {artifact.command}
- Max Allowed Failure Rate: {artifact.expected_max_failure_rate:.1%}
- Created: {artifact.created_at}
"""

import pytest
from morph.regression.replay import replay_regression


def test_morph_{safe_name}_environment_invariant():
    """Verify application complies with the recorded regression threshold."""
    result = replay_regression(
        "{artifact.regression_id}",
        trials=1,
    )
    assert result.matches_expected, (
        f"Morph invariant violation on '{artifact.regression_id}': "
        f"failure rate {{result.failure_rate:.1%}} exceeds max allowed "
        f"{artifact.expected_max_failure_rate:.1%}. Summary: {{result.summary}}"
    )
'''
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(code, encoding="utf-8")
    return out
