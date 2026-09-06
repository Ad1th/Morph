"""Bridge between the pure experiment engine and real command execution.

`morph.engine.experiment` and `morph.engine.threshold` are deliberately
decoupled from the runtime: they take plain callbacks (`run_fn`, `run_at`) so
they stay unit-testable without a target application. This module builds those
callbacks from an `EnvironmentProfile` and a command string.

Both the API `/experiments` route and the `morph experiment` / `morph threshold`
CLI commands construct their runners here, so the two entry points always run
the identical experiment.
"""

from __future__ import annotations

from collections.abc import Callable

from morph.runtime.controller import RuntimeController
from morph.runtime.runner import execute_command
from morph.schema.profile import EnvironmentProfile

RunFn = Callable[[], bool]
RunAtFn = Callable[[float], bool]


def _field_is_positive(field: object) -> bool:
    """True when a ProfileField holds a numeric value greater than zero."""
    value = getattr(field, "value", None)
    try:
        return float(value or 0.0) > 0.0
    except (TypeError, ValueError):
        return False


def make_run_fn(
    command: str,
    profile: EnvironmentProfile | None,
    timeout: float,
    controller: RuntimeController | None = None,
) -> RunFn:
    """Return a zero-arg callable that runs ``command`` once and reports pass/fail.

    ``profile=None`` runs the command unconstrained (the experiment baseline);
    any other profile is applied through the RuntimeController first.
    """
    ctrl = controller or RuntimeController()

    def _run() -> bool:
        if profile is None:
            return execute_command(command, timeout=timeout).passed
        return ctrl.run(profile=profile, command=command, timeout=timeout).passed

    return _run


def build_baseline_and_candidates(
    target_profile: EnvironmentProfile | None,
    command: str,
    timeout: float,
    controller: RuntimeController | None = None,
) -> tuple[RunFn, dict[str, RunFn]]:
    """Build the runners for a single-variable isolation experiment.

    - baseline: the command on the unconstrained host.
    - candidates: one runner per isolated network variable that the target
      profile actually requests (latency alone, packet loss alone), plus the
      full target profile.

    When ``target_profile`` is None the candidate map is empty; callers decide
    what to substitute.
    """
    ctrl = controller or RuntimeController()
    baseline_fn = make_run_fn(command, None, timeout, ctrl)

    candidates: dict[str, RunFn] = {}
    if target_profile is None:
        return baseline_fn, candidates

    net = target_profile.network
    if net is not None and _field_is_positive(net.latency_ms):
        latency_only = target_profile.model_copy(deep=True)
        latency_only.network.packet_loss_percent.value = 0.0
        candidates["latency_only"] = make_run_fn(command, latency_only, timeout, ctrl)

    if net is not None and _field_is_positive(net.packet_loss_percent):
        loss_only = target_profile.model_copy(deep=True)
        loss_only.network.latency_ms.value = 0.0
        candidates["loss_only"] = make_run_fn(command, loss_only, timeout, ctrl)

    candidates["full_treatment"] = make_run_fn(command, target_profile, timeout, ctrl)
    return baseline_fn, candidates


def set_profile_parameter(
    profile: EnvironmentProfile, dotted_path: str, value: float
) -> EnvironmentProfile:
    """Return a deep copy of ``profile`` with one field's value replaced.

    ``dotted_path`` addresses a ProfileField by section and name, e.g.
    ``network.latency_ms``, ``cpu.cores``, ``memory.total_mb``.
    """
    updated = profile.model_copy(deep=True)
    parts = dotted_path.split(".")
    if len(parts) < 2:
        raise ValueError(
            f"Parameter '{dotted_path}' must be '<section>.<field>', e.g. 'network.latency_ms'"
        )

    section = updated
    for part in parts[:-1]:
        section = getattr(section, part, None)
        if section is None:
            raise ValueError(f"Profile has no '{part}' section for parameter '{dotted_path}'")

    leaf = getattr(section, parts[-1], None)
    if leaf is None or not hasattr(leaf, "value"):
        raise ValueError(f"'{dotted_path}' is not a settable profile field")

    leaf.value = value
    return updated


def make_threshold_run_fn(
    command: str,
    profile: EnvironmentProfile,
    parameter: str,
    timeout: float,
    controller: RuntimeController | None = None,
) -> RunAtFn:
    """Return ``run_at(value)`` for `search_threshold`: set ``parameter`` to
    ``value`` on the profile, run the command once, and report pass/fail."""
    ctrl = controller or RuntimeController()

    def _run_at(value: float) -> bool:
        candidate = set_profile_parameter(profile, parameter, value)
        return ctrl.run(profile=candidate, command=command, timeout=timeout).passed

    return _run_at
