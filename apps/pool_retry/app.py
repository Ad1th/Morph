"""Failure B (FLAGSHIP): latency AND packet loss interaction.

This is the fixture that proves Morph finds *combinations*, not just single
toggles. Neither condition alone breaks it. Together they do.

    latency alone    -> PASS
    packet loss alone-> PASS
    latency + loss   -> FAIL

Mechanism. A client fires N_REQUESTS concurrent requests through a small
connection pool (POOL_MAX slots), with bounded retries and one overall
wall-clock DEADLINE_S budget. The server answers in ~80ms.

  - Latency alone: every request costs 80ms + RTT. With POOL_MAX slots the
    batch runs in ceil(N/POOL) waves. Slower, but inside the deadline.
  - Loss alone: a dropped packet stalls one request until its per-request
    timeout fires, then it retries. At low latency that retry is cheap, and
    the other requests drain quickly through the free slot.
  - Both: the stalled request holds its pool slot for the whole per-request
    timeout while every remaining request is now ALSO slow (RTT on each), so
    they queue behind the reduced pool. The queue cascades past the deadline.

    Env knobs Morph turns : latency AND packet loss (on lo, or via proxy)
    Baseline              : batch ~240ms -> PASS
    Fix (one line)        : POOL_MAX = N_REQUESTS (no queueing) via --fixed
    Classification        : environment-caused, INTERACTION

Simulated conditions (for verification where tc/Clumsy are unavailable):

    MORPH_B_SIM_LATENCY_MS   extra ms the server adds to every response
    MORPH_B_SIM_STALL_PCT    % of requests the server stalls past the client's
                             per-request timeout

Real packet loss does not lose whole requests -- it costs a TCP retransmit
timeout. So loss is emulated as a per-request probability of a stall, which is
the same thing the client experiences. NOTE: the mapping from netem's "loss 2%"
to a per-request stall percentage is NOT 1:1 (one HTTP request is many packets,
and TCP retransmits), so MORPH_B_SIM_STALL_PCT must be recalibrated against real
netem on the Pi before any number here is quoted as a real-world figure.
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

# Tuned so that each condition ALONE stays inside the deadline and only the
# combination cascades past it. The deadline is placed in the measured gap
# between the slowest passing leg (latency alone, max 2298ms) and the fastest
# failing one (both, min 2466ms). See the README for the full distributions.
DEADLINE_S = float(os.getenv("MORPH_B_DEADLINE", "2.4"))
POOL_MAX = int(os.getenv("MORPH_B_POOL", "2"))
PER_REQ_TIMEOUT = float(os.getenv("MORPH_B_REQ_TIMEOUT", "0.5"))
# 4 retries, not 2: a request dies only if EVERY attempt is dropped, with
# probability loss^(retries+1). At 2 retries that killed enough requests to
# fail the --fixed and loss-alone legs outright, no matter the pool size.
RETRIES = int(os.getenv("MORPH_B_RETRIES", "4"))
N_REQUESTS = int(os.getenv("MORPH_B_N", "12"))
SERVER_DELAY_S = float(os.getenv("MORPH_B_SERVER_DELAY", "0.08"))

# Real network conditions, injected by Morph's user-space TCP proxy rather than
# faked in the server. The proxy relays chunks and genuinely drops them, so a
# lost response never arrives and the client's read timeout fires on a real
# connection. It also delays each direction, so round-trip grows by ~2x the
# configured latency -- the same doubling real netem shows on loopback.
PROXY_LATENCY_MS = float(os.getenv("MORPH_B_PROXY_LATENCY_MS", "0"))
PROXY_LOSS_PCT = float(os.getenv("MORPH_B_PROXY_LOSS_PCT", "0"))


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        time.sleep(SERVER_DELAY_S)
        try:
            self.send_response(200)
            # Content-Length is required here, not cosmetic: without it the
            # client can only detect the end of the body by connection EOF, and
            # a relaying proxy that does not forward half-close will hang the
            # request until the read timeout fires.
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError):
            pass                              # client already gave up

    def log_message(self, *args) -> None:
        pass


class _QuietServer(http.server.ThreadingHTTPServer):
    """Client timeouts disconnect mid-response by design; those tracebacks would
    otherwise flood stderr, which Morph parses for the failure signal."""

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


# A bare `timeout=PER_REQ_TIMEOUT` sets every httpx timeout INCLUDING the pool
# timeout -- the wait for a free connection. With N requests queued behind
# POOL_MAX slots, ordinary queueing then trips PoolTimeout and is indistinguishable
# from a network stall, which both muddies the mechanism and leaves the baseline
# riding the edge of that timeout. Only the READ timeout should model "the
# response never arrived"; queueing is governed by the batch deadline instead.
_TIMEOUT = httpx.Timeout(PER_REQ_TIMEOUT, pool=DEADLINE_S)


def _fetch(client: httpx.Client, url: str, deadline_at: float) -> bool:
    """One logical request with bounded retries. True if it eventually succeeded."""
    for _ in range(RETRIES + 1):
        if time.monotonic() >= deadline_at:
            return False
        try:
            client.get(url, timeout=_TIMEOUT)
            return True
        except httpx.HTTPError:
            continue                          # timed out or dropped: retry
    return False


def _start_proxy(upstream_port: int) -> tuple[int, object]:
    """Runs Morph's TCP proxy in front of the server, on its own event loop thread.

    Imported lazily so the app still runs standalone when no conditions are set.
    Returns (proxy_port, shutdown_callable).
    """
    import asyncio

    from morph.runtime.adapters.proxy import ProxyServer

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    proxy = ProxyServer(
        upstream_host="127.0.0.1",
        upstream_port=upstream_port,
        latency_ms=PROXY_LATENCY_MS,
        packet_loss_percent=PROXY_LOSS_PCT,
    )
    asyncio.run_coroutine_threadsafe(proxy.start(), loop).result(timeout=5)

    def shutdown() -> None:
        asyncio.run_coroutine_threadsafe(proxy.stop(), loop).result(timeout=5)
        loop.call_soon_threadsafe(loop.stop)

    return proxy.port, shutdown


def main(machine_mode: bool, fixed: bool) -> int:
    pool_max = N_REQUESTS if fixed else POOL_MAX

    srv = _QuietServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    port, proxy_shutdown = srv.server_address[1], None
    if PROXY_LATENCY_MS or PROXY_LOSS_PCT:
        port, proxy_shutdown = _start_proxy(srv.server_address[1])
    url = f"http://127.0.0.1:{port}/"

    # Built before the timer: constructing a Client costs ~350ms on some
    # machines (proxy/env probing) and would otherwise be charged to the batch.
    client = httpx.Client(
        limits=httpx.Limits(max_connections=pool_max, max_keepalive_connections=pool_max),
        trust_env=False,
    )

    t0 = time.monotonic()
    deadline_at = t0 + DEADLINE_S
    with ThreadPoolExecutor(max_workers=N_REQUESTS) as pool:
        results = list(pool.map(lambda _: _fetch(client, url, deadline_at), range(N_REQUESTS)))
    duration_ms = (time.monotonic() - t0) * 1000

    client.close()
    if proxy_shutdown is not None:
        proxy_shutdown()
    srv.shutdown()
    thread.join(timeout=2)

    succeeded = sum(results)
    over_deadline = duration_ms > DEADLINE_S * 1000
    failed = over_deadline or succeeded < N_REQUESTS

    outcome = {
        "result": "fail" if failed else "pass",
        "signal": "DeadlineExceeded" if failed else None,
        "duration_ms": round(duration_ms),
        "detail": (f"{succeeded}/{N_REQUESTS} requests completed in "
                   f"{duration_ms:.0f}ms (deadline {DEADLINE_S * 1000:.0f}ms, "
                   f"pool {pool_max})"),
    }

    if machine_mode:
        print(json.dumps(outcome))
    else:
        print(f"[pool_retry] {'FAIL' if failed else 'PASS'}")
        print(f"  {outcome['detail']}")

    return 1 if failed else 0
