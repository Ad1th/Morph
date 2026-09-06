"""Replay engine: execute and verify saved regression bundles."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Union
from pydantic import BaseModel, Field

from morph.regression.artifact import load_regression
from morph.runtime.controller import RuntimeController
from morph.schema.regression import RegressionArtifact
from morph.schema.telemetry import RunResult


class ReplayResult(BaseModel):
    """Result of replaying a regression artifact under simulated conditions."""
    regression_id: str
    passed: bool
    matches_expected: bool
    failure_rate: float
    total_runs: int
    failures: int
    runs: List[RunResult] = Field(default_factory=list)
    regression: RegressionArtifact
    summary: str = ""


def replay_regression(
    regression: Union[RegressionArtifact, Path, str],
    controller: Optional[RuntimeController] = None,
    trials: int = 1,
    timeout: float = 30.0,
    cwd: Optional[str] = None,
) -> ReplayResult:
    """Load and execute a regression artifact, evaluating against its expected tolerances."""
    if isinstance(regression, (str, Path)):
        artifact = load_regression(regression)
    else:
        artifact = regression

    ctrl = controller or RuntimeController()
    runs: List[RunResult] = []
    failures = 0

    for _ in range(trials):
        res = ctrl.run(
            profile=artifact.environment,
            command=artifact.command,
            timeout=timeout,
            cwd=cwd,
        )
        runs.append(res)
        if res.exit_code != artifact.expected_exit_code or not res.passed:
            failures += 1

    failure_rate = failures / trials if trials > 0 else 0.0
    matches_expected = failure_rate <= artifact.expected_max_failure_rate
    passed = matches_expected

    summary = (
        f"Regression '{artifact.regression_id}' replayed across {trials} trial(s): "
        f"{failures} failure(s) ({failure_rate:.1%}). "
        f"Expected max failure rate: {artifact.expected_max_failure_rate:.1%}. "
        f"Result: {'PASS' if passed else 'FAIL'}."
    )

    return ReplayResult(
        regression_id=artifact.regression_id,
        passed=passed,
        matches_expected=matches_expected,
        failure_rate=failure_rate,
        total_runs=trials,
        failures=failures,
        runs=runs,
        regression=artifact,
        summary=summary,
    )
