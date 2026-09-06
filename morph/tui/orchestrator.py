"""Engine <-> TUI bridge.

Thin wrappers that build ``RunResult``-returning trial runners from an
``EnvironmentProfile`` + command, then drive the engine with an ``on_event``
callback. The TUI runs these inside a Textual thread worker and marshals the
events onto the UI thread; nothing here imports Textual, so it is unit-testable
on its own.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from morph.engine.experiment import RunFn, run_experiment, run_trials
from morph.engine.progress import OnEvent
from morph.engine.threshold import search_threshold
from morph.regression import load_regression
from morph.regression.replay import ReplayResult
from morph.runtime.controller import RuntimeController
from morph.runtime.runner import execute_command
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult
from morph.schema.profile import EnvironmentProfile
from morph.schema.regression import RegressionArtifact
from morph.schema.telemetry import RunResult

# Parameters the threshold search knows how to vary on a profile.
THRESHOLD_PARAMETERS = ("network.latency_ms", "network.packet_loss_percent")


def _positive(field: object) -> bool:
    value = getattr(field, "value", None)
    try:
        return float(value or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def make_result_runner(
    command: str,
    profile: EnvironmentProfile | None,
    timeout: float,
    controller: RuntimeController | None = None,
) -> Callable[[], RunResult]:
    """A zero-arg callable returning the full ``RunResult`` of one run.

    ``profile=None`` runs unconstrained (the experiment baseline).
    """
    ctrl = controller or RuntimeController()

    def _run() -> RunResult:
        if profile is None:
            return execute_command(command, timeout=timeout)
        return ctrl.run(profile=profile, command=command, timeout=timeout)

    return _run


def build_isolation_runners(
    target: EnvironmentProfile,
    command: str,
    timeout: float,
    controller: RuntimeController | None = None,
) -> tuple[RunFn, dict[str, RunFn]]:
    """Baseline (unconstrained) + one runner per network variable the target
    actually requests, plus the full target profile."""
    ctrl = controller or RuntimeController()
    baseline = make_result_runner(command, None, timeout, ctrl)

    candidates: dict[str, RunFn] = {}
    net = target.network
    if net is not None and _positive(net.latency_ms):
        latency_only = target.model_copy(deep=True)
        latency_only.network.packet_loss_percent.value = 0.0
        candidates["latency_only"] = make_result_runner(command, latency_only, timeout, ctrl)
    if net is not None and _positive(net.packet_loss_percent):
        loss_only = target.model_copy(deep=True)
        loss_only.network.latency_ms.value = 0.0
        candidates["loss_only"] = make_result_runner(command, loss_only, timeout, ctrl)

    candidates["full_target"] = make_result_runner(command, target, timeout, ctrl)
    return baseline, candidates


def run_experiment_live(
    target: EnvironmentProfile,
    command: str,
    trials: int,
    timeout: float,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
) -> ExperimentResult:
    baseline, candidates = build_isolation_runners(target, command, timeout, controller)
    if not candidates:
        candidates = {"treatment": make_result_runner(command, target, timeout, controller)}
    return run_experiment(baseline, candidates, n=trials, on_event=on_event)


def set_profile_parameter(
    profile: EnvironmentProfile, dotted_path: str, value: float
) -> EnvironmentProfile:
    """Deep-copy ``profile`` with one dotted field's value replaced."""
    updated = profile.model_copy(deep=True)
    section: object = updated
    parts = dotted_path.split(".")
    for part in parts[:-1]:
        section = getattr(section, part, None)
        if section is None:
            raise ValueError(f"Profile has no '{part}' section for parameter '{dotted_path}'")
    leaf = getattr(section, parts[-1], None)
    if leaf is None or not hasattr(leaf, "value"):
        raise ValueError(f"'{dotted_path}' is not a settable profile field")
    leaf.value = value
    return updated


def run_threshold_live(
    base: EnvironmentProfile,
    command: str,
    parameter: str,
    low: float,
    high: float,
    trials: int,
    timeout: float,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
) -> ThresholdResult:
    ctrl = controller or RuntimeController()

    def run_at(value: float) -> RunResult:
        candidate = set_profile_parameter(base, parameter, value)
        return ctrl.run(profile=candidate, command=command, timeout=timeout)

    return search_threshold(
        parameter=parameter, run_at=run_at, low=low, high=high, trials=trials, on_event=on_event
    )


def run_replay_live(
    regression: RegressionArtifact | Path | str,
    trials: int,
    timeout: float,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
) -> ReplayResult:
    """Re-run a saved regression bundle under its own environment, emitting a
    trial event per run, then check the failure rate against its tolerance."""
    artifact = (
        regression
        if isinstance(regression, RegressionArtifact)
        else load_regression(regression)
    )
    ctrl = controller or RuntimeController()
    runner = make_result_runner(artifact.command, artifact.environment, timeout, ctrl)
    batch = run_trials(runner, trials, f"replay:{artifact.regression_id}", on_event=on_event)

    matches = batch.failure_rate <= artifact.expected_max_failure_rate
    summary = (
        f"{batch.failures}/{trials} failed ({batch.failure_rate:.0%}); "
        f"tolerance ≤ {artifact.expected_max_failure_rate:.0%}"
    )
    on_event(
        TrialEvent(
            kind="verdict",
            condition=artifact.regression_id,
            classification="compliant" if matches else "violation",
            extra={"summary": summary},
        )
    )
    return ReplayResult(
        regression_id=artifact.regression_id,
        passed=matches,
        matches_expected=matches,
        failure_rate=batch.failure_rate or 0.0,
        total_runs=trials,
        failures=batch.failures,
        runs=batch.run_results,
        regression=artifact,
        summary=summary,
    )
