"""Failure A: timeout under network latency.

Mechanism: a client with a tight deadline calls a local server that always takes
~200 ms to respond. Under normal (near-zero) loopback latency the response beats
the deadline. Add round-trip latency and the response arrives after the
client's timeout fires.

    Env knob Morph turns : network latency (profile ``network.latency_ms``, an RTT)
    Baseline (0 ms added) : ~205 ms < 250 ms deadline -> PASS
    Fails when           : RTT pushes the response past 250 ms, i.e. ~45 ms RTT
    Fix (one line)       : raise CLIENT_TIMEOUT (--fixed sets 1.0 s)
    Classification       : environment-caused

The ONLY way this app fails is its deadline (``httpx.TimeoutException``).
Morph's proxy never corrupts the byte stream: packet loss is delivered as a
retransmission stall (``max(200 ms, 3 x RTT)``), so under loss the request
simply arrives late and trips the same deadline. Anything that is not a
timeout (connection refused, protocol error) is a setup error and exits 2:
an *invalid* trial the engine discards rather than counts.

How the condition reaches the app: when Morph cannot shape the loopback
interface natively (no root), its runtime exports ``MORPH_NET_LATENCY_MS`` /
``MORPH_NET_PACKET_LOSS_PCT`` and this app fronts its own server with Morph's
TCP proxy (``apps/netshape.py``). With native shaping (root + tc/dnctl) those
variables are absent and the app runs unshaped by itself. The server never
sleeps for a latency value of its own: the delay comes from the network path,
once, exactly as it would in production.

Tuning knobs (env vars):

    MORPH_A_RESP_DELAY_S  server response delay in seconds (default 0.20)
    MORPH_A_TIMEOUT       client timeout in seconds (default 0.25)
    MORPH_A_FIXED_TIMEOUT client timeout for --fixed (default 1.0)
"""

from __future__ import annotations

import http.server
import json
import os
import sys
import threading
import time

import httpx

from apps.netshape import start_proxy

RESP_DELAY_S = float(os.getenv("MORPH_A_RESP_DELAY_S", "0.20"))
DEFAULT_TIMEOUT_S = float(os.getenv("MORPH_A_TIMEOUT", "0.25"))
FIXED_TIMEOUT_S = float(os.getenv("MORPH_A_FIXED_TIMEOUT", "1.0"))


class _Handler(http.server.BaseHTTPRequestHandler):
    # Buffer the response so headers and body leave in ONE write. Two writes
    # would be two proxy chunks, each an independent loss event, which makes
    # the fixture's loss sensitivity depend on socket timing.
    wbufsize = -1

    def do_GET(self) -> None:
        time.sleep(RESP_DELAY_S)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:  # silence default request logging
        pass


class _QuietServer(http.server.ThreadingHTTPServer):
    """Suppresses tracebacks from clients that disconnect mid-response.

    When the client's timeout fires it drops the connection while the handler is
    still sleeping; the subsequent write raises ConnectionAborted/Reset/BrokenPipe
    and socketserver would dump a full traceback to stderr. That is the *expected*
    path for this fixture, and Morph parses stderr to identify the failure signal,
    so leaving the noise in would mislabel every failure.
    """

    daemon_threads = True

    def handle_error(self, request, client_address) -> None:
        exc = sys.exc_info()[1]
        if isinstance(exc, (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def _run_once(client_timeout: float) -> dict:
    """Starts a local server, makes one request against it, tears it down.

    Returns the result dict; does not print or exit (kept separate for testability).
    """
    srv = _QuietServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    proxy_shutdown = None
    client = None
    try:
        port, proxy_shutdown = start_proxy(srv.server_address[1])

        # httpx.get() would build a fresh Client per call, which on some machines
        # costs ~300 ms of proxy/env/netrc probing *outside* httpx's own timeout,
        # corrupting duration_ms without ever tripping the deadline. Build it
        # once, before the timer starts, with env probing off.
        client = httpx.Client(trust_env=False)

        t0 = time.monotonic()
        try:
            client.get(f"http://127.0.0.1:{port}/", timeout=client_timeout)
            result, signal, detail = "pass", None, ""
        except httpx.TimeoutException:
            result, signal = "fail", "TimeoutException"
            detail = f"deadline {client_timeout * 1000:.0f}ms exceeded"
        except httpx.HTTPError as exc:
            # Not the engineered failure: connection refused, protocol error.
            # The caller maps this to exit 2 (invalid trial).
            result, signal, detail = "error", type(exc).__name__, str(exc)
        duration_ms = (time.monotonic() - t0) * 1000
    finally:
        if client is not None:
            client.close()
        if proxy_shutdown is not None:
            proxy_shutdown()
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)
    return {
        "result": result,
        "signal": signal,
        "duration_ms": round(duration_ms),
        "detail": detail,
    }


def main(machine_mode: bool, fixed: bool) -> int:
    client_timeout = FIXED_TIMEOUT_S if fixed else DEFAULT_TIMEOUT_S
    outcome = _run_once(client_timeout)

    if machine_mode:
        print(json.dumps(outcome))
    else:
        label = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[outcome["result"]]
        print(f"[timeout] {label} in {outcome['duration_ms']}ms "
              f"(timeout={client_timeout * 1000:.0f}ms, signal={outcome['signal']})")
        if outcome["detail"]:
            print(f"  detail: {outcome['detail']}")

    if outcome["result"] == "pass":
        return 0
    if outcome["result"] == "fail":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(machine_mode="test" in sys.argv, fixed="--fixed" in sys.argv))
