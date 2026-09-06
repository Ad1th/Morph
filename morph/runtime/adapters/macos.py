"""macOS runtime adapter using dnctl/pfctl when root, with ProxyAdapter fallback."""

from __future__ import annotations

import os
import shutil
import subprocess

from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter


class MacOSAdapter(BaseAdapter):
    """Adapter for macOS environment condition simulation."""

    def __init__(self) -> None:
        super().__init__()
        self._proxy: ProxyAdapter | None = None
        self._pipe_num: int = 1
        self._used_dnctl: bool = False

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": True,
            "memory": False,
            "locale": True,
        }

    def apply_network(
        self,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_mbps: float | None = None,
    ) -> None:
        if latency_ms <= 0.0 and packet_loss_percent <= 0.0:
            return

        is_root = os.name != "nt" and os.geteuid() == 0
        has_dnctl = shutil.which("dnctl") is not None

        if is_root and has_dnctl:
            try:
                cmd = ["dnctl", "pipe", str(self._pipe_num), "config"]
                if latency_ms > 0:
                    cmd.extend(["delay", f"{latency_ms}ms"])
                if packet_loss_percent > 0:
                    cmd.extend(["plr", str(packet_loss_percent / 100.0)])
                if bandwidth_mbps:
                    cmd.extend(["bw", f"{bandwidth_mbps}Mbit/s"])
                subprocess.run(cmd, check=True, capture_output=True)
                self._used_dnctl = True
                return
            except (subprocess.SubprocessError, OSError):
                pass

        # Unprivileged fallback: user-space TCP proxy
        self._proxy = ProxyAdapter()
        self._proxy.apply_network(
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_mbps=bandwidth_mbps,
        )
        self._env_overrides.update(self._proxy.get_env_overrides())

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._env_overrides["MORPH_MAX_CORES"] = str(max_cores)
            # macOS doesn't have cgroups, but taskpolicy background or nice can throttle
            self._env_overrides["MORPH_CPU_THROTTLE"] = "1"
        if quota_percent is not None and quota_percent > 0:
            self._env_overrides["MORPH_CPU_QUOTA_PERCENT"] = str(quota_percent)

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            self._env_overrides["MORPH_MEMORY_LIMIT_MB"] = str(limit_mb)

    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        if locale_str:
            self._env_overrides["LC_ALL"] = locale_str
            self._env_overrides["LANG"] = locale_str
        if timezone:
            self._env_overrides["TZ"] = timezone

    def cleanup(self) -> None:
        if self._proxy is not None:
            self._proxy.cleanup()
            self._proxy = None

        if self._used_dnctl:
            try:
                subprocess.run(
                    ["dnctl", "-q", "flush"],
                    check=False,
                    capture_output=True,
                )
            except OSError:
                pass
            self._used_dnctl = False

        self._env_overrides.clear()
