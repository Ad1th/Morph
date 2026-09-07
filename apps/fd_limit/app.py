"""Failure E: connection-pool exhaustion under a lowered file-descriptor limit.

Mechanism. A client talks to a local keep-alive server through a "pool" that
opens a fresh connection for every request and never reaps idle ones. Each
pooled connection costs two descriptors in this single-process fixture (the
client socket and the server's accepted socket), so after N requests the
process holds ~2N sockets. On the developer's machine (``ulimit -n`` 1024 or
more) nobody notices. Inside a container or a hardened service unit with
``LimitNOFILE=64`` the pool hits ``EMFILE`` ("Too many open files") halfway
through the batch.

    Env knob Morph turns : RLIMIT_NOFILE (profile ``process.fd_limit``)
    Baseline (host limit) : 48 requests, ~110 descriptors -> PASS
    Fails when           : fd_limit <= ~100 (EMFILE at request ~(limit - 12) / 2)
    Fix (one line)       : reuse the idle keep-alive connection (--fixed)
    Classification       : environment-caused (a resource limit), and the demo
                           of a non-network knob Morph can apply with no root

How the condition reaches the app: Morph's telemetry collector applies
``profile.process.fd_limit`` with ``resource.setrlimit(RLIMIT_NOFILE)`` in the
child before exec (``morph/telemetry/collector.py``). Lowering a soft limit
needs no privileges on macOS or Linux, so this is fully demoable on a laptop.

Exit codes: 0 pass, 1 the engineered failure (``EMFILE``), 2 invalid trial
(the soft limit is below MIN_FDS, or the server cannot start: the environment
cannot run the app at all, which is not evidence about the bug).

Tuning knobs:
    MORPH_E_REQUESTS   requests in the batch (default 48)
    MORPH_E_TIMEOUT_S  per-request socket timeout in seconds (default 2.0)
    MORPH_E_MIN_FDS    soft limit below which the trial is invalid (default 16)
"""

from __future__ import annotations

import errno
import json
import os
import socket
import socketserver
import sys
import threading
import time

N_REQUESTS = int(os.getenv("MORPH_E_REQUESTS", "48"))
SOCKET_TIMEOUT_S = float(os.getenv("MORPH_E_TIMEOUT_S", "2.0"))
# Below this many descriptors the process cannot hold stdio, the listening
# socket and one live connection at once: the environment cannot run the app
# at all, which is an invalid trial (exit 2), not evidence about the pool.
MIN_FDS = int(os.getenv("MORPH_E_MIN_FDS", "16"))

_EXHAUSTED = {errno.EMFILE, errno.ENFILE}


class _Handler(socketserver.StreamRequestHandler):
    """Keep-alive line protocol: one reply per request line, until the client closes."""

    def handle(self) -> None:
        try:
            while True:
                line = self.rfile.readline()
                if not line:
                    return
                self.wfile.write(b"ok\n")
                self.wfile.flush()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError, TimeoutError):
            return


class _Server(socketserver.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True

    def handle_error(self, request, client_address) -> None:
        pass  # client-side timeouts are the expected path; keep stderr clean


def _fd_count() -> int | str:
    """Descriptors currently open in this process (POSIX); "?" when even the
    directory listing cannot get a descriptor, which is itself the symptom."""
    for path in ("/dev/fd", f"/proc/{os.getpid()}/fd"):
        try:
            return len(os.listdir(path))
        except OSError:
            continue
    return "?"


def _soft_limit() -> int | None:
    try:
        import resource
        return resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    except (ImportError, OSError, ValueError):
        return None


def _request(conn: socket.socket) -> None:
    conn.sendall(b"GET /item\n")
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(64)
        if not chunk:
            raise ConnectionResetError("server closed the connection")
        buf += chunk


def _run_batch(port: int, reuse: bool) -> tuple[int, str | None, str]:
    """Returns (requests_completed, failure_signal_or_None, detail)."""
    pool: list[socket.socket] = []       # the leak: grows by one per request when reuse is off
    completed = 0
    try:
        for i in range(N_REQUESTS):
            if reuse and pool:
                conn = pool[-1]           # the fix: reuse the idle keep-alive connection
            else:
                conn = socket.create_connection(("127.0.0.1", port), timeout=SOCKET_TIMEOUT_S)
                pool.append(conn)
            try:
                _request(conn)
            except (TimeoutError, ConnectionResetError, ConnectionAbortedError, BrokenPipeError) as exc:
                # The server side ran out of descriptors: its accept() failed
                # and our connection sits unanswered in the listen backlog.
                fds, limit = _fd_count(), _soft_limit()
                if limit is not None and (fds == "?" or fds >= limit - 2):
                    return completed, "EMFILE", (
                        f"request {i + 1}/{N_REQUESTS}: server could not accept "
                        f"({fds} descriptors open, soft limit {limit}); {type(exc).__name__}")
                return completed, "error", f"request {i + 1}: {type(exc).__name__}: {exc}"
            completed += 1
        return completed, None, f"{completed}/{N_REQUESTS} requests, {len(pool)} pooled connections"
    except OSError as exc:
        if exc.errno in _EXHAUSTED:
            return completed, "EMFILE", (
                f"request {completed + 1}/{N_REQUESTS}: {exc.strerror} "
                f"(errno {exc.errno}; {_fd_count()} descriptors open, soft limit {_soft_limit()})")
        return completed, "error", f"request {completed + 1}: {type(exc).__name__}: {exc}"
    finally:
        for conn in pool:
            try:
                conn.close()
            except OSError:
                pass


def main(machine_mode: bool, fixed: bool) -> int:
    t0 = time.monotonic()
    limit = _soft_limit()
    if limit is not None and limit < MIN_FDS:
        outcome = {"result": "error", "signal": "LimitTooLowToRun", "duration_ms": 0,
                   "detail": (f"soft RLIMIT_NOFILE is {limit}, below the {MIN_FDS} this app needs "
                              f"just to start; the environment cannot run it at all")}
        return _finish(machine_mode, outcome, fixed)
    try:
        srv = _Server(("127.0.0.1", 0), _Handler)
    except OSError as exc:
        outcome = {"result": "error", "signal": "ServerStartFailed", "duration_ms": 0,
                   "detail": f"could not start the local server: {exc} (soft limit {_soft_limit()})"}
        return _finish(machine_mode, outcome, fixed)

    thread = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    thread.start()
    try:
        _completed, signal, detail = _run_batch(srv.server_address[1], reuse=fixed)
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)
    duration_ms = round((time.monotonic() - t0) * 1000)

    if signal is None:
        outcome = {"result": "pass", "signal": None, "duration_ms": duration_ms, "detail": detail}
    elif signal == "EMFILE":
        outcome = {"result": "fail", "signal": "EMFILE", "duration_ms": duration_ms, "detail": detail}
    else:
        outcome = {"result": "error", "signal": signal, "duration_ms": duration_ms, "detail": detail}
    return _finish(machine_mode, outcome, fixed)


def _finish(machine_mode: bool, outcome: dict, fixed: bool) -> int:
    if machine_mode:
        print(json.dumps(outcome))
    else:
        label = {"pass": "PASS", "fail": "FAIL", "error": "ERROR"}[outcome["result"]]
        print(f"[fd_limit] {label} in {outcome['duration_ms']}ms"
              + ("  (--fixed: pool reuses its idle connection)" if fixed else ""))
        print(f"  {outcome['detail']}")
    if outcome["result"] == "pass":
        return 0
    if outcome["result"] == "fail":
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main(machine_mode="test" in sys.argv, fixed="--fixed" in sys.argv))
