"""Runtime Controller: orchestrates environment condition reproduction and execution.

The controller only ever runs on THIS machine. Routing a run to a remote
worker is an explicit, visible decision made by `morph.cloud.dispatch.run_anywhere`
(`morph run --cloud`); it never happens as a side effect of constructing a
controller, and a worker that is down never degrades into a silent local run.
"""

from __future__ import annotations

import platform
import random

from morph.runtime.adapters.base import BaseAdapter, Fidelity, ProxyAdapter
from morph.runtime.adapters.linux import LinuxAdapter
from morph.runtime.adapters.macos import MacOSAdapter
from morph.runtime.adapters.windows import WindowsAdapter
from morph.runtime.runner import execute_command
from morph.schema.profile import EnvironmentProfile, FieldStatus, ProfileField
from morph.schema.telemetry import FidelityEntry, RunResult
from morph.telemetry.provenance import profile_hash, seed_from_env


def get_default_adapter(force_proxy: bool = False) -> BaseAdapter:
    """Return the default system adapter for the current host OS, or ProxyAdapter if forced."""
    if force_proxy:
        return ProxyAdapter()

    sys_name = platform.system().lower()
    if sys_name == "darwin":
        return MacOSAdapter()
    elif sys_name == "linux":
        return LinuxAdapter()
    elif sys_name == "windows":
        return WindowsAdapter()
    else:
        return ProxyAdapter()


def _field(profile: EnvironmentProfile, path: str) -> ProfileField | None:
    section, _, name = path.partition(".")
    obj = getattr(profile, section, None)
    if obj is None:
        return None
    return getattr(obj, name, None)


def fidelity_report(
    profile: EnvironmentProfile, adapter: BaseAdapter | None = None
) -> dict[str, Fidelity]:
    """What the adapter did (after a run) or would do (before one) for each field.

    After `apply_conditions` the adapter's own record is authoritative; before
    it, `adapter.plan(profile)` predicts without side effects.
    """
    adapter = adapter or get_default_adapter()
    applied = adapter.fidelity()
    return applied if applied else adapter.plan(profile)


def reconcile_profile_statuses(
    profile: EnvironmentProfile, adapter: BaseAdapter | None = None
) -> EnvironmentProfile:
    """Evaluate an EnvironmentProfile against what the adapter can really do and update statuses.

    Marks fields as REPRODUCED, APPROXIMATED, or UNAVAILABLE using the
    adapter's per-field fidelity, not its class-level capability booleans: a
    proxy-shaped network is APPROXIMATED, an env-var CPU knob nothing consumes
    is UNAVAILABLE. Returns a copy of the profile with updated statuses.
    """
    adapter = adapter or get_default_adapter()
    report = fidelity_report(profile, adapter)
    updated = profile.model_copy(deep=True)

    # OS: nothing applies it; it either matches the host or it does not.
    current_os = platform.system().lower()
    target_os = str(updated.os.family.value).lower()
    if target_os == current_os:
        updated.os.family.status = FieldStatus.REPRODUCED
        updated.os.version.status = FieldStatus.APPROXIMATED
    else:
        updated.os.family.status = FieldStatus.UNAVAILABLE
        updated.os.version.status = FieldStatus.UNAVAILABLE

    # Architecture: likewise a property of the host.
    updated.cpu.architecture.status = (
        FieldStatus.REPRODUCED
        if str(updated.cpu.architecture.value) == platform.machine()
        else FieldStatus.UNAVAILABLE
    )

    # Everything an adapter applies: status from the report, else UNAVAILABLE.
    for path in (
        "cpu.cores", "cpu.quota_percent",
        "memory.total_mb",
        "locale.locale", "locale.timezone",
        "network.latency_ms", "network.packet_loss_percent", "network.bandwidth_mbps",
    ):
        field = _field(updated, path)
        if field is None:
            continue
        entry = report.get(path)
        field.status = entry.status if entry is not None else FieldStatus.UNAVAILABLE

    return updated


class RuntimeController:
    """Master controller managing adapter lifecycles and application execution."""

    def __init__(
        self,
        adapter: BaseAdapter | None = None,
        force_proxy: bool = False,
        seed: int | None = None,
    ) -> None:
        self.adapter = adapter or get_default_adapter(force_proxy=force_proxy)
        # Explicit seed > MORPH_SEED > a fresh one per run (recorded on the
        # result, so any trial can be replayed with the same loss pattern).
        self.seed = seed if seed is not None else seed_from_env()

    def apply_conditions(self, profile: EnvironmentProfile) -> None:
        """Apply all relevant conditions from the environment profile via the active adapter."""
        # 1. Network conditions
        if profile.network:
            latency = float(profile.network.latency_ms.value or 0.0)
            loss = float(profile.network.packet_loss_percent.value or 0.0)
            bw = (
                float(profile.network.bandwidth_mbps.value)
                if profile.network.bandwidth_mbps and profile.network.bandwidth_mbps.value
                else None
            )
            # "Offline" has no dedicated mechanism: it reuses the existing
            # proxy path with loss forced to 100%, which stalls every chunk
            # until the path is declared dead and the connection reset --
            # what a disconnected machine actually looks like to a client
            # (ui-spec.md section 5: "Network availability = Offline ->
            # latency/bandwidth/loss/jitter greyed and ignored").
            if profile.network.available and profile.network.available.value is False:
                loss = 100.0
            self.adapter.apply_network(
                latency_ms=latency,
                packet_loss_percent=loss,
                bandwidth_mbps=bw,
            )

        # 2. CPU constraints
        if profile.cpu and profile.cpu.cores:
            try:
                cores = int(profile.cpu.cores.value)
                quota = (
                    float(profile.cpu.quota_percent.value)
                    if profile.cpu.quota_percent and profile.cpu.quota_percent.value is not None
                    else None
                )
                self.adapter.apply_cpu(max_cores=cores, quota_percent=quota)
            except (ValueError, TypeError):
                pass

        # 3. Memory constraints
        if profile.memory and profile.memory.total_mb:
            try:
                mem_mb = int(profile.memory.total_mb.value)
                self.adapter.apply_memory(limit_mb=mem_mb)
            except (ValueError, TypeError):
                pass

        # 4. Locale & Timezone
        locale_str = str(profile.locale.locale.value) if profile.locale and profile.locale.locale else None
        timezone = str(profile.locale.timezone.value) if profile.locale and profile.locale.timezone else None
        self.adapter.apply_locale(locale_str=locale_str, timezone=timezone)

    def run(
        self,
        profile: EnvironmentProfile,
        command: str,
        timeout: float = 30.0,
        cwd: str | None = None,
    ) -> RunResult:
        """Apply environment conditions, execute the command, capture telemetry, and guarantee cleanup.

        `profile.process.timeout_s`, if requested, overrides the `timeout`
        argument; `max_processes`/`fd_limit` are POSIX-only rlimits applied
        to the child (see `morph.telemetry.collector.run_with_telemetry`).

        The returned RunResult carries provenance (`seed`, `profile_hash`,
        `adapter`, `fidelity`, plus what the collector stamps) so it can be
        reproduced and attributed.
        """
        effective_timeout = timeout
        if profile.process:
            if (
                profile.process.timeout_s
                and profile.process.timeout_s.value is not None
                and float(profile.process.timeout_s.value) > 0
            ):
                effective_timeout = float(profile.process.timeout_s.value)

        seed = self.seed if self.seed is not None else random.getrandbits(32)
        if hasattr(self.adapter, "seed"):
            self.adapter.seed = seed

        try:
            self.apply_conditions(profile)
            env_overrides = self.adapter.get_env_overrides()
            env_overrides.setdefault("MORPH_SEED", str(seed))
            if profile.env_vars:
                # Explicit user-requested variables take precedence over the
                # adapter's own (locale/proxy) overrides.
                env_overrides = {**env_overrides, **profile.env_vars}

            max_processes = fd_limit = None
            if profile.process:
                if profile.process.max_processes and profile.process.max_processes.value is not None:
                    max_processes = int(profile.process.max_processes.value)
                if profile.process.fd_limit and profile.process.fd_limit.value is not None:
                    fd_limit = int(profile.process.fd_limit.value)

            result = execute_command(
                command, env_overrides=env_overrides, timeout=effective_timeout, cwd=cwd,
                max_processes=max_processes, fd_limit=fd_limit,
                cgroup_path=self.adapter.cgroup_path(),
            )
            result.seed = seed
            result.profile_hash = profile_hash(profile)
            result.adapter = type(self.adapter).__name__
            result.fidelity = {
                path: FidelityEntry(**entry) for path, entry in self.adapter.report().items()
            }
            return result
        finally:
            self.adapter.cleanup()
