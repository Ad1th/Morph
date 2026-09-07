"""BaseAdapter interface and cross-platform ProxyAdapter."""

from __future__ import annotations

import asyncio
import os
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from morph.schema.profile import FieldStatus

if TYPE_CHECKING:  # imported lazily at runtime so `python -m ...adapters.proxy` stays clean
    from morph.runtime.adapters.proxy import ProxyServer

# Detail strings shared by every adapter that falls back to the proxy path.
PROXY_DETAIL = "user-space proxy: only traffic routed through MORPH_PROXY_* is shaped"
ENV_HINT_DETAIL = "env hint only ({var}); nothing on this host enforces it"


@dataclass
class Fidelity:
    """How one profile field was (or was not) applied by an adapter."""

    status: FieldStatus
    mechanism: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, str]:
        return {"status": str(self.status), "mechanism": self.mechanism, "detail": self.detail}


class BaseAdapter(ABC):
    """Abstract interface for operating system and network environment adapters."""

    def __init__(self) -> None:
        self._env_overrides: dict[str, str] = {}
        self._fidelity: dict[str, Fidelity] = {}

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
        """Clean up all applied conditions and restore normal host state.

        Must be idempotent: the controller calls it from a `finally`, and
        `morph doctor` may call it again after a crash.
        """
        pass

    @abstractmethod
    def capabilities(self) -> dict[str, bool]:
        """Return capabilities dict: {'network': bool, 'cpu': bool, 'memory': bool, 'locale': bool}.

        Class-level claims ("this adapter has SOME mechanism"). What actually
        happened for a given run is `fidelity()`.
        """
        pass

    # ------------------------------------------------------------- fidelity

    def _note(self, field_path: str, status: FieldStatus, mechanism: str = "", detail: str = "") -> None:
        self._fidelity[field_path] = Fidelity(status, mechanism, detail)

    def fidelity(self) -> dict[str, Fidelity]:
        """Per-field report of what the last `apply_*` calls really did.

        Keys are profile field paths ("network.latency_ms"). Populated by the
        adapter that applied each condition, so a proxy-shaped network is
        APPROXIMATED, an env-var CPU knob nothing reads is UNAVAILABLE, and a
        tc netem rule is REPRODUCED. Empty for fields not applied.
        """
        return dict(self._fidelity)

    def report(self) -> dict[str, dict[str, str]]:
        """JSON-ready form of `fidelity()` for RunResult.fidelity."""
        return {k: v.as_dict() for k, v in self._fidelity.items()}

    def plan(self, profile: Any) -> dict[str, Fidelity]:
        """Predict `fidelity()` for `profile` WITHOUT applying anything.

        The default derives from `capabilities()` and is deliberately generic
        (a capability means "some mechanism exists"). Every adapter shipped
        with Morph overrides it with what it will actually do on this host.
        """
        caps = self.capabilities()
        out: dict[str, Fidelity] = {}
        net_status = FieldStatus.REPRODUCED if caps.get("network") else FieldStatus.UNAVAILABLE
        if getattr(profile, "network", None):
            out["network.latency_ms"] = Fidelity(net_status, "capability", "class-level claim")
            out["network.packet_loss_percent"] = Fidelity(net_status, "capability", "class-level claim")
            if profile.network.bandwidth_mbps:
                out["network.bandwidth_mbps"] = Fidelity(
                    FieldStatus.APPROXIMATED if caps.get("network") else FieldStatus.UNAVAILABLE,
                    "capability", "class-level claim",
                )
        cpu_status = FieldStatus.APPROXIMATED if caps.get("cpu") else FieldStatus.UNAVAILABLE
        out["cpu.cores"] = Fidelity(cpu_status, "capability", "class-level claim")
        if getattr(profile, "cpu", None) and profile.cpu.quota_percent:
            out["cpu.quota_percent"] = Fidelity(cpu_status, "capability", "class-level claim")
        out["memory.total_mb"] = Fidelity(
            FieldStatus.APPROXIMATED if caps.get("memory") else FieldStatus.UNAVAILABLE,
            "capability", "class-level claim",
        )
        loc_status = FieldStatus.REPRODUCED if caps.get("locale") else FieldStatus.UNAVAILABLE
        out["locale.locale"] = Fidelity(loc_status, "capability", "class-level claim")
        out["locale.timezone"] = Fidelity(loc_status, "capability", "class-level claim")
        return out

    def cgroup_path(self) -> str | None:
        """cgroup directory the child should join, if this adapter set one up."""
        return None

    # -------------------------------------------------------- env / context

    def get_env_overrides(self) -> dict[str, str]:
        """Return dictionary of environment variables to inject into target process."""
        return dict(self._env_overrides)

    def _apply_locale_env(self, locale_str: str | None, timezone: str | None,
                          locale_status: FieldStatus = FieldStatus.REPRODUCED,
                          locale_detail: str = "LC_ALL/LANG exported to the child") -> None:
        """Shared LC_ALL/LANG/TZ export; POSIX-normalises the locale name."""
        if locale_str:
            posix = to_posix_locale(locale_str)
            self._env_overrides["LC_ALL"] = posix
            self._env_overrides["LANG"] = posix
            self._note("locale.locale", locale_status, "env", locale_detail)
        if timezone:
            self._env_overrides["TZ"] = timezone
            if is_iana_timezone(timezone):
                self._note("locale.timezone", FieldStatus.REPRODUCED, "env", "TZ exported (IANA zone)")
            else:
                self._note(
                    "locale.timezone", FieldStatus.APPROXIMATED, "env",
                    f"TZ={timezone!r} is not an IANA zone name; libc will treat it as UTC",
                )

    def __enter__(self) -> BaseAdapter:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.cleanup()


# --------------------------------------------------------------------------- #
# locale / timezone helpers shared by every adapter
# --------------------------------------------------------------------------- #

def to_posix_locale(value: str) -> str:
    """``en-IN`` -> ``en_IN.UTF-8``; values already POSIX (``de_DE.UTF-8``, ``C``) pass through."""
    v = (value or "").strip()
    if not v:
        return v
    if v in ("C", "POSIX") or "_" in v or "." in v or "@" in v:
        return v
    parts = v.split("-")
    if len(parts) >= 2 and parts[0].isalpha():
        lang, region = parts[0].lower(), parts[1].upper()
        return f"{lang}_{region}.UTF-8"
    return v


def is_iana_timezone(name: str) -> bool:
    if not name or name == "UTC":
        return True
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(name)
        return True
    except Exception:
        return False


class ProxyAdapter(BaseAdapter):
    """Cross-platform fallback adapter using user-space TCP proxy and environment variables.

    Zero root privileges needed. Ideal for test environments and CI. Honest
    about its reach: only traffic the target routes through the proxy (or a
    target that reads MORPH_NET_* and fronts its own server, like apps/*) is
    shaped, so the network fields are reported APPROXIMATED, never REPRODUCED.
    """

    def __init__(
        self,
        upstream_host: str = "127.0.0.1",
        upstream_port: int = 80,
        listen_host: str = "127.0.0.1",
        listen_port: int = 0,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.upstream_host = upstream_host
        self.upstream_port = upstream_port
        self.listen_host = listen_host
        self.listen_port = listen_port
        self.seed = seed
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

        from morph.runtime.adapters.proxy import ProxyServer

        # Generic condition hand-off for targets that host their own localhost
        # server (they cannot be routed through an external proxy). Such an app
        # reads these and puts Morph's own TCP proxy in front of its server
        # in-process -- same delay/stall code, applied where the app can see it.
        # Only ever set on the unprivileged proxy path; the native tc/dnctl
        # adapters shape the real interface and return before reaching here.
        self._env_overrides["MORPH_NET_LATENCY_MS"] = str(latency_ms)
        self._env_overrides["MORPH_NET_PACKET_LOSS_PCT"] = str(packet_loss_percent)
        if bandwidth_mbps:
            self._env_overrides["MORPH_NET_BANDWIDTH_KBPS"] = str(float(bandwidth_mbps) * 1000.0)
        if self.seed is not None:
            self._env_overrides["MORPH_SEED"] = str(self.seed)

        self.proxy = ProxyServer(
            upstream_host=self.upstream_host,
            upstream_port=self.upstream_port,
            listen_host=self.listen_host,
            listen_port=self.listen_port,
            latency_ms=latency_ms,
            packet_loss_percent=packet_loss_percent,
            bandwidth_kbps=(float(bandwidth_mbps) * 1000.0) if bandwidth_mbps else None,
            seed=self.seed,
        )

        # Start synchronously: run the loop on a thread, then block on the
        # start() coroutine so a bind failure raises HERE (not as a traceback
        # on a dead thread with the env half-populated).
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        try:
            asyncio.run_coroutine_threadsafe(self.proxy.start(), self._loop).result(timeout=5.0)
        except Exception:
            self._stop_loop()
            self.proxy = None
            self._note("network.latency_ms", FieldStatus.UNAVAILABLE, "none",
                       "proxy failed to start; MORPH_NET_* hint only")
            self._note("network.packet_loss_percent", FieldStatus.UNAVAILABLE, "none",
                       "proxy failed to start; MORPH_NET_* hint only")
            raise
        self._is_running = True
        self.listen_port = self.proxy.port
        self._env_overrides["MORPH_PROXY_PORT"] = str(self.listen_port)
        self._env_overrides["MORPH_PROXY_HOST"] = self.listen_host
        self._env_overrides["MORPH_UPSTREAM_PORT"] = str(self.upstream_port)

        for field_name in ("network.latency_ms", "network.packet_loss_percent"):
            self._note(field_name, FieldStatus.APPROXIMATED, "user-space proxy", PROXY_DETAIL)
        if bandwidth_mbps:
            self._note("network.bandwidth_mbps", FieldStatus.APPROXIMATED, "user-space proxy",
                       PROXY_DETAIL + " (token bucket)")

    def plan(self, profile: Any) -> dict[str, Fidelity]:
        return plan_proxy_path(profile, native_cpu_mem=False, windows=False)

    def apply_cpu(self, max_cores: int | None = None, quota_percent: float | None = None) -> None:
        if max_cores is not None and max_cores > 0:
            self._note("cpu.cores", FieldStatus.UNAVAILABLE, "none", "proxy adapter cannot pin cores")
        if quota_percent is not None and quota_percent > 0:
            self._note("cpu.quota_percent", FieldStatus.UNAVAILABLE, "none",
                       "proxy adapter cannot throttle CPU")

    def apply_memory(self, limit_mb: int | None = None) -> None:
        if limit_mb is not None and limit_mb > 0:
            self._note("memory.total_mb", FieldStatus.UNAVAILABLE, "none",
                       "proxy adapter cannot limit memory")

    def apply_locale(
        self, locale_str: str | None = None, timezone: str | None = None
    ) -> None:
        self._apply_locale_env(locale_str, timezone)

    def _stop_loop(self) -> None:
        loop, thread = self._loop, self._thread
        if loop is not None:
            try:
                loop.call_soon_threadsafe(loop.stop)
            except RuntimeError:
                pass
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        if loop is not None and not loop.is_running():
            try:
                loop.close()  # every trial used to leak one event loop
            except Exception:
                pass
        self._loop = None
        self._thread = None

    def cleanup(self) -> None:
        if self._loop is not None and self._is_running and self.proxy is not None:
            fut = asyncio.run_coroutine_threadsafe(self.proxy.stop(), self._loop)
            try:
                fut.result(timeout=2.0)
            except Exception:
                pass
        self._is_running = False
        self._stop_loop()
        self._env_overrides.clear()
        self._fidelity.clear()
        self.proxy = None


def _wants_network(profile: Any) -> bool:
    net = getattr(profile, "network", None)
    if not net:
        return False
    try:
        lat = float(net.latency_ms.value or 0.0)
        loss = float(net.packet_loss_percent.value or 0.0)
    except (TypeError, ValueError):
        return False
    offline = bool(net.available and net.available.value is False)
    return lat > 0.0 or loss > 0.0 or offline


def plan_proxy_path(profile: Any, *, native_cpu_mem: bool, windows: bool) -> dict[str, Fidelity]:
    """Prediction shared by every adapter whose network path is the user-space proxy.

    `native_cpu_mem` is reserved for adapters that CAN enforce CPU/RAM (Linux
    with a cgroup); the callers that pass True fill those entries themselves.
    """
    out: dict[str, Fidelity] = {}
    if _wants_network(profile):
        for path in ("network.latency_ms", "network.packet_loss_percent"):
            out[path] = Fidelity(FieldStatus.APPROXIMATED, "user-space proxy", PROXY_DETAIL)
        if profile.network.bandwidth_mbps and profile.network.bandwidth_mbps.value:
            out["network.bandwidth_mbps"] = Fidelity(
                FieldStatus.APPROXIMATED, "user-space proxy", PROXY_DETAIL + " (token bucket)"
            )
    elif getattr(profile, "network", None):
        # Nothing requested: there is nothing to reproduce, and saying so is accurate.
        for path in ("network.latency_ms", "network.packet_loss_percent"):
            out[path] = Fidelity(FieldStatus.REPRODUCED, "none needed", "no shaping requested")
    if not native_cpu_mem:
        out["cpu.cores"] = Fidelity(FieldStatus.UNAVAILABLE, "env hint",
                                    ENV_HINT_DETAIL.format(var="MORPH_MAX_CORES"))
        if getattr(profile, "cpu", None) and profile.cpu.quota_percent:
            out["cpu.quota_percent"] = Fidelity(FieldStatus.UNAVAILABLE, "env hint",
                                                ENV_HINT_DETAIL.format(var="MORPH_CPU_QUOTA_PERCENT"))
        out["memory.total_mb"] = Fidelity(FieldStatus.UNAVAILABLE, "env hint",
                                          ENV_HINT_DETAIL.format(var="MORPH_MEMORY_LIMIT_MB"))
    loc = getattr(profile, "locale", None)
    if loc:
        if windows:
            out["locale.locale"] = Fidelity(FieldStatus.APPROXIMATED, "env",
                                            "LC_ALL exported; the MSVC CRT ignores it")
            out["locale.timezone"] = Fidelity(FieldStatus.APPROXIMATED, "env",
                                              "TZ exported; the MSVC CRT ignores IANA names")
        else:
            out["locale.locale"] = Fidelity(FieldStatus.REPRODUCED, "env", "LC_ALL/LANG exported")
            tz = str(loc.timezone.value) if loc.timezone and loc.timezone.value else ""
            out["locale.timezone"] = (
                Fidelity(FieldStatus.REPRODUCED, "env", "TZ exported (IANA zone)")
                if is_iana_timezone(tz)
                else Fidelity(FieldStatus.APPROXIMATED, "env",
                              f"TZ={tz!r} is not an IANA zone; libc treats it as UTC")
            )
    return out


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes", "on")


def no_native_side_effects() -> bool:
    """True when tests/CI ask adapters not to touch tc/dnctl/cgroups/sudo."""
    return _truthy(os.environ.get("MORPH_NO_NATIVE")) or _truthy(os.environ.get("MORPH_NO_NETWORK"))
