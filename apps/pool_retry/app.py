"""Failure B (FLAGSHIP): latency AND packet loss interaction.

This is the fixture that proves Morph finds *combinations*, not just single
toggles. Neither condition alone breaks it. Together they do.

    latency alone     -> PASS
    packet loss alone -> PASS
    latency + loss    -> FAIL

Mechanism. A client fires N_REQUESTS concurrent requests through a small
connection pool (POOL_MAX slots), with a per-request read timeout, bounded
retries, and one overall wall-clock DEADLINE_S budget. The server answers in
~80 ms.

The interaction lives in how a lost packet costs time on a real TCP path: a
loss is not a missing byte, it is a *retransmission stall* of roughly
``max(200 ms, 3 x RTT)`` (Linux's minimum RTO, then the RTT-scaled estimate),
which is exactly what Morph's proxy emulates.

  - Latency alone (120 ms RTT): every request costs 80 ms + 120 ms = 200 ms;
    the batch runs in ceil(N/POOL) waves. Slower, but well inside the deadline.
  - Loss alone (18 %): a stall is 200 ms at near-zero RTT; 80 + 200 = 280 ms
    still fits inside the 500 ms read timeout, so the request just arrives a
    little late. No retry, no slot held.
  - Both: the stall is now 3 x 120 = 360 ms, and 200 + 360 = 560 ms is PAST the
    read timeout. Every single loss now burns a full read timeout, the retry
    goes through the pool queue again, and with N requests sharing POOL_MAX
    slots the queue cascades past the deadline.

    Env knobs Morph turns : latency AND packet loss (profile ``network.*``)
    Baseline              : batch ~0.7 s -> PASS
    Fix (one line)        : POOL_MAX = N_REQUESTS (no queueing) via --fixed
    Classification        : environment-caused, INTERACTION

Conditions are real, not simulated: Morph's runtime exports MORPH_NET_* and
this app fronts its own server with Morph's TCP proxy (apps/netshape.py), the
same delay-line and retransmission model Morph uses everywhere it cannot shape
a real interface. The proxy never corrupts bytes, so the only failure path is
the deadline (``DeadlineExceeded``); a setup error exits 2.
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

from apps.netshape import start_proxy

# Operating point, measured (see README "How the deadline was chosen"). The
# deadline sits in the gap between the slowest leg that must pass (latency
# alone, or --fixed under both) and the fastest that must fail (both).
DEADLINE_S = float(os.getenv("MORPH_B_DEADLINE", "2.8"))
POOL_MAX = int(os.getenv("MORPH_B_POOL", "2"))
PER_REQ_TIMEOUT = float(os.getenv("MORPH_B_REQ_TIMEOUT", "0.5"))
# A request dies only if EVERY attempt is lost; with enough retries that
# probability is negligible for the --fixed and loss-alone legs, while the
# pooled variant still pays a read timeout per retry, which is the cascade.
RETRIES = int(os.getenv("MORPH_B_RETRIES", "5"))
N_REQUESTS = int(os.getenv("MORPH_B_N", "16"))
SERVER_DELAY_S = float(os.getenv("MORPH_B_SERVER_DELAY", "0.08"))

# MORPH_B_PROXY_* are per-app overrides; absent those, Morph's runtime passes
# the isolated conditions through the generic MORPH_NET_* vars (see
# apps/netshape.py). None here means "defer to the generic vars".
_ENV_LAT = os.getenv("MORPH_B_PROXY_LATENCY_MS")
_ENV_LOSS = os.getenv("MORPH_B_PROXY_LOSS_PCT")
PROXY_LATENCY_MS = float(_ENV_LAT) if _ENV_LAT is not None else None
PROXY_LOSS_PCT = float(_ENV_LOSS) if _ENV_LOSS is not None else None


class _Handler(http.server.BaseHTTPRequestHandler):
    # Buffer the response so headers and body leave in ONE write: one proxy
    # chunk, one loss event. Two writes would make the per-request loss
    # probability depend on socket timing instead of on the loss rate.
    wbufsize = -1

    def do_GET(self) -> None:
        time.sleep(SERVER_DELAY_S)
        try:
            self.send_response(200)
            # Content-Length is required, not cosmetic: without it the client
            # can only detect the end of the body by connection EOF.
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
# timeout (the wait for a free connection). With N requests queued behind
# POOL_MAX slots, ordinary queueing would then trip PoolTimeout and be
# indistinguishable from a network stall. Only the READ timeout models "the
# response never arrived"; queueing is governed by the batch deadline.
_TIMEOUT = httpx.Timeout(PER_REQ_TIMEOUT, pool=DEADLINE_S + PER_REQ_TIMEOUT)


def _fetch(client: httpx.Client, url: str, deadline_at: float) -> bool:
    """One logical request with bounded retries. True if it eventually succeeded."""
    for _ in range(RETRIES + 1):
        if time.monotonic() >= deadline_at:
            return False
        try:
            client.get(url, timeout=_TIMEOUT)
            return True
        except httpx.HTTPError:
            continue                          # timed out or reset: retry
    return False


def main(machine_mode: bool, fixed: bool) -> int:
    pool_max = N_REQUESTS if fixed else POOL_MAX

    srv = _QuietServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    proxy_shutdown = None
    client = None
    try:
        # Morph's real TCP proxy in front of our own server when a condition is
        # set, via MORPH_B_PROXY_* (per-app override) or generic MORPH_NET_*.
        port, proxy_shutdown = start_proxy(
            srv.server_address[1], latency_ms=PROXY_LATENCY_MS, loss_pct=PROXY_LOSS_PCT
        )
        url = f"http://127.0.0.1:{port}/"

        # Built before the timer: constructing a Client costs ~350 ms on some
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
    finally:
        if client is not None:
            client.close()
        if proxy_shutdown is not None:
            proxy_shutdown()
        srv.shutdown()
        srv.server_close()
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
