"""Linux runtime adapter using tc/netem and cgroups when root, with ProxyAdapter fallback."""

from __future__ import annotations

import os
import shutil
import subprocess

from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter


class LinuxAdapter(BaseAdapter):
    """Adapter for Linux environment condition simulation."""

    _CGROUP_CPU_PATHS = ("/sys/fs/cgroup/morph/cpu.max", "/sys/fs/cgroup/cpu.max")
    _CGROUP_MEM_PATHS = ("/sys/fs/cgroup/morph/memory.max", "/sys/fs/cgroup/memory.max")

    def __init__(self, interface: str = "lo") -> None:
        super().__init__()
        self.interface = interface
        self._proxy: ProxyAdapter | None = None
        self._used_tc: bool = False
        self._used_cgroup_quota_path: str | None = None
        self._used_cgroup_mem_path: str | None = None

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": True,
            "memory": True,
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

        has_tc = shutil.which("tc") is not None or os.path.exists("/sbin/tc") or os.path.exists("/usr/sbin/tc")
        tc_bin = shutil.which("tc") or ("/sbin/tc" if os.path.exists("/sbin/tc") else "tc")
        is_root = os.name != "nt" and os.geteuid() == 0

        if has_tc:
            cmd = [tc_bin, "qdisc", "add", "dev", self.interface, "root", "netem"]
            if not is_root:
                cmd = ["sudo", "-n", *cmd]
            if latency_ms > 0:
                cmd.extend(["delay", f"{latency_ms}ms"])
            if packet_loss_percent > 0:
                cmd.extend(["loss", f"{packet_loss_percent}%"])
            try:
                subprocess.run(cmd, check=True, capture_output=True)
                self._used_tc = True
                return
            except (subprocess.SubprocessError, OSError):
                pass

        # Fallback to user-space TCP proxy
        self._proxy = ProxyAdapter()
        self._proxy.apply_network(
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_mbps=bandwidth_mbps,
        )
        self._env_overrides.update(self._proxy.get_env_overrides())

    def _write_cgroup(self, path: str, value: str) -> bool:
        """Write a value to a cgroup control file, falling back to passwordless sudo if unprivileged."""
        try:
            with open(path, "w") as f:
                f.write(value)
            return True
        except (PermissionError, OSError):
            if os.name != "nt":
                try:
                    res = subprocess.run(
                        ["sudo", "-n", "sh", "-c", f"echo '{value}' > '{path}'"],
                        check=False,
                        capture_output=True,
                    )
                    return res.returncode == 0
                except OSError:
                    pass
        return False

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._env_overrides["MORPH_MAX_CORES"] = str(max_cores)

        if quota_percent is not None and quota_percent > 0:
            applied = False
            period_us = 100_000
            quota_us = int(period_us * quota_percent / 100)
            for path in self._CGROUP_CPU_PATHS:
                if self._write_cgroup(path, f"{quota_us} {period_us}"):
                    self._used_cgroup_quota_path = path
                    applied = True
                    break
            if not applied:
                self._env_overrides["MORPH_CPU_QUOTA_PERCENT"] = str(quota_percent)

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            applied = False
            limit_bytes = limit_mb * 1024 * 1024
            for path in self._CGROUP_MEM_PATHS:
                if self._write_cgroup(path, str(limit_bytes)):
                    self._used_cgroup_mem_path = path
                    applied = True
                    break
            if not applied:
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

        if self._used_cgroup_quota_path:
            self._write_cgroup(self._used_cgroup_quota_path, "max 100000")
            self._used_cgroup_quota_path = None

        if self._used_cgroup_mem_path:
            self._write_cgroup(self._used_cgroup_mem_path, "max")
            self._used_cgroup_mem_path = None


        if self._used_tc:
            tc_bin = shutil.which("tc") or ("/sbin/tc" if os.path.exists("/sbin/tc") else "tc")
            cmd = [tc_bin, "qdisc", "del", "dev", self.interface, "root"]
            if os.name != "nt" and os.geteuid() != 0:
                cmd = ["sudo", "-n", *cmd]
            try:
                subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                )
            except OSError:
                pass
            self._used_tc = False

        self._env_overrides.clear()

