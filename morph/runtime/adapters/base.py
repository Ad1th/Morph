"""BaseAdapter interface and cross-platform ProxyAdapter."""

from __future__ import annotations

import asyncio
import threading
from abc import ABC, abstractmethod
from typing import Any

from morph.runtime.adapters.proxy import ProxyServer


class BaseAdapter(ABC):
    """Abstract interface for operating system and network environment adapters."""

    def __init__(self) -> None:
        self._env_overrides: dict[str, str] = {}

    @abstractmethod
    def apply_network(
        self,
        latency_ms: float = 0.0,
        packet_loss_percent: float = 0.0,
        bandwidth_mbps: float | None = None,
    ) -> None:
        """Apply network conditions (latency, packet loss, bandwidth limit)."""
        pass

    @abstractmethod
    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        """Apply CPU core count and/or usage quota restrictions."""
        pass

    @abstractmethod
    def apply_memory(self, limit_mb: int | None = None) -> None:
        """Apply memory restrictions."""
        pass

    @abstractmethod
    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        """Apply locale and timezone settings."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Clean up all applied conditions and restore normal host state."""
        pass

    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Return capabilities dict: {'network': bool, 'cpu': bool, 'memory': bool, 'locale': bool}."""
        pass

    def get_env_overrides(self) -> dict[str, str]:
        """Return dictionary of environment variables to inject into target process."""
        return dict(self._env_overrides)

    def __enter__(self) -> BaseAdapter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()


class ProxyAdapter(BaseAdapter):
    """Cross-platform fallback adapter using user-space TCP proxy and environment variables.

    Zero root privileges needed. Ideal for test environments and CI.
    """

    def __init__(
        self,
        upstream_host: str = "127.0.0.1",
        upstream_port: int = 80,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
    ) -> None:
        super().__init__()
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.proxy: ProxyServer | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._is_running = False

    def capabilities(self) -> dict[str, bool]:
        return {
            "network": True,
            "cpu": False,
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

        self.proxy = ProxyServer(
            upstream_host=self.upstream_host,
            upstream_port=self.upstream_port,
            listen_host=self.listen_host,
            listen_port=self.listen_port,
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
        )

        ready_event = threading.Event()

        def _run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_until_complete(self.proxy.start())
            self.listen_port = self.proxy.port
            self._env_overrides["MORPH_PROXY_PORT"] = str(self.listen_port)
            self._env_overrides["MORPH_PROXY_HOST"] = self.listen_host
            self._env_overrides["MORPH_UPSTREAM_PORT"] = str(self.upstream_port)
            self._env_overrides["MORPH_LATENCY_MS"] = str(latency_ms)
            self._env_overrides["MORPH_PACKET_LOSS"] = str(packet_loss_percent)
            self._is_running = True
            ready_event.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_run_loop, daemon=True)
        self._thread.start()
        ready_event.wait(timeout=5.0)

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        pass

    def apply_memory(self, limit_mb: int | None = None) -> None:
        pass

    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        if locale_str:
            self._env_overrides["LC_ALL"] = locale_str
            self._env_overrides["LANG"] = locale_str
        if timezone:
            self._env_overrides["TZ"] = timezone

    def cleanup(self) -> None:
        if self._loop and self._is_running:
            if self.proxy:
                fut = asyncio.run_coroutine_threadsafe(self.proxy.stop(), self._loop)
                try:
                    fut.result(timeout=2.0)
                except Exception:
                    pass
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._is_running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._env_overrides.clear()
        self.proxy = None
        self._loop = None
        self._thread = None
