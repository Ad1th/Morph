"""Service layer: the one orchestration path behind the CLI and the API.

`morph experiment` / `morph threshold` and `POST /experiments` /
`POST /threshold` used to each wire profiles -> runners -> engine on their own
(with different candidate labels, defaults, and error handling). Both now call
into this module, so the same request is the same experiment however it
arrives. The TUI keeps its own orchestrator for now (out of scope here).

What lives here:

* :class:`IsolationSpec` / :class:`ThresholdSpec` -- validated request objects.
* :func:`run_isolation` / :func:`run_threshold` -- build runners, probe for
  setup errors, run the engine, return the engine's own result models.
* :class:`SetupError` -- raised (never counted as an application failure) when
  the command cannot even launch: missing binary, bad ``cwd``, permission
  denied. Exit codes 126/127 and the collector's ``FileNotFoundError`` /
  ``PermissionError`` error types are the signal.
* :class:`JobRegistry` -- background experiments the API can cancel, and the
  hook the server's lifespan uses so Ctrl-C never leaves shaping applied.
* :func:`doctor` -- the local health checks behind ``morph doctor``.

This module deliberately imports no FastAPI or Typer.
"""

from __future__ import annotations

import importlib
import os
import platform
import shutil
import subprocess
import sys
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from morph.api import defaults
from morph.engine.progress import OnEvent, emit
from morph.engine.runners import set_profile_parameter, with_unconstrained_network
from morph.schema.comparison import ThresholdResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult
from morph.schema.profile import EnvironmentProfile, FieldStatus, NetworkInfo, ProfileField
from morph.schema.telemetry import RunResult

ResultRunner = Callable[[], RunResult]


# --------------------------------------------------------------------------- #
# errors
# --------------------------------------------------------------------------- #


class SetupError(RuntimeError):
    """The command could not be launched at all.

    This is *not* an application failure and must never be counted as one:
    a bad ``cwd`` or a missing interpreter would otherwise fail every trial of
    every condition and produce a confident ``no_effect`` verdict from zero
    real executions.
    """

    def __init__(self, result: RunResult, command: str, cwd: str | None = None) -> None:
        self.result = result
        self.command = command
        self.cwd = cwd
        super().__init__(setup_error_message(result, command, cwd))


class Cancelled(RuntimeError):
    """A background experiment was asked to stop between trials."""


def setup_error_types() -> tuple[type[BaseException], ...]:
    """Exception types a caller should report as "setup error" (exit 2 / HTTP 422)."""
    try:
        from morph.engine.errors import InvalidTrialError
    except ImportError:  # engine without the invalid-trial convention
        return (SetupError,)
    return (SetupError, InvalidTrialError)


class ProfileLoadError(ValueError):
    """A profile file is missing or is not an EnvironmentProfile."""


SETUP_ERROR_TYPES = frozenset({"FileNotFoundError", "PermissionError", "NotADirectoryError"})
SETUP_EXIT_CODES = frozenset({126, 127})


def is_setup_error(result: RunResult) -> bool:
    """True when ``result`` says the process never ran (as opposed to ran and failed)."""
    if result.passed:
        return False
    if getattr(result, "invalid", False):
        return True
    if result.error_type in SETUP_ERROR_TYPES:
        return True
    return result.exit_code in SETUP_EXIT_CODES and (
        result.error_type in SETUP_ERROR_TYPES or result.error_type is None or not result.stdout
    )


def setup_error_message(result: RunResult, command: str, cwd: str | None = None) -> str:
    where = f" (cwd: {cwd})" if cwd else ""
    reason = (
        getattr(result, "invalid_reason", None)
        or result.error_message
        or result.stderr.strip()
        or result.error_type
        or "unknown reason"
    )
    if result.exit_code == 127 or result.error_type == "FileNotFoundError":
        hint = "command or working directory not found"
    elif result.exit_code == 126 or result.error_type == "PermissionError":
        hint = "command is not executable"
    else:
        hint = "could not launch"
    return f"setup error: {hint}{where}: {command!r}: {reason}"


# --------------------------------------------------------------------------- #
# profiles
# --------------------------------------------------------------------------- #


def load_profile_file(path: str | Path) -> EnvironmentProfile:
    """Read an EnvironmentProfile JSON file; a clear error instead of a traceback."""
    p = Path(path)
    if not p.is_file():
        raise ProfileLoadError(f"Profile file '{p}' not found")
    try:
        return EnvironmentProfile.model_validate_json(p.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        first = str(exc).strip().splitlines()[0] if str(exc).strip() else exc.__class__.__name__
        raise ProfileLoadError(f"'{p}' is not an EnvironmentProfile: {first}") from exc


def default_target_profile(
    latency_ms: float = defaults.DEMO_LATENCY_MS,
    packet_loss_percent: float = defaults.DEMO_PACKET_LOSS_PERCENT,
    base: EnvironmentProfile | None = None,
) -> EnvironmentProfile:
    """The host profile plus a requested network condition.

    This is what `morph experiment` uses when no ``--profile`` is given: the
    machine as it is, with latency / packet loss requested on top.
    """
    from morph.profiler.capture import capture_environment

    target = (base or capture_environment()).model_copy(deep=True)
    target.network = NetworkInfo(
        latency_ms=ProfileField(value=float(latency_ms), status=FieldStatus.REQUESTED),
        packet_loss_percent=ProfileField(
            value=float(packet_loss_percent), status=FieldStatus.REQUESTED
        ),
    )
    return target


# --------------------------------------------------------------------------- #
# runners
# --------------------------------------------------------------------------- #


def _positive(fld: object) -> bool:
    value = getattr(fld, "value", None)
    try:
        return float(value or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def make_result_runner(
    command: str,
    profile: EnvironmentProfile | None,
    timeout: float,
    controller: Any | None = None,
    cwd: str | None = None,
    stop_event: threading.Event | None = None,
) -> ResultRunner:
    """A zero-arg callable that runs ``command`` once and returns its ``RunResult``.

    Returning the full result (rather than a bool) lets progress events carry
    stdout/stderr and timing. A setup error raises :class:`SetupError` so the
    engine aborts instead of tallying it; a set ``stop_event`` raises
    :class:`Cancelled` before the next trial starts.
    """
    from morph.runtime.controller import RuntimeController
    from morph.runtime.runner import execute_command

    ctrl = controller or RuntimeController()

    def _run() -> RunResult:
        if stop_event is not None and stop_event.is_set():
            raise Cancelled("experiment cancelled")
        if profile is None:
            result = execute_command(command, timeout=timeout, cwd=cwd)
        else:
            result = ctrl.run(profile=profile, command=command, timeout=timeout, cwd=cwd)
        # A result the runtime flagged `invalid` is left to the engine, which
        # retries it and raises InvalidTrialError; the exit-code heuristic
        # covers a runtime that has not set the flag.
        if is_setup_error(result) and not getattr(result, "invalid", False):
            raise SetupError(result, command, cwd)
        return result

    return _run


def build_isolation_runners(
    target: EnvironmentProfile | None,
    command: str,
    timeout: float,
    controller: Any | None = None,
    cwd: str | None = None,
    stop_event: threading.Event | None = None,
) -> tuple[ResultRunner, dict[str, ResultRunner]]:
    """Baseline (unconstrained host) plus one candidate per isolated network
    variable the target requests (``latency_only``, ``loss_only``) and the
    full target (``full_treatment``).

    Without a target there is nothing to isolate: the candidate map is empty
    and callers must refuse rather than compare the command against itself.
    """
    from morph.runtime.controller import RuntimeController

    ctrl = controller or RuntimeController()
    baseline = make_result_runner(command, None, timeout, ctrl, cwd, stop_event)
    candidates: dict[str, ResultRunner] = {}
    if target is None:
        return baseline, candidates

    net = target.network
    if net is not None and _positive(net.latency_ms):
        latency_only = target.model_copy(deep=True)
        latency_only.network.packet_loss_percent.value = 0.0
        candidates["latency_only"] = make_result_runner(
            command, latency_only, timeout, ctrl, cwd, stop_event
        )
    if net is not None and _positive(net.packet_loss_percent):
        loss_only = target.model_copy(deep=True)
        loss_only.network.latency_ms.value = 0.0
        candidates["loss_only"] = make_result_runner(command, loss_only, timeout, ctrl, cwd, stop_event)

    candidates["full_treatment"] = make_result_runner(command, target, timeout, ctrl, cwd, stop_event)
    return baseline, candidates


def probe_setup(
    command: str, timeout: float, cwd: str | None = None, on_event: OnEvent | None = None
) -> RunResult:
    """Run the command once, unconstrained, purely to prove it can launch.

    Raises :class:`SetupError` when it cannot. The outcome (pass or fail) is
    deliberately *not* fed into any statistic: this run exists so an
    experiment stops before spending trials on a command that never starts.
    """
    from morph.runtime.runner import execute_command

    emit(on_event, TrialEvent(kind="phase_start", phase="probe", condition="baseline"))
    result = execute_command(command, timeout=timeout, cwd=cwd)
    if is_setup_error(result):
        raise SetupError(result, command, cwd)
    emit(
        on_event,
        TrialEvent(
            kind="phase_done",
            phase="probe",
            condition="baseline",
            passed=result.passed,
            duration_ms=result.duration_ms,
            extra={"exit_code": result.exit_code},
        ),
    )
    return result


# --------------------------------------------------------------------------- #
# specs
# --------------------------------------------------------------------------- #


@dataclass
class IsolationSpec:
    """Everything an isolation experiment needs, already validated."""

    command: str
    target_profile: EnvironmentProfile | None = None
    cwd: str | None = None
    timeout: float = defaults.TIMEOUT_SEC
    mode: str = defaults.DEFAULT_EXPERIMENT_MODE
    trials: int = defaults.TRIALS
    max_rounds: int = defaults.SEQUENTIAL_MAX_ROUNDS
    alpha: float = defaults.ALPHA
    min_rounds: int = defaults.SEQUENTIAL_MIN_ROUNDS
    probe: bool = True

    def validate(self) -> IsolationSpec:
        if not self.command or not self.command.strip():
            raise ValueError("'command' must not be empty")
        if self.mode not in defaults.EXPERIMENT_MODES:
            raise ValueError(f"'mode' must be one of {', '.join(defaults.EXPERIMENT_MODES)}")
        if self.trials < 1:
            raise ValueError("'trials' must be at least 1")
        if self.max_rounds < 1:
            raise ValueError("'max_rounds' must be at least 1")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("'alpha' must be strictly between 0 and 1")
        if self.timeout <= 0:
            raise ValueError("'timeout' must be greater than 0")
        if self.target_profile is None:
            raise ValueError(
                "'target_profile' is required: without a target there is no condition to isolate"
            )
        return self


# Parameters that hurt when they get SMALLER: the boundary search runs on the
# negated axis for these and reports real units (see boundary.locate_boundary).
DECREASING_PARAMETERS = ("process.fd_limit", "process.max_processes", "memory.total_mb",
                         "memory.available_mb", "cpu.cores", "cpu.quota_percent",
                         "network.bandwidth_mbps", "network.bandwidth_kbps")


def parameter_hurts_when_larger(parameter: str) -> bool:
    return parameter not in DECREASING_PARAMETERS


@dataclass
class ThresholdSpec:
    command: str
    parameter: str
    low: float = defaults.THRESHOLD_LOW
    high: float = defaults.THRESHOLD_HIGH
    profile: EnvironmentProfile | None = None
    cwd: str | None = None
    timeout: float = defaults.TIMEOUT_SEC
    method: str = defaults.DEFAULT_THRESHOLD_METHOD
    trials: int = defaults.THRESHOLD_TRIALS
    precision: float | None = None
    max_trials: int = defaults.THRESHOLD_MAX_TRIALS
    credible_mass: float = defaults.THRESHOLD_CREDIBLE_MASS
    probe: bool = True

    def validate(self) -> ThresholdSpec:
        if not self.command or not self.command.strip():
            raise ValueError("'command' must not be empty")
        if self.method not in defaults.THRESHOLD_METHODS:
            raise ValueError(f"'method' must be one of {', '.join(defaults.THRESHOLD_METHODS)}")
        if self.high <= self.low:
            raise ValueError("'high' must be greater than 'low'")
        if self.trials < 1:
            raise ValueError("'trials' must be at least 1")
        if self.max_trials < 1:
            raise ValueError("'max_trials' must be at least 1")
        if self.precision is not None and self.precision <= 0:
            raise ValueError("'precision' must be greater than 0")
        if not 0.0 < self.credible_mass < 1.0:
            raise ValueError("'credible_mass' must be strictly between 0 and 1")
        if self.timeout <= 0:
            raise ValueError("'timeout' must be greater than 0")
        return self

    @property
    def effective_precision(self) -> float:
        if self.precision is not None:
            return self.precision
        return defaults.default_precision(self.low, self.high)


# --------------------------------------------------------------------------- #
# orchestration
# --------------------------------------------------------------------------- #


def run_isolation(
    spec: IsolationSpec,
    *,
    on_event: OnEvent | None = None,
    stop_event: threading.Event | None = None,
    controller: Any | None = None,
) -> ExperimentResult:
    """Probe, build runners, run the engine in the requested mode.

    Raises ``ValueError`` on a bad spec, :class:`SetupError` when the command
    cannot launch, :class:`Cancelled` when ``stop_event`` is set mid-run.
    """
    spec.validate()
    if spec.probe:
        probe_setup(spec.command, spec.timeout, spec.cwd, on_event)

    baseline, candidates = build_isolation_runners(
        spec.target_profile, spec.command, spec.timeout, controller, spec.cwd, stop_event
    )
    if not candidates:  # a target with no network request: run it as one treatment
        candidates = {
            "full_treatment": make_result_runner(
                spec.command, spec.target_profile, spec.timeout, controller, spec.cwd, stop_event
            )
        }

    if spec.mode == "sequential":
        from morph.engine.sequential import run_sequential_experiment

        result = run_sequential_experiment(
            baseline,
            candidates,
            spec.max_rounds,
            alpha=spec.alpha,
            min_rounds=min(spec.min_rounds, spec.max_rounds),
            on_event=on_event,
        )
    else:
        from morph.engine.experiment import run_experiment

        result = run_experiment(baseline, candidates, n=spec.trials, on_event=on_event)

    if spec.target_profile is not None:
        result.target_profile = spec.target_profile
    return result


def run_threshold(
    spec: ThresholdSpec,
    *,
    on_event: OnEvent | None = None,
    stop_event: threading.Event | None = None,
    controller: Any | None = None,
) -> ThresholdResult:
    """Locate the failure boundary of one parameter with the requested method."""
    from morph.runtime.controller import RuntimeController

    spec.validate()
    base = spec.profile
    if base is None:
        from morph.profiler.capture import capture_environment

        base = capture_environment()
    # An absent network section means "unconstrained": fill it so a network
    # parameter can be searched at all (also what the API always did).
    base = with_unconstrained_network(base)
    # Fail on an unknown parameter before spending a single trial.
    set_profile_parameter(base, spec.parameter, spec.low)

    if spec.probe:
        probe_setup(spec.command, spec.timeout, spec.cwd, on_event)

    ctrl = controller or RuntimeController()

    def run_at(value: float) -> RunResult:
        if stop_event is not None and stop_event.is_set():
            raise Cancelled("threshold search cancelled")
        candidate = set_profile_parameter(base, spec.parameter, value)
        result = ctrl.run(profile=candidate, command=spec.command, timeout=spec.timeout, cwd=spec.cwd)
        if is_setup_error(result) and not getattr(result, "invalid", False):
            raise SetupError(result, spec.command, spec.cwd)
        return result

    if spec.method == "bayes":
        from morph.engine.boundary import locate_boundary

        return locate_boundary(
            spec.parameter,
            run_at,
            spec.low,
            spec.high,
            max_trials=spec.max_trials,
            precision=spec.effective_precision,
            credible_mass=spec.credible_mass,
            increasing=parameter_hurts_when_larger(spec.parameter),
            on_event=on_event,
        )

    from morph.engine.threshold import search_threshold

    return search_threshold(
        parameter=spec.parameter,
        run_at=run_at,
        low=spec.low,
        high=spec.high,
        trials=spec.trials,
        precision=spec.effective_precision,
        on_event=on_event,
    )


# --- minimal failing condition set (ddmin over conditions) ------------------- #


def minimize_module():
    """``morph.engine.minimize`` if the engine ships it, else ``None``."""
    try:
        return importlib.import_module("morph.engine.minimize")
    except ImportError:
        return None


HAS_MINIMIZE = minimize_module() is not None

#: Profile fields a target may deviate in, in the order ddmin considers them.
CONDITION_FIELDS = (
    "network.latency_ms",
    "network.packet_loss_percent",
    "network.bandwidth_mbps",
    "cpu.cores",
    "cpu.quota_percent",
    "memory.total_mb",
    "locale.locale",
    "locale.timezone",
    "process.max_processes",
    "process.fd_limit",
)


def _field_value(profile: EnvironmentProfile, dotted: str) -> Any:
    node: Any = profile
    for part in dotted.split("."):
        node = getattr(node, part, None)
        if node is None:
            return None
    return getattr(node, "value", None)


def deviating_conditions(target: EnvironmentProfile, base: EnvironmentProfile) -> list[str]:
    """Dotted fields where ``target`` asks for something other than ``base``."""
    out: list[str] = []
    for dotted in CONDITION_FIELDS:
        t = _field_value(target, dotted)
        if t is None:
            continue
        b = _field_value(base, dotted)
        if dotted.startswith("network."):
            try:
                if float(t or 0.0) <= 0.0:
                    continue
            except (TypeError, ValueError):
                pass
        if t != b:
            out.append(dotted)
    return out


@dataclass
class MinimizeSpec:
    command: str
    target_profile: EnvironmentProfile
    conditions: list[str] | None = None
    base_profile: EnvironmentProfile | None = None
    cwd: str | None = None
    timeout: float = defaults.TIMEOUT_SEC
    runs: int = 3
    failure_rate_threshold: float = 0.5
    probe: bool = True

    def validate(self) -> MinimizeSpec:
        if not self.command or not self.command.strip():
            raise ValueError("'command' must not be empty")
        if self.runs < 1:
            raise ValueError("'runs' must be at least 1")
        if not 0.0 <= self.failure_rate_threshold < 1.0:
            raise ValueError("'failure_rate_threshold' must be in [0, 1)")
        if self.timeout <= 0:
            raise ValueError("'timeout' must be greater than 0")
        if self.conditions is not None:
            for dotted in self.conditions:
                set_profile_parameter(with_unconstrained_network(self.target_profile), dotted, 0)
        return self


@dataclass
class MinimizeOutcome:
    conditions: list[str]
    minimal: list[str]
    reproduced: bool
    oracle_calls: int
    history: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "conditions": self.conditions,
            "minimal": self.minimal,
            "reproduced": self.reproduced,
            "oracle_calls": self.oracle_calls,
            "history": self.history,
            "summary": self.summary,
        }


def run_minimize(
    spec: MinimizeSpec,
    *,
    stop_event: threading.Event | None = None,
    controller: Any | None = None,
) -> MinimizeOutcome:
    """ddmin over the conditions the target deviates in: the smallest subset
    that still makes the command fail (``runs`` trials per subset, majority rule)."""
    module = minimize_module()
    if module is None:
        raise RuntimeError("morph.engine.minimize is not available in this build")
    from morph.runtime.controller import RuntimeController

    spec.validate()
    base = spec.base_profile
    if base is None:
        from morph.profiler.capture import capture_environment

        base = capture_environment()
    base = with_unconstrained_network(base)
    target = with_unconstrained_network(spec.target_profile)
    conditions = list(spec.conditions) if spec.conditions is not None else deviating_conditions(target, base)
    if not conditions:
        raise ValueError("the target profile does not deviate from the host in any condition")

    if spec.probe:
        probe_setup(spec.command, spec.timeout, spec.cwd)

    ctrl = controller or RuntimeController()

    def run_fn_for(subset: frozenset[str]) -> Callable[[], RunResult]:
        profile = base
        for dotted in conditions:
            if dotted in subset:
                profile = set_profile_parameter(profile, dotted, _field_value(target, dotted))
        return make_result_runner(spec.command, profile, spec.timeout, ctrl, spec.cwd, stop_event)

    oracle = module.batch_oracle(
        run_fn_for, runs=spec.runs, failure_rate_threshold=spec.failure_rate_threshold
    )
    result = module.ddmin(conditions, oracle)
    minimal = sorted(result.minimal)
    if not result.reproduced:
        summary = (
            f"The full condition set ({', '.join(conditions)}) did not fail "
            f"({spec.runs} runs per subset): nothing to minimise."
        )
    else:
        summary = (
            f"Minimal failing set: {', '.join(minimal)} "
            f"({len(minimal)} of {len(conditions)} conditions, {result.oracle_calls} subsets tried)."
        )
    return MinimizeOutcome(
        conditions=conditions,
        minimal=minimal,
        reproduced=result.reproduced,
        oracle_calls=result.oracle_calls,
        history=[{"conditions": sorted(sub), "fails": fails} for sub, fails in result.history],
        summary=summary,
    )


# --------------------------------------------------------------------------- #
# background jobs (API streaming) + shutdown safety
# --------------------------------------------------------------------------- #


@dataclass
class Job:
    job_id: str
    kind: str  # "experiment" | "threshold"
    stop_event: threading.Event = field(default_factory=threading.Event)
    thread: threading.Thread | None = None
    controller: Any | None = None

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()


class JobRegistry:
    """Background experiments the server can cancel, and clean up after."""

    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, kind: str, controller: Any | None = None) -> Job:
        job = Job(job_id=job_id, kind=kind, controller=controller)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def start(self, job: Job, target: Callable[[], None]) -> None:
        job.thread = threading.Thread(target=target, name=f"{job.kind}-{job.job_id}", daemon=True)
        job.thread.start()

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def running(self) -> list[Job]:
        with self._lock:
            return [j for j in self._jobs.values() if j.running]

    def cancel(self, job_id: str) -> bool:
        """Ask a job to stop between trials. False when unknown or already finished."""
        job = self.get(job_id)
        if job is None or not job.running:
            return False
        job.stop_event.set()
        return True

    def forget(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def shutdown(self, join_timeout: float = 5.0) -> None:
        """Stop every running job and make sure no shaping is left applied.

        Each ``RuntimeController.run`` cleans its adapter up in a ``finally``,
        so a job that stops between trials leaves nothing behind. A job still
        mid-trial after ``join_timeout`` gets its adapter cleaned up from here.
        """
        jobs = self.running()
        for job in jobs:
            job.stop_event.set()
        for job in jobs:
            if job.thread is not None:
                job.thread.join(timeout=join_timeout)
        for job in jobs:
            if job.running and job.controller is not None:
                try:
                    job.controller.adapter.cleanup()
                except Exception:
                    pass
        cleanup_stale_shaping()


def cleanup_stale_shaping() -> dict[str, Any]:
    """Revert tc/dnctl rules left behind by a crashed run, via the runtime's
    crash-safe state file (:mod:`morph.runtime.state`).

    Returns ``{"supported": False}`` on a runtime without the state module,
    else ``{"supported": True, "pending": [...], "reverted": [...], "failed": [...]}``.
    """
    try:
        from morph.runtime import state
    except ImportError:
        return {"supported": False}
    try:
        pending = state.describe()
        results = state.cleanup_stale()
    except Exception as exc:
        return {"supported": True, "error": str(exc)}
    reverted = [f"{e.get('kind')}: {e.get('detail')}" for e, ok in results if ok]
    failed = [f"{e.get('kind')}: {e.get('detail')}" for e, ok in results if not ok]
    return {"supported": True, "pending": pending, "reverted": reverted, "failed": failed}


# --------------------------------------------------------------------------- #
# doctor
# --------------------------------------------------------------------------- #


@dataclass
class Check:
    name: str
    status: str  # "ok" | "warn" | "fail" | "skip"
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.status != "fail"


def _which(name: str) -> str | None:
    return shutil.which(name) or next(
        (p for p in (f"/sbin/{name}", f"/usr/sbin/{name}") if os.path.exists(p)), None
    )


def _sudo_available() -> bool:
    if not shutil.which("sudo"):
        return False
    try:
        proc = subprocess.run(["sudo", "-n", "true"], capture_output=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return False
    return proc.returncode == 0


def _proxy_self_check() -> Check:
    from morph.runtime.adapters.base import ProxyAdapter

    adapter = ProxyAdapter()
    try:
        adapter.apply_network(latency_ms=1.0)
        env = adapter.get_env_overrides()
        port = env.get("MORPH_PROXY_PORT")
        if not port:
            return Check("proxy self-check", "fail", "user-space proxy did not bind a port")
        return Check("proxy self-check", "ok", f"user-space TCP proxy bound 127.0.0.1:{port}")
    except Exception as exc:
        return Check("proxy self-check", "fail", f"{exc.__class__.__name__}: {exc}")
    finally:
        try:
            adapter.cleanup()
        except Exception:
            pass


def doctor(*, network: bool | None = None) -> list[Check]:
    """Local health checks: interpreter, adapter, shaping tools, proxy, config, worker.

    ``network=False`` (or ``MORPH_NO_NETWORK=1``) skips the worker probe.
    """
    import morph
    from morph.config import find_config_path, load_config
    from morph.runtime.controller import get_default_adapter

    if network is None:
        network = not os.environ.get("MORPH_NO_NETWORK")

    checks: list[Check] = []
    checks.append(
        Check(
            "python",
            "ok",
            f"{platform.python_version()} at {sys.executable} (morph {morph.__version__})",
        )
    )

    system = platform.system().lower()
    is_root = os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0
    try:
        adapter = get_default_adapter()
        caps = adapter.capabilities()
        checks.append(
            Check(
                "adapter",
                "ok",
                f"{adapter.__class__.__name__}: "
                + ", ".join(f"{k}={'yes' if v else 'no'}" for k, v in caps.items()),
            )
        )
    except Exception as exc:
        checks.append(Check("adapter", "fail", f"could not construct adapter: {exc}"))

    if system == "linux":
        tc = _which("tc")
        checks.append(
            Check("tc", "ok" if tc else "warn", tc or "not found: network shaping falls back to the proxy")
        )
        cgroup_paths = ("/sys/fs/cgroup/cpu.max", "/sys/fs/cgroup/morph/cpu.max")
        cg = next((p for p in cgroup_paths if os.path.exists(p)), None)
        checks.append(Check("cgroup v2", "ok" if cg else "warn", cg or "cpu.max not found: no CPU quota"))
    elif system == "darwin":
        dn = _which("dnctl")
        checks.append(
            Check("dnctl", "ok" if dn else "warn", dn or "not found: network shaping falls back to the proxy")
        )
    if is_root:
        checks.append(Check("privileges", "ok", "running as root: native shaping available"))
    else:
        sudo_ok = _sudo_available()
        checks.append(
            Check(
                "privileges",
                "ok" if sudo_ok else "warn",
                "passwordless sudo available" if sudo_ok
                else "unprivileged: only the user-space proxy path can shape the network",
            )
        )

    checks.append(_proxy_self_check())

    stale = cleanup_stale_shaping()
    if not stale.get("supported"):
        checks.append(Check("stale shaping", "skip", "runtime has no shaping state file"))
    elif "error" in stale:
        checks.append(Check("stale shaping", "fail", f"state file unreadable: {stale['error']}"))
    elif stale["failed"]:
        checks.append(
            Check("stale shaping", "fail", "could not revert: " + "; ".join(stale["failed"]))
        )
    elif stale["reverted"]:
        checks.append(
            Check("stale shaping", "warn", "reverted stale rules: " + "; ".join(stale["reverted"]))
        )
    elif stale["pending"]:
        checks.append(Check("stale shaping", "ok", "in use by live runs: " + "; ".join(stale["pending"])))
    else:
        checks.append(Check("stale shaping", "ok", "no leftover tc/dnctl rules"))

    home = Path.home() / ".morph"
    try:
        home.mkdir(parents=True, exist_ok=True)
        probe = home / ".doctor-write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        checks.append(Check("~/.morph", "ok", f"writable: {home}"))
    except OSError as exc:
        checks.append(Check("~/.morph", "fail", f"not writable: {exc}"))

    cfg_path = find_config_path()
    if cfg_path is None:
        checks.append(Check("morph.yaml", "skip", "no morph.yaml found (defaults apply)"))
    else:
        try:
            import yaml

            from morph.schema.config import MorphConfig

            MorphConfig.model_validate(yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {})
            checks.append(Check("morph.yaml", "ok", str(cfg_path)))
        except Exception as exc:
            checks.append(Check("morph.yaml", "fail", f"{cfg_path}: {str(exc).splitlines()[0]}"))

    for tool in ("git", "gh", "uv", "npm"):
        path = shutil.which(tool)
        checks.append(Check(tool, "ok" if path else "skip", path or "not installed"))

    try:
        from morph.cloud.worker import RemoteWorker

        cfg = load_config()
        worker = RemoteWorker(getattr(cfg, "cloud", None) or getattr(cfg, "worker", None))
        if not worker.configured:
            checks.append(Check("worker", "skip", "no remote worker configured"))
        elif not network:
            checks.append(Check("worker", "skip", f"{worker.target}: probe skipped (MORPH_NO_NETWORK)"))
        else:
            info = worker.check()
            checks.append(
                Check(
                    "worker",
                    "ok" if info.usable else "fail",
                    f"{worker.target}: reachable={info.reachable} morph={info.morph_importable} "
                    f"tc={info.can_shape_network}" + (f" ({info.detail})" if info.detail else ""),
                )
            )
    except Exception as exc:
        checks.append(Check("worker", "fail", f"could not evaluate worker config: {exc}"))

    return checks
