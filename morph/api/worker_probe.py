"""One cached view of the cloud worker, shared by the routes that need it.

Both /parameters (which bounds its cores and memory sliders by what hardware
actually exists) and /platform (which lists the worker as a run target) need
the same answer to the same question. The configuration screen fetches both on
load, so without sharing this the UI would pay two SSH handshakes to learn one
thing.

The cache exists because worker hardware does not change between page loads.
A result that is stale by a couple of minutes is a far better trade than an
SSH round trip in front of every render -- and failures are cached too, so an
unreachable box costs one timeout rather than one per request.
"""

from __future__ import annotations

import time

from morph.cloud.worker import WorkerInfo

_TTL_S = 120.0
_cache: tuple[float, WorkerInfo | None] | None = None


def probe(*, force: bool = False) -> WorkerInfo | None:
    """The worker's state, or None when no worker is configured at all.

    Never raises. Every failure mode here -- no config, no ssh binary, a box
    that does not answer -- means the same thing to a caller: there is no
    worker capacity to offer right now.
    """
    global _cache
    now = time.monotonic()
    if not force and _cache is not None and _cache[0] > now:
        return _cache[1]

    info: WorkerInfo | None = None
    try:
        from morph.cloud.worker import RemoteWorker
        from morph.config import load_config

        cloud = load_config().cloud
        if cloud.enabled and cloud.host:
            info = RemoteWorker(cloud).check()
    except Exception:
        info = None

    _cache = (now + _TTL_S, info)
    return info


def reset_cache() -> None:
    """Drop the cached probe. For tests, and for a config change mid-session."""
    global _cache
    _cache = None
