"""Spawn a subprocess, capture output, track peak RSS + duration, kill cleanly on timeout."""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

import psutil

from morph.schema.telemetry import RunResult, TelemetryData
from morph.telemetry.parser import (
    extract_error_message,
    extract_error_type,
    extract_stack_trace,
)

_MONITOR_INTERVAL_S = 0.02
_KILL_GRACE_S = 3.0


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _sample_rss(procs) -> int:
    total = 0
    for p in procs:
        try:
            total += p.memory_info().rss
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return total


def _monitor(pid: int, stop: threading.Event, stats: dict) -> None:
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    while not stop.is_set():
        try:
            procs = [root, *root.children(recursive=True)]
        except psutil.NoSuchProcess:
            break
        rss = _sample_rss(procs)
        if rss > stats["peak_rss"]:
            stats["peak_rss"] = rss
        try:
            cpu = root.cpu_percent(interval=None)
            if cpu > stats["cpu_max"]:
                stats["cpu_max"] = cpu
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
        stop.wait(_MONITOR_INTERVAL_S)


def _kill_tree(pid: int) -> None:
    """Terminate the process and every descendant; escalate to SIGKILL after a grace period."""
    try:
        root = psutil.Process(pid)
    except psutil.NoSuchProcess:
        return
    try:
        procs = root.children(recursive=True)
    except psutil.NoSuchProcess:
        procs = []
    procs.append(root)

    for p in procs:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    _gone, alive = psutil.wait_procs(procs, timeout=_KILL_GRACE_S)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(alive, timeout=_KILL_GRACE_S)

    # Belt-and-suspenders: nuke the process group on POSIX in case a
    # grandchild reparented away from us.
    if os.name != "nt":
        try:
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass


def _early_result(*, exit_code: int, stderr: str, duration_ms: float,
                  error_type: str, error_message: str) -> RunResult:
    return RunResult(
        run_id=_new_run_id(),
        exit_code=exit_code,
        stdout="",
        stderr=stderr,
        duration_ms=duration_ms,
        peak_memory_mb=None,
        passed=False,
        error_type=error_type,
        error_message=error_message,
        timestamp=_now_iso(),
        telemetry=TelemetryData(),
    )


def run_with_telemetry(
    command: str,
    env: Optional[dict] = None,
    timeout: float = 30.0,
    cwd: Optional[str] = None,
) -> RunResult:
    """Run `command`, returning a populated RunResult.

    `env`, if given, is passed verbatim to the child and fully replaces its
    environment. Callers wanting os.environ + overrides should go through
    `morph.runtime.runner.execute_command`, which does the merge.
    """
    if not command.strip():
        raise ValueError("command is empty")

    popen_kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=env
    )
    if os.name == "nt":
        # Windows' CreateProcess takes the whole command line as one string
        # and does its own native quoting/backslash parsing -- passing it
        # through untouched is both correct AND what a real Windows path or
        # a manually-typed command already assumes. Re-splitting with shlex
        # (a POSIX-shell concept) previously mismatched real-world command
        # strings: `posix=False` corrupted shlex.join()-built commands, and
        # `posix=True` corrupted raw Windows paths (their backslashes are
        # POSIX escape characters), breaking one calling style or the other.
        popen_target: str | list[str] = command
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # POSIX Popen (shell=False) requires an argv list; shlex.split with
        # posix=True is the correct, standard way to tokenize a shell-style
        # command string here.
        popen_target = shlex.split(command, posix=True)
        popen_kwargs["start_new_session"] = True

    start = time.perf_counter()
    try:
        proc = subprocess.Popen(popen_target, **popen_kwargs)
    except FileNotFoundError as exc:
        return _early_result(exit_code=127, stderr=str(exc),
                             duration_ms=(time.perf_counter() - start) * 1000,
                             error_type="FileNotFoundError", error_message=str(exc))
    except (PermissionError, OSError) as exc:
        return _early_result(exit_code=126, stderr=str(exc),
                             duration_ms=(time.perf_counter() - start) * 1000,
                             error_type=type(exc).__name__, error_message=str(exc))

    stats = {"peak_rss": 0, "cpu_max": 0.0}
    try:  # one synchronous sample so even sub-20ms processes report a peak
        stats["peak_rss"] = psutil.Process(proc.pid).memory_info().rss
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        pass

    stop = threading.Event()
    mon = threading.Thread(target=_monitor, args=(proc.pid, stop, stats), daemon=True)
    mon.start()

    stdout, stderr, timed_out = "", "", False
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        _kill_tree(proc.pid)
        try:
            out, err = proc.communicate(timeout=5)
            stdout, stderr = out or "", err or ""
        except Exception:
            pass
    finally:
        stop.set()
        mon.join(timeout=2)

    duration_ms = (time.perf_counter() - start) * 1000
    exit_code = proc.returncode if proc.returncode is not None else -1
    peak_mb = stats["peak_rss"] / (1024 * 1024) if stats["peak_rss"] else None

    if timed_out:
        passed, error_type = False, "TimeoutExpired"
        error_message = f"Command timed out after {timeout}s"
        if exit_code == 0:
            exit_code = -1
    else:
        passed = exit_code == 0
        error_type = None if passed else extract_error_type(stderr, stdout)
        error_message = None if passed else extract_error_message(stderr, stdout)

    extra: dict = {}
    stack_trace = None if passed else extract_stack_trace(stderr)
    if stack_trace:
        extra["stack_trace"] = stack_trace
    if timed_out:
        extra["timed_out"] = True

    return RunResult(
        run_id=_new_run_id(),
        exit_code=exit_code,
        stdout=stdout or "",
        stderr=stderr or "",
        duration_ms=duration_ms,
        peak_memory_mb=peak_mb,
        passed=passed,
        error_type=error_type,
        error_message=error_message,
        timestamp=_now_iso(),
        telemetry=TelemetryData(
            cpu_percent=stats["cpu_max"] or None,
            memory_rss_mb=peak_mb,
            extra=extra,
        ),
    )
