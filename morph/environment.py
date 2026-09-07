"""Morph environment context manager for tests and executable invariants."""

from __future__ import annotations

import contextlib
import os
from collections.abc import Iterator
from typing import Any


@contextlib.contextmanager
def environment(
    latency_ms: float | None = None,
    packet_loss: float | None = None,
    jitter_ms: float | None = None,
    bandwidth_mbps: float | None = None,
    cpu_quota: float | None = None,
    memory_mb: float | None = None,
    **kwargs: Any,
) -> Iterator[dict[str, str]]:
    """Context manager that injects mock/virtual environment boundaries into runtime env vars.

    Usage:
        with morph.environment(latency_ms=160, packet_loss=0.01):
            result = run_checkout_flow()
            assert result.status_code == 200
    """
    injected: dict[str, str] = {}
    if latency_ms is not None:
        injected["MORPH_LATENCY_MS"] = str(latency_ms)
    if packet_loss is not None:
        # Accept either percentage (0-100) or fraction (0-1.0)
        pct = packet_loss * 100.0 if 0 < packet_loss < 1.0 else packet_loss
        injected["MORPH_PACKET_LOSS"] = str(pct)
    if jitter_ms is not None:
        injected["MORPH_JITTER_MS"] = str(jitter_ms)
    if bandwidth_mbps is not None:
        injected["MORPH_BANDWIDTH_MBPS"] = str(bandwidth_mbps)
    if cpu_quota is not None:
        injected["MORPH_CPU_QUOTA"] = str(cpu_quota)
    if memory_mb is not None:
        injected["MORPH_MEMORY_MB"] = str(memory_mb)

    for k, v in kwargs.items():
        key = f"MORPH_{k.upper()}"
        injected[key] = str(v)

    old_values: dict[str, str | None] = {k: os.environ.get(k) for k in injected}

    try:
        for k, v in injected.items():
            os.environ[k] = v
        yield injected
    finally:
        for k, old in old_values.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old
