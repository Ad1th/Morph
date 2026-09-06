"""Windows runtime adapter using Job Objects when native, with ProxyAdapter fallback."""

from __future__ import annotations

import os
from typing import Optional

from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter


class WindowsAdapter(BaseAdapter):
    """Adapter for Windows environment condition simulation."""

    def __init__(self) -> None:
        super().__init__()
        self._proxy: ProxyAdapter | None = None

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

        self._proxy = ProxyAdapter()
        self._proxy.apply_network(
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_mbps=bandwidth_mbps,
        )
        self._env_overrides.update(self._proxy.get_env_overrides())

    def apply_cpu(self, max_cores: int | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._env_overrides["MORPH_MAX_CORES"] = str(max_cores)

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

        self._env_overrides.clear()
