"""Linux runtime adapter: tc/netem for the network, cgroup v2 for CPU/RAM, ProxyAdapter fallback.

Every native side effect is recorded in ``~/.morph/state/shaping.json`` before
it is applied and forgotten after it is reverted, so a run that is SIGKILLed
mid-trial leaves a record `morph doctor` (``morph.runtime.state.cleanup_stale``)
can act on instead of a stale qdisc that silently double-shapes the next run.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess

from morph.runtime import state
from morph.runtime.adapters.base import (
    RUNTIME_HINT_DETAIL,
    BaseAdapter,
    Fidelity,
    ProxyAdapter,
    _vars,
    cpu_hint_env,
    memory_hint_env,
    no_native_side_effects,
    plan_proxy_path,
    quota_hint_env,
)
from morph.schema.profile import FieldStatus


def _is_linux() -> bool:
    return platform.system().lower() == "linux"


def _is_root() -> bool:
    return os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0


def _tc_bin() -> str | None:
    found = shutil.which("tc")
    if found:
        return found
    for candidate in ("/sbin/tc", "/usr/sbin/tc"):
        if os.path.exists(candidate):
            return candidate
    return None


class LinuxAdapter(BaseAdapter):
    """Adapter for Linux environment condition simulation."""

    def __init__(self, interface: str = "lo", seed: int | None = None) -> None:
        super().__init__()
        self.interface = interface
        self.seed = seed
        self._proxy: ProxyAdapter | None = None
        self._tc_entry: state.StateEntry | None = None
        self._cgroup_entries: list[state.StateEntry] = []
        self._cgroup_dir: str | None = None

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": True,
            "memory": True,
            "locale": True,
        }

    # ----------------------------------------------------------------- plan

    def _can_tc(self) -> bool:
        """Will `tc` work here? Root, or passwordless sudo (probed read-only, once)."""
        if not _is_linux() or not _tc_bin() or no_native_side_effects():
            return False
        if _is_root():
            return True
        cached = getattr(self, "_sudo_tc_ok", None)
        if cached is None:
            try:
                res = subprocess.run(
                    ["sudo", "-n", _tc_bin(), "qdisc", "show", "dev", self.interface],
                    capture_output=True,
                    timeout=5,
                )
                cached = res.returncode == 0
            except (OSError, subprocess.SubprocessError):
                cached = False
            self._sudo_tc_ok = cached
        return cached

    def plan(self, profile) -> dict[str, Fidelity]:
        out = plan_proxy_path(profile, native_cpu_mem=True, windows=False)
        if self._can_tc():
            mech = f"tc netem on {self.interface}"
            for path in list(out):
                if path.startswith("network."):
                    out[path] = Fidelity(FieldStatus.REPRODUCED, mech, "netem on the interface")
        base = self._cgroup_base()
        if base:
            out["memory.total_mb"] = Fidelity(FieldStatus.REPRODUCED, "cgroup v2 memory.max", base)
            out["cpu.quota_percent"] = Fidelity(FieldStatus.REPRODUCED, "cgroup v2 cpu.max", base)
        else:
            hint = "; set MORPH_CGROUP_PATH to a writable cgroup to enforce it"
            out["memory.total_mb"] = Fidelity(
                FieldStatus.APPROXIMATED,
                "runtime hints",
                RUNTIME_HINT_DETAIL.format(vars=_vars(memory_hint_env(1))) + hint,
            )
            out["cpu.quota_percent"] = Fidelity(
                FieldStatus.APPROXIMATED,
                "runtime hints",
                RUNTIME_HINT_DETAIL.format(vars="MORPH_CPU_QUOTA_PERCENT") + hint,
            )
        out["cpu.cores"] = Fidelity(
            FieldStatus.APPROXIMATED, "runtime hints", RUNTIME_HINT_DETAIL.format(vars=_vars(cpu_hint_env(1)))
        )
        return out

    # -------------------------------------------------------------- network

    def _tc(self, *args: str) -> list[str]:
        tc = _tc_bin() or "tc"
        cmd = [tc, *args]
        return cmd if _is_root() else ["sudo", "-n", *cmd]

    def apply_network(
        self,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_mbps: float | None = None,
    ) -> None:
        if latency_ms <= 0.0 and packet_loss_percent <= 0.0:
            return

        if _is_linux() and _tc_bin() and not no_native_side_effects():
            # `replace` is idempotent: it installs the qdisc whether or not a
            # root qdisc (ours from a crashed run, or someone else's) exists,
            # where `add` fails with "File exists" and used to fall through to
            # the proxy on top of the stale rule.
            args = ["qdisc", "replace", "dev", self.interface, "root", "netem"]
            if latency_ms > 0:
                args.extend(["delay", f"{latency_ms}ms"])
            if packet_loss_percent > 0:
                args.extend(["loss", f"{packet_loss_percent}%"])
            if bandwidth_mbps:
                args.extend(["rate", f"{float(bandwidth_mbps)}mbit"])
            entry = state.record(
                state.StateEntry(
                    kind="tc",
                    detail=f"netem on {self.interface}: {latency_ms}ms / {packet_loss_percent}%",
                    undo=self._tc("qdisc", "del", "dev", self.interface, "root"),
                )
            )
            try:
                subprocess.run(self._tc(*args), check=True, capture_output=True, timeout=15)
                self._tc_entry = entry
                mech = f"tc netem on {self.interface}"
                self._note(
                    "network.latency_ms", FieldStatus.REPRODUCED, mech, "netem delay applied to the interface"
                )
                self._note(
                    "network.packet_loss_percent",
                    FieldStatus.REPRODUCED,
                    mech,
                    "netem loss applied to the interface",
                )
                if bandwidth_mbps:
                    self._note("network.bandwidth_mbps", FieldStatus.REPRODUCED, mech, "netem rate")
                return
            except (subprocess.SubprocessError, OSError):
                state.forget(entry.id)

        # Fallback to user-space TCP proxy
        self._proxy = ProxyAdapter(seed=self.seed)
        self._proxy.apply_network(
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_mbps=bandwidth_mbps,
        )
        self._env_overrides.update(self._proxy.get_env_overrides())
        self._fidelity.update(self._proxy.fidelity())

    # ------------------------------------------------------------ cgroups

    def _cgroup_base(self) -> str | None:
        """Explicit opt-in only: MORPH_CGROUP_PATH names a cgroup-v2 directory
        Morph may write to (created and delegated by the operator, e.g.
        `sudo mkdir /sys/fs/cgroup/morph && sudo chown $USER ...`). Without it
        nothing is throttled, and that is reported as APPROXIMATED (runtime hints) rather than
        silently writing to a shared or root cgroup."""
        path = (os.environ.get("MORPH_CGROUP_PATH") or "").strip()
        if not path or not _is_linux() or no_native_side_effects():
            return None
        return path if os.path.isdir(path) else None

    def _write_cgroup(self, path: str, value: str, restore_value: str, detail: str) -> bool:
        entry = state.record(
            state.StateEntry(
                kind="cgroup",
                detail=detail,
                restore={"path": path, "value": restore_value},
            )
        )
        try:
            with open(path, "w") as f:
                f.write(value)
        except OSError:
            state.forget(entry.id)
            return False
        self._cgroup_entries.append(entry)
        return True

    def cgroup_path(self) -> str | None:
        return self._cgroup_dir

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._env_overrides.update(cpu_hint_env(max_cores))
            self._note(
                "cpu.cores",
                FieldStatus.APPROXIMATED,
                "runtime hints",
                RUNTIME_HINT_DETAIL.format(vars=_vars(cpu_hint_env(max_cores))),
            )

        if quota_percent is not None and quota_percent > 0:
            base = self._cgroup_base()
            applied = False
            if base:
                period_us = 100_000
                quota_us = int(period_us * quota_percent / 100)
                applied = self._write_cgroup(
                    os.path.join(base, "cpu.max"),
                    f"{quota_us} {period_us}",
                    "max 100000",
                    f"cpu.max={quota_percent}% in {base}",
                )
            if applied:
                self._cgroup_dir = base
                self._note(
                    "cpu.quota_percent", FieldStatus.REPRODUCED, "cgroup v2 cpu.max", f"child joins {base}"
                )
            else:
                self._env_overrides.update(quota_hint_env(quota_percent))
                self._note(
                    "cpu.quota_percent",
                    FieldStatus.APPROXIMATED,
                    "runtime hints",
                    RUNTIME_HINT_DETAIL.format(vars="MORPH_CPU_QUOTA_PERCENT")
                    + "; set MORPH_CGROUP_PATH to a writable cgroup to enforce it",
                )

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            base = self._cgroup_base()
            applied = False
            if base:
                applied = self._write_cgroup(
                    os.path.join(base, "memory.max"),
                    str(limit_mb * 1024 * 1024),
                    "max",
                    f"memory.max={limit_mb}MB in {base}",
                )
            if applied:
                self._cgroup_dir = base
                self._note(
                    "memory.total_mb", FieldStatus.REPRODUCED, "cgroup v2 memory.max", f"child joins {base}"
                )
            else:
                self._env_overrides.update(memory_hint_env(limit_mb))
                self._note(
                    "memory.total_mb",
                    FieldStatus.APPROXIMATED,
                    "runtime hints",
                    RUNTIME_HINT_DETAIL.format(vars=_vars(memory_hint_env(limit_mb)))
                    + "; set MORPH_CGROUP_PATH to a writable cgroup to enforce it",
                )

    # -------------------------------------------------------------- locale

    def apply_locale(self, locale_str: str | None = None, timezone: str | None = None) -> None:
        self._apply_locale_env(locale_str, timezone)

    # ------------------------------------------------------------- cleanup

    def cleanup(self) -> None:
        if self._proxy is not None:
            self._proxy.cleanup()
            self._proxy = None

        for entry in self._cgroup_entries:
            try:
                with open(entry.restore["path"], "w") as f:
                    f.write(entry.restore["value"])
            except (OSError, TypeError):
                pass
            state.forget(entry.id)
        self._cgroup_entries = []
        self._cgroup_dir = None

        if self._tc_entry is not None:
            try:
                subprocess.run(self._tc_entry.undo, check=False, capture_output=True, timeout=15)
            except (OSError, subprocess.SubprocessError):
                pass
            state.forget(self._tc_entry.id)
            self._tc_entry = None

        self._env_overrides.clear()
        self._fidelity.clear()
