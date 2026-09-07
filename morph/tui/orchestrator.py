"""Engine <-> TUI bridge.

Thin wrappers that build ``RunResult``-returning trial runners from an
``EnvironmentProfile`` + command, then drive the engine with an ``on_event``
callback. The TUI runs these inside a Textual thread worker and marshals the
events onto the UI thread; nothing here imports Textual, so it is unit-testable
on its own.

Cancellation is cooperative: the screen's ``on_event`` raises
:class:`RunCancelled` once the user has pressed Stop. The engine calls
``on_event`` *between* trials, after ``RuntimeController.run`` has already
restored the host in its ``finally``, so shaping never outlives a cancelled run.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from morph.engine.boundary import locate_boundary
from morph.engine.experiment import RunFn, run_experiment, run_trials
from morph.engine.progress import OnEvent
from morph.engine.sequential import run_sequential_experiment
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

EXPERIMENT_MODES = ("sequential", "batch")
THRESHOLD_METHODS = ("bayesian", "bisection")


class RunCancelled(Exception):
    """Raised from an ``on_event`` callback to stop the engine between trials."""


def cancellable(on_event: OnEvent, is_cancelled: Callable[[], bool]) -> OnEvent:
    """Wrap ``on_event`` so it raises :class:`RunCancelled` once ``is_cancelled()``."""

    def _emit(event: TrialEvent) -> None:
        if is_cancelled():
            raise RunCancelled()
        on_event(event)

    return _emit


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
    cwd: str | None = None,
) -> Callable[[], RunResult]:
    """A zero-arg callable returning the full ``RunResult`` of one run.

    ``profile=None`` runs unconstrained (the experiment baseline).
    """
    ctrl = controller or RuntimeController()

    def _run() -> RunResult:
        if profile is None:
            return execute_command(command, timeout=timeout, cwd=cwd)
        return ctrl.run(profile=profile, command=command, timeout=timeout, cwd=cwd)

    return _run


def build_isolation_runners(
    target: EnvironmentProfile,
    command: str,
    timeout: float,
    controller: RuntimeController | None = None,
    cwd: str | None = None,
) -> tuple[RunFn, dict[str, RunFn]]:
    """Baseline (unconstrained) + one runner per network variable the target
    actually requests, plus the full target profile."""
    ctrl = controller or RuntimeController()
    baseline = make_result_runner(command, None, timeout, ctrl, cwd)

    candidates: dict[str, RunFn] = {}
    net = target.network
    if net is not None and _positive(net.latency_ms):
        latency_only = target.model_copy(deep=True)
        latency_only.network.packet_loss_percent.value = 0.0
        candidates["latency_only"] = make_result_runner(command, latency_only, timeout, ctrl, cwd)
    if net is not None and _positive(net.packet_loss_percent):
        loss_only = target.model_copy(deep=True)
        loss_only.network.latency_ms.value = 0.0
        candidates["loss_only"] = make_result_runner(command, loss_only, timeout, ctrl, cwd)

    candidates["full_target"] = make_result_runner(command, target, timeout, ctrl, cwd)
    return baseline, candidates


def run_experiment_live(
    target: EnvironmentProfile,
    command: str,
    trials: int,
    timeout: float,
    *,
    cwd: str | None = None,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
    mode: str = "sequential",
    alpha: float = 0.05,
) -> ExperimentResult:
    """Causal isolation. ``mode="sequential"`` (default) runs paired round-robin
    trials with anytime-valid e-values and stops early; ``"batch"`` runs the
    classic fixed-N design with one Fisher test per condition at the end.
    ``trials`` is the per-condition budget in both modes."""
    if mode not in EXPERIMENT_MODES:
        raise ValueError(f"mode must be one of {EXPERIMENT_MODES}, got {mode!r}")
    baseline, candidates = build_isolation_runners(target, command, timeout, controller, cwd)
    if not candidates:
        candidates = {"treatment": make_result_runner(command, target, timeout, controller, cwd)}
    if mode == "sequential":
        return run_sequential_experiment(
            baseline, candidates, max_rounds=trials, alpha=alpha,
            min_rounds=min(3, trials), on_event=on_event,
        )
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
    *,
    cwd: str | None = None,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
    method: str = "bayesian",
) -> ThresholdResult:
    """Locate the failure boundary of ``parameter``. ``method="bayesian"``
    (default) is probabilistic bisection: ``trials`` is the total trial budget
    and the result carries a credible interval. ``"bisection"`` is the classic
    halving search with ``trials`` runs per probe."""
    if method not in THRESHOLD_METHODS:
        raise ValueError(f"method must be one of {THRESHOLD_METHODS}, got {method!r}")
    ctrl = controller or RuntimeController()

    def run_at(value: float) -> RunResult:
        candidate = set_profile_parameter(base, parameter, value)
        return ctrl.run(profile=candidate, command=command, timeout=timeout, cwd=cwd)

    if method == "bayesian":
        return locate_boundary(
            parameter, run_at, low, high, max_trials=max(trials, 6), on_event=on_event
        )
    return search_threshold(
        parameter=parameter, run_at=run_at, low=low, high=high, trials=trials, on_event=on_event
    )


def run_replay_live(
    regression: RegressionArtifact | Path | str,
    trials: int,
    timeout: float,
    on_event: OnEvent,
    controller: RuntimeController | None = None,
    run_fn: Callable[[], RunResult] | None = None,
) -> ReplayResult:
    """Re-run a saved regression bundle under its own environment, emitting a
    trial event per run, then check the failure rate against its tolerance.

    Trials run from the directory the bundle was recorded in
    (``metadata["cwd"]``), so a project-based experiment replays correctly.
    ``run_fn`` overrides the runner (demo mode / tests)."""
    artifact = (
        regression
        if isinstance(regression, RegressionArtifact)
        else load_regression(regression)
    )
    if run_fn is None:
        ctrl = controller or RuntimeController()
        cwd = artifact.metadata.get("cwd") if isinstance(artifact.metadata, dict) else None
        run_fn = make_result_runner(artifact.command, artifact.environment, timeout, ctrl, cwd)
    batch = run_trials(run_fn, trials, f"replay:{artifact.regression_id}", on_event=on_event)

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
