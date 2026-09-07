"""macOS runtime adapter: dummynet via pf (root) for the network, ProxyAdapter fallback.

A dnctl pipe on its own shapes nothing -- packets only enter it through a pf
rule. When root, the adapter installs a pipe AND a `morph` pf anchor that
routes loopback TCP through it, and removes both on cleanup. Both steps are
recorded in the state file so a crashed run can be undone by `morph doctor`.
CPU/RAM have no native control on macOS: reported UNAVAILABLE, never faked.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from morph.runtime import state
from morph.runtime.adapters.base import (
    ENV_HINT_DETAIL,
    BaseAdapter,
    Fidelity,
    ProxyAdapter,
    no_native_side_effects,
    plan_proxy_path,
)
from morph.schema.profile import FieldStatus


def _is_macos() -> bool:
    return platform.system().lower() == "darwin"


def _is_root() -> bool:
    return os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0


class MacOSAdapter(BaseAdapter):
    """Adapter for macOS environment condition simulation."""

    _ANCHOR = "morph"

    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        self.seed = seed
        self._proxy: ProxyAdapter | None = None
        self._pipe_num: int = 1
        self._entry: state.StateEntry | None = None

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": False,
            "memory": False,
            "locale": True,
        }

    def _can_native(self) -> bool:
        return bool(
            _is_macos() and _is_root() and shutil.which("dnctl") and shutil.which("pfctl")
            and not no_native_side_effects()
        )

    def plan(self, profile) -> dict[str, Fidelity]:
        out = plan_proxy_path(profile, native_cpu_mem=False, windows=False)
        if self._can_native():
            mech = f"dummynet pipe via pf anchor {self._ANCHOR}"
            for path in list(out):
                if path.startswith("network."):
                    out[path] = Fidelity(FieldStatus.REPRODUCED, mech, "loopback TCP shaped")
        return out

    def _undo_argv(self) -> list[str]:
        # One shell line so the state file can replay it verbatim.
        return ["sh", "-c", f"pfctl -a {self._ANCHOR} -F all >/dev/null 2>&1; dnctl -q flush >/dev/null 2>&1"]

    def apply_network(
        self,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_mbps: float | None = None,
    ) -> None:
        if latency_ms <= 0.0 and packet_loss_percent <= 0.0:
            return

        if self._can_native():
            entry = state.record(state.StateEntry(
                kind="dnctl",
                detail=f"dummynet pipe {self._pipe_num} + pf anchor {self._ANCHOR}: "
                       f"{latency_ms}ms / {packet_loss_percent}%",
                undo=self._undo_argv(),
            ))
            try:
                cmd = ["dnctl", "pipe", str(self._pipe_num), "config"]
                if latency_ms > 0:
                    # dummynet delay is per direction; the profile value is an RTT.
                    cmd.extend(["delay", f"{latency_ms / 2:g}ms"])
                if packet_loss_percent > 0:
                    cmd.extend(["plr", str(packet_loss_percent / 100.0)])
                if bandwidth_mbps:
                    cmd.extend(["bw", f"{bandwidth_mbps}Mbit/s"])
                subprocess.run(cmd, check=True, capture_output=True, timeout=15)
                rules = (
                    f"dummynet in proto tcp from any to 127.0.0.1 pipe {self._pipe_num}\n"
                    f"dummynet out proto tcp from any to 127.0.0.1 pipe {self._pipe_num}\n"
                )
                subprocess.run(["pfctl", "-a", self._ANCHOR, "-f", "-"], input=rules.encode(),
                               check=True, capture_output=True, timeout=15)
                subprocess.run(["pfctl", "-E"], check=False, capture_output=True, timeout=15)
                self._entry = entry
                mech = f"dummynet pipe via pf anchor {self._ANCHOR}"
                self._note("network.latency_ms", FieldStatus.REPRODUCED, mech, "loopback TCP shaped")
                self._note("network.packet_loss_percent", FieldStatus.REPRODUCED, mech,
                           "loopback TCP shaped")
                if bandwidth_mbps:
                    self._note("network.bandwidth_mbps", FieldStatus.REPRODUCED, mech, "pipe bw")
                return
            except (subprocess.SubprocessError, OSError):
                try:
                    subprocess.run(entry.undo, check=False, capture_output=True, timeout=15)
                except (OSError, subprocess.SubprocessError):
                    pass
                state.forget(entry.id)

        # Unprivileged fallback: user-space TCP proxy
        self._proxy = ProxyAdapter(seed=self.seed)
        self._proxy.apply_network(
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_mbps=bandwidth_mbps,
        )
        self._env_overrides.update(self._proxy.get_env_overrides())
        self._fidelity.update(self._proxy.fidelity())

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._env_overrides["MORPH_MAX_CORES"] = str(max_cores)
            self._note("cpu.cores", FieldStatus.UNAVAILABLE, "env hint",
                       ENV_HINT_DETAIL.format(var="MORPH_MAX_CORES") + "; macOS has no core pinning")
        if quota_percent is not None and quota_percent > 0:
            self._env_overrides["MORPH_CPU_QUOTA_PERCENT"] = str(quota_percent)
            self._note("cpu.quota_percent", FieldStatus.UNAVAILABLE, "env hint",
                       ENV_HINT_DETAIL.format(var="MORPH_CPU_QUOTA_PERCENT")
                       + "; macOS has no cgroups (needs a Linux worker)")

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            self._env_overrides["MORPH_MEMORY_LIMIT_MB"] = str(limit_mb)
            self._note("memory.total_mb", FieldStatus.UNAVAILABLE, "env hint",
                       ENV_HINT_DETAIL.format(var="MORPH_MEMORY_LIMIT_MB")
                       + "; macOS has no per-process memory cap (needs a Linux worker)")

    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        self._apply_locale_env(locale_str, timezone)

    def cleanup(self) -> None:
        if self._proxy is not None:
            self._proxy.cleanup()
            self._proxy = None

        if self._entry is not None:
            try:
                subprocess.run(self._entry.undo, check=False, capture_output=True, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass
            state.forget(self._entry.id)
            self._entry = None

        self._env_overrides.clear()
        self._fidelity.clear()
