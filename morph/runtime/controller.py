"""Runtime Controller: orchestrates environment condition reproduction and execution."""

from __future__ import annotations

import platform

from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter
from morph.runtime.adapters.linux import LinuxAdapter
from morph.runtime.adapters.macos import MacOSAdapter
from morph.runtime.adapters.windows import WindowsAdapter
from morph.runtime.runner import execute_command
from morph.schema.profile import EnvironmentProfile, FieldStatus
from morph.schema.telemetry import RunResult


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


def reconcile_profile_statuses(
    profile: EnvironmentProfile, adapter: BaseAdapter | None = None
) -> EnvironmentProfile:
    """Evaluate an EnvironmentProfile against adapter capabilities and update FieldStatuses.

    Marks fields as REPRODUCED, APPROXIMATED, or UNAVAILABLE.
    Returns a copy of the profile with updated statuses.
    """
    adapter = adapter or get_default_adapter()
    caps = adapter.capabilities()
    updated = profile.model_copy(deep=True)

    # OS reconciliation
    current_os = platform.system().lower()
    target_os = str(updated.os.family.value).lower()
    if target_os == current_os:
        updated.os.family.status = FieldStatus.REPRODUCED
        updated.os.version.status = FieldStatus.APPROXIMATED
    else:
        updated.os.family.status = FieldStatus.UNAVAILABLE
        updated.os.version.status = FieldStatus.UNAVAILABLE

    # CPU reconciliation
    if caps.get("cpu", False):
        updated.cpu.cores.status = FieldStatus.APPROXIMATED
        updated.cpu.architecture.status = (
            FieldStatus.REPRODUCED
            if str(updated.cpu.architecture.value) == platform.machine()
            else FieldStatus.UNAVAILABLE
        )
    else:
        updated.cpu.cores.status = FieldStatus.UNAVAILABLE
        updated.cpu.architecture.status = FieldStatus.UNAVAILABLE

    # Memory reconciliation
    if caps.get("memory", False):
        updated.memory.total_mb.status = FieldStatus.APPROXIMATED
    else:
        updated.memory.total_mb.status = FieldStatus.UNAVAILABLE

    # Locale reconciliation
    if caps.get("locale", False):
        updated.locale.locale.status = FieldStatus.REPRODUCED
        updated.locale.timezone.status = FieldStatus.REPRODUCED
    else:
        updated.locale.locale.status = FieldStatus.UNAVAILABLE
        updated.locale.timezone.status = FieldStatus.UNAVAILABLE

    # Network reconciliation
    if updated.network:
        if caps.get("network", False):
            updated.network.latency_ms.status = FieldStatus.REPRODUCED
            updated.network.packet_loss_percent.status = FieldStatus.REPRODUCED
            if updated.network.bandwidth_mbps:
                updated.network.bandwidth_mbps.status = FieldStatus.APPROXIMATED
        else:
            updated.network.latency_ms.status = FieldStatus.UNAVAILABLE
            updated.network.packet_loss_percent.status = FieldStatus.UNAVAILABLE

    return updated


class RuntimeController:
    """Master controller managing adapter lifecycles and application execution."""

    def __init__(
        self,
        adapter: BaseAdapter | None = None,
        force_proxy: bool = False,
        worker: RemoteWorker | None = None,
    ) -> None:
        self.adapter = adapter or get_default_adapter(force_proxy=force_proxy)
        if worker is not None:
            self.worker = worker
        else:
            try:
                from morph.cloud.worker import RemoteWorker as _RemoteWorker
                from morph.config import load_config
                cfg = load_config()
                worker_cfg = cfg.worker if cfg.worker.host else cfg.cloud
                self.worker = _RemoteWorker(worker_cfg)
            except Exception:
                self.worker = None

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
            # proxy path with loss forced to 100%, which genuinely drops
            # every packet rather than approximating disconnection some
            # other way (ui-spec.md section 5: "Network availability =
            # Offline -> latency/bandwidth/loss/jitter greyed and ignored").
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

        If this host cannot reproduce the requested profile and a remote worker is configured,
        the trial is dispatched to the worker over SSH.
        """
        effective_timeout = timeout
        if profile.process:
            if (
                profile.process.timeout_s
                and profile.process.timeout_s.value is not None
                and float(profile.process.timeout_s.value) > 0
            ):
                effective_timeout = float(profile.process.timeout_s.value)

        # Check for local capability gap and dispatch to worker if configured
        if self.worker and self.worker.configured:
            try:
                from morph.cloud.capability import assess_locally
                cap = assess_locally(profile)
                if not cap.reproducible_locally:
                    return self.worker.run(profile=profile, command=command, timeout=effective_timeout)
            except Exception:
                pass

        try:
            self.apply_conditions(profile)
            env_overrides = self.adapter.get_env_overrides()
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

            return execute_command(
                command, env_overrides=env_overrides, timeout=effective_timeout, cwd=cwd,
                max_processes=max_processes, fd_limit=fd_limit,
            )
        finally:
            self.adapter.cleanup()

