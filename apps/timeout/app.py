"""Failure A: timeout under network latency.

Mechanism: a client with a tight timeout calls a local server that always takes
~200ms to respond. Under normal (near-zero) loopback latency the response beats
the deadline. Add latency on `lo` (see docs/faultyapps.md section 6) and the
response arrives after the client's timeout fires.

    Env knob Morph turns : network latency on the loopback interface
    Baseline (0ms added) : ~200ms < 250ms deadline -> PASS,  ~100/100
    Fails when           : added latency pushes round-trip past ~250ms
    Fix (one line)       : raise CLIENT_TIMEOUT (--fixed sets 1.0s)
    Classification       : environment-caused

Tuning knobs are env vars so they can be re-tuned during the hackathon without
touching code:

    MORPH_A_RESP_DELAY_S  server response delay in seconds (default 0.20)
    MORPH_A_TIMEOUT       client timeout in seconds (default 0.25)
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
    def do_GET(self) -> None:
        time.sleep(RESP_DELAY_S)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args) -> None:  # silence default request logging
        pass


class _QuietServer(http.server.ThreadingHTTPServer):
    """Suppresses tracebacks from clients that disconnect mid-response.

    When the client's timeout fires it drops the connection while the handler is
    still sleeping; the subsequent write raises ConnectionAborted/Reset/BrokenPipe
    and socketserver would dump a full traceback to stderr. That is the *expected*
    path for this fixture, and Morph parses stderr to identify the failure signal
    (see architecture.md 5.4) -- leaving the noise in would mislabel every failure.
    Unexpected errors still propagate to the default handler.
    """

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

    # When Morph shapes the loopback natively (tc netem / dnctl) this is a
    # no-op; when it can't (no root), it passes the latency through
    # MORPH_NET_LATENCY_MS and we front our own server with Morph's TCP proxy.
    port, proxy_shutdown = start_proxy(srv.server_address[1])

    # httpx.get() would build a fresh httpx.Client() per call -- on some
    # machines that alone costs ~300ms+ (proxy/env/netrc probing), *outside*
    # httpx's own timeout enforcement, which corrupts duration_ms without ever
    # tripping the timeout. Build the client once, before the timer starts,
    # and disable env probing (the app has no network egress requirement).
    client = httpx.Client(trust_env=False)

    # Measure only the client request itself. srv.shutdown() below waits on
    # ThreadingHTTPServer's serve_forever poll_interval (default 0.5s), which
    # would otherwise inflate duration_ms far past the actual request latency.
    t0 = time.monotonic()
    try:
        client.get(f"http://127.0.0.1:{port}/", timeout=client_timeout)
        result, signal, detail = "pass", None, ""
    except httpx.TimeoutException:
        result, signal = "fail", "TimeoutException"
        detail = f"deadline {client_timeout * 1000:.0f}ms exceeded"
    except httpx.HTTPError as exc:
        # anything else (connection refused, etc.) is a setup error, not the
        # engineered failure -- caller maps this to exit code 2.
        result, signal, detail = "error", type(exc).__name__, str(exc)
    duration_ms = (time.monotonic() - t0) * 1000
    client.close()

    if proxy_shutdown is not None:
        proxy_shutdown()
    srv.shutdown()
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
