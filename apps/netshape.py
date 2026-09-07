"""Shared in-process network shaping for the demo apps.

When Morph's runtime cannot shape the real network interface (no root on
macOS/Windows, or the cross-platform CI proxy adapter), it hands the requested
conditions to the target as environment variables instead:

    MORPH_NET_LATENCY_MS       one-way latency to inject, milliseconds
    MORPH_NET_PACKET_LOSS_PCT  chunk-drop probability, percent

A demo app that hosts its own localhost server (so there is nothing for an
external proxy to sit in front of) calls ``start_proxy(upstream_port)``. If a
condition is set it starts Morph's real TCP proxy
(``morph.runtime.adapters.proxy.ProxyServer``) in front of the app's server on
a background event loop and returns ``(proxy_port, shutdown)``; otherwise it
returns ``(upstream_port, None)`` and the app runs unshaped. The delay and the
chunk drops are the exact code path Morph uses when it shapes a real NIC, just
hosted inside the target because that is the only place the app's own loopback
socket is reachable.
"""

from __future__ import annotations

import asyncio
import os
import threading
from collections.abc import Callable


def net_conditions() -> tuple[float, float]:
    """(latency_ms, packet_loss_percent) requested via env, or (0.0, 0.0)."""
    latency = float(os.getenv("MORPH_NET_LATENCY_MS", "0") or 0.0)
    loss = float(os.getenv("MORPH_NET_PACKET_LOSS_PCT", "0") or 0.0)
    return latency, loss


def start_proxy(
    upstream_port: int,
    *,
    latency_ms: float | None = None,
    loss_pct: float | None = None,
    upstream_host: str = "127.0.0.1",
) -> tuple[int, Callable[[], None] | None]:
    """Put Morph's TCP proxy in front of ``upstream_port`` if a condition applies.

    ``latency_ms`` / ``loss_pct`` override the env-derived values when given
    (app-specific knobs still win). Returns ``(port_to_connect_to, shutdown)``;
    ``shutdown`` is ``None`` when no proxy was started.
    """
    env_latency, env_loss = net_conditions()
    latency = env_latency if latency_ms is None else latency_ms
    loss = env_loss if loss_pct is None else loss_pct

    if latency <= 0.0 and loss <= 0.0:
        return upstream_port, None

    from morph.runtime.adapters.proxy import ProxyServer

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    proxy = ProxyServer(
        upstream_host=upstream_host,
        upstream_port=upstream_port,
        latency_ms=latency,
        packet_loss_percent=loss,
    )
    asyncio.run_coroutine_threadsafe(proxy.start(), loop).result(timeout=5)

    def shutdown() -> None:
        try:
            asyncio.run_coroutine_threadsafe(proxy.stop(), loop).result(timeout=5)
        finally:
            loop.call_soon_threadsafe(loop.stop)

    return proxy.port, shutdown
