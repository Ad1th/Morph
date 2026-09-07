"""Windows runtime adapter: ProxyAdapter for the network; CPU/RAM/locale honestly reported.

There is no Job Object wiring (it needs pywin32, a dependency this project does
not have), so CPU and memory travel as runtime hints and are reported APPROXIMATED. The MSVC
CRT ignores LC_ALL/TZ, so locale and timezone are APPROXIMATED: a target that
reads the variables itself (apps/locale_parse) honours them, `setlocale(LC_ALL,
"")` does not.
"""

from __future__ import annotations

from morph.runtime.adapters.base import (
    RUNTIME_HINT_DETAIL,
    BaseAdapter,
    Fidelity,
    ProxyAdapter,
    _vars,
    cpu_hint_env,
    memory_hint_env,
    plan_proxy_path,
    quota_hint_env,
)
from morph.schema.profile import FieldStatus


class WindowsAdapter(BaseAdapter):
    """Adapter for Windows environment condition simulation."""

    def __init__(self, seed: int | None = None) -> None:
        super().__init__()
        self.seed = seed
        self._proxy: ProxyAdapter | None = None

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": False,
            "memory": False,
            "locale": True,
        }

    def plan(self, profile) -> dict[str, Fidelity]:
        return plan_proxy_path(profile, native_cpu_mem=False, windows=True)

    def apply_network(
        self,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_mbps: float | None = None,
    ) -> None:
        if latency_ms <= 0.0 and packet_loss_percent <= 0.0:
            return

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
            self._env_overrides.update(cpu_hint_env(max_cores))
            self._note("cpu.cores", FieldStatus.APPROXIMATED, "runtime hints",
                       RUNTIME_HINT_DETAIL.format(vars=_vars(cpu_hint_env(max_cores))))
        if quota_percent is not None and quota_percent > 0:
            self._env_overrides.update(quota_hint_env(quota_percent))
            self._note("cpu.quota_percent", FieldStatus.APPROXIMATED, "runtime hints",
                       RUNTIME_HINT_DETAIL.format(vars="MORPH_CPU_QUOTA_PERCENT")
                       + "; Job Object rate control needs pywin32")

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            self._env_overrides.update(memory_hint_env(limit_mb))
            self._note("memory.total_mb", FieldStatus.APPROXIMATED, "runtime hints",
                       RUNTIME_HINT_DETAIL.format(vars=_vars(memory_hint_env(limit_mb)))
                       + "; Job Object memory limit needs pywin32")

    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        self._apply_locale_env(
            locale_str, timezone,
            locale_status=FieldStatus.APPROXIMATED,
            locale_detail="LC_ALL/LANG exported, but the MSVC CRT ignores them; "
                          "only targets that read the variables themselves honour it",
        )
        if timezone:
            self._note("locale.timezone", FieldStatus.APPROXIMATED, "env",
                       "TZ exported, but the MSVC CRT does not read IANA names")

    def cleanup(self) -> None:
        if self._proxy is not None:
            self._proxy.cleanup()
            self._proxy = None

        self._env_overrides.clear()
        self._fidelity.clear()
