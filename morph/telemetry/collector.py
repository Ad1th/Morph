"""Spawn a subprocess, capture output, track peak RSS + duration, kill cleanly on timeout."""

from __future__ import annotations

import os
import re
import shlex
import signal
import subprocess
import sys
import threading
import time
import uuid
from datetime import UTC, datetime

import psutil

from morph.schema.telemetry import RunResult, TelemetryData
from morph.telemetry.parser import (
    extract_error_message,
    extract_error_type,
    extract_stack_trace,
)
from morph.telemetry.provenance import host_fingerprint, morph_version, seed_from_env

# 100 ms, not 20: psutil enumerates the whole process table on every sample
# (it needs a ppid map for children(recursive=True)), which at 50 Hz cost a
# core on macOS and perturbed exactly the timing-sensitive runs Morph measures.
_MONITOR_INTERVAL_S = 0.1
_KILL_GRACE_S = 3.0

# Captured stdout/stderr are bounded so a chatty target cannot blow up the
# host's memory or the JSON result. The TAIL is kept: the failure is at the
# end of the output, not the start.
MAX_CAPTURE_BYTES = 2 * 1024 * 1024
_TRUNCATION_NOTE = "[... morph: output truncated, tail kept ...]\n"

# apps/README.md and docs/faultyapps.md: exit 2 means "invalid trial -- the app
# could not even attempt the test" (bad arguments, missing fixture, setup
# error). 126/127 are the shell's "not executable" / "not found".
_INVALID_EXIT_CODES = {2: "exit 2: the app could not attempt the test (setup/usage error)",
                       126: "exit 126: command is not executable",
                       127: "exit 127: command not found"}

# A bare `python` / `python3` / `python3.12` as the command's first token is
# ambiguous: on PATH it may resolve to an interpreter that lacks Morph's or the
# target corpus's dependencies (the classic "works on my machine"). Morph runs
# targets as separate processes, not by importing them, so pinning the launcher
# to the interpreter Morph itself runs under is safe and removes that whole
# failure class from the demo. An explicit path (``/usr/bin/python3``, ``.venv/
# bin/python``) never matches this pattern and is passed through untouched.
_BARE_PYTHON_RE = re.compile(r"^python(?:3(?:\.\d+)?)?$")


def _pin_interpreter(argv: list[str]) -> list[str]:
    if argv and _BARE_PYTHON_RE.match(argv[0]):
        return [sys.executable, *argv[1:]]
    return argv


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


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


def _signal_group(pid: int, descendants: list, sig: int) -> None:
    try:
        os.killpg(pid, sig)
    except (ProcessLookupError, PermissionError, OSError):
        pass
    for p in descendants:  # anything that setsid'd away from the group
        try:
            p.send_signal(sig)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass


def _kill_tree(proc: subprocess.Popen) -> None:
    """Terminate the child and every descendant.

    POSIX: the child was started in its own session (`start_new_session=True`),
    so its pid IS its process-group id. Signal the whole group FIRST -- before
    anything reaps the root -- then sweep with psutil for any grandchild that
    `setsid`'d away from the group. Windows: the child was created in its own
    process group; `taskkill /T` walks the tree.
    """
    pid = proc.pid
    try:
        root = psutil.Process(pid)
        descendants = root.children(recursive=True)
    except psutil.NoSuchProcess:
        return
    procs = [root, *descendants]

    if os.name != "nt":
        _signal_group(pid, descendants, signal.SIGTERM)
        _gone, alive = psutil.wait_procs(procs, timeout=_KILL_GRACE_S)
        if alive:
            _signal_group(pid, descendants, signal.SIGKILL)
            psutil.wait_procs(alive, timeout=_KILL_GRACE_S)
        return

    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=_KILL_GRACE_S
        )
    except (OSError, subprocess.SubprocessError):
        pass
    for p in procs:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(procs, timeout=_KILL_GRACE_S)


def _limit_resources(max_processes: int | None, fd_limit: int | None, cgroup_path: str | None) -> None:
    """preexec_fn: POSIX rlimits and an explicit cgroup join, in the child before exec.

    Only installed when one of these was actually requested (preexec_fn forces
    the slow fork() path and is documented as unsafe with threads). Never
    called on Windows -- subprocess.Popen rejects preexec_fn there outright.
    """
    import resource

    if max_processes is not None:
        resource.setrlimit(resource.RLIMIT_NPROC, (max_processes, max_processes))
    if fd_limit is not None:
        resource.setrlimit(resource.RLIMIT_NOFILE, (fd_limit, fd_limit))
    if cgroup_path:
        with open(os.path.join(cgroup_path, "cgroup.procs"), "w") as f:
            f.write(str(os.getpid()))


def _clamp_rlimits(
    max_processes: int | None, fd_limit: int | None
) -> tuple[int | None, int | None, list[str]]:
    """Clamp requested rlimits to this host's hard limits; return notes for anything clamped.

    A profile captured on Linux (NOFILE soft 1,048,576) replayed on macOS
    (hard ~10k) would otherwise make setrlimit raise in the child.
    """
    notes: list[str] = []
    if os.name == "nt":
        return max_processes, fd_limit, notes
    import resource

    def clamp(name: str, res: int, value: int | None) -> int | None:
        if value is None:
            return None
        _soft, hard = resource.getrlimit(res)
        if hard != resource.RLIM_INFINITY and value > hard:
            notes.append(f"{name} clamped from {value} to host hard limit {hard}")
            return hard
        return value

    return (
        clamp("max_processes", resource.RLIMIT_NPROC, max_processes),
        clamp("fd_limit", resource.RLIMIT_NOFILE, fd_limit),
        notes,
    )


def _tail(text: str, limit: int = MAX_CAPTURE_BYTES) -> str:
    if len(text) <= limit:
        return text
    return _TRUNCATION_NOTE + text[-limit:]


def _early_result(*, exit_code: int, stderr: str, duration_ms: float,
                  error_type: str, error_message: str, command: str,
                  invalid_reason: str | None = None) -> RunResult:
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
        invalid=True,
        invalid_reason=invalid_reason or f"could not launch: {error_type}: {error_message}",
        command=command,
        seed=seed_from_env(),
        morph_version=morph_version(),
        host_fingerprint=host_fingerprint(),
    )


def run_with_telemetry(
    command: str,
    env: dict | None = None,
    timeout: float = 30.0,
    cwd: str | None = None,
    max_processes: int | None = None,
    fd_limit: int | None = None,
    cgroup_path: str | None = None,
) -> RunResult:
    """Run `command`, returning a populated RunResult.

    `env`, if given, is passed verbatim to the child and fully replaces its
    environment. Callers wanting os.environ + overrides should go through
    `morph.runtime.runner.execute_command`, which does the merge.

    `max_processes`/`fd_limit` apply POSIX rlimits (RLIMIT_NPROC/RLIMIT_NOFILE)
    to the child before exec, clamped to this host's hard limits. `cgroup_path`
    (a cgroup-v2 directory Morph may write to) puts the child in that cgroup.
    All three are silently ignored on Windows: there is no direct equivalent
    without a pywin32 dependency this project doesn't have.

    Never raises for anything the child does: undecodable output is replaced,
    a refused rlimit or an unlaunchable command comes back as an `invalid`
    RunResult, and stdout/stderr are bounded to MAX_CAPTURE_BYTES (tail kept).
    """
    if not command.strip():
        raise ValueError("command is empty")

    if env is not None and "MORPH_SEED" in env:
        try:
            seed: int | None = int(env["MORPH_SEED"])
        except (TypeError, ValueError):
            seed = None
    else:
        seed = seed_from_env()

    max_processes, fd_limit, limit_notes = _clamp_rlimits(max_processes, fd_limit)

    popen_kwargs = dict(
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace",
        cwd=cwd, env=env,
    )
    wants_limits = max_processes is not None or fd_limit is not None or bool(cgroup_path)
    if os.name != "nt" and wants_limits:
        popen_kwargs["preexec_fn"] = lambda: _limit_resources(max_processes, fd_limit, cgroup_path)

    if os.name == "nt":
        # Windows' CreateProcess takes the whole command line as one string
        # and does its own native quoting/backslash parsing -- passing it
        # through untouched is both correct AND what a real Windows path or
        # a manually-typed command already assumes. Re-splitting with shlex
        # (a POSIX-shell concept) previously mismatched real-world command
        # strings: `posix=False` corrupted shlex.join()-built commands, and
        # `posix=True` corrupted raw Windows paths (their backslashes are
        # POSIX escape characters), breaking one calling style or the other.
        # Only the leading bare-`python` token is rewritten (see _pin_interpreter);
        # the rest of the command line is left exactly as given.
        head, sep, tail = command.partition(" ")
        if _BARE_PYTHON_RE.match(head):
            command_line = f'"{sys.executable}"{sep}{tail}'
        else:
            command_line = command
        popen_target: str | list[str] = command_line
        # Own process group so _kill_tree can take the whole tree down.
        popen_kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        # POSIX Popen (shell=False) requires an argv list; shlex.split with
        # posix=True is the correct, standard way to tokenize a shell-style
        # command string here.
        try:
            popen_target = _pin_interpreter(shlex.split(command, posix=True))
        except ValueError as exc:
            return _early_result(exit_code=2, stderr=str(exc), duration_ms=0.0,
                                 error_type="ValueError", error_message=f"cannot parse command: {exc}",
                                 command=command)
        # Own session => pid == pgid, so a timeout can kill the whole group.
        popen_kwargs["start_new_session"] = True

    start = time.perf_counter()
    try:
        proc = subprocess.Popen(popen_target, **popen_kwargs)
    except FileNotFoundError as exc:
        return _early_result(exit_code=127, stderr=str(exc),
                             duration_ms=(time.perf_counter() - start) * 1000,
                             error_type="FileNotFoundError", error_message=str(exc),
                             command=command)
    except (PermissionError, OSError, subprocess.SubprocessError) as exc:
        # SubprocessError covers "Exception occurred in preexec_fn" -- an rlimit
        # or cgroup the host refused. That is a setup problem, not a failure
        # of the application.
        return _early_result(exit_code=126, stderr=str(exc),
                             duration_ms=(time.perf_counter() - start) * 1000,
                             error_type=type(exc).__name__, error_message=str(exc),
                             command=command)

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
        _kill_tree(proc)
        try:
            out, err = proc.communicate(timeout=5)
            stdout, stderr = out or "", err or ""
        except Exception:
            # A daemonised grandchild may still hold the pipes; do not wait on it.
            for stream in (proc.stdout, proc.stderr):
                try:
                    if stream:
                        stream.close()
                except Exception:
                    pass
    finally:
        stop.set()
        mon.join(timeout=2)

    duration_ms = (time.perf_counter() - start) * 1000
    exit_code = proc.returncode if proc.returncode is not None else -1
    peak_mb = stats["peak_rss"] / (1024 * 1024) if stats["peak_rss"] else None
    stdout, stderr = _tail(stdout or ""), _tail(stderr or "")

    invalid, invalid_reason = False, None
    if timed_out:
        passed, error_type = False, "TimeoutExpired"
        error_message = f"Command timed out after {timeout}s"
        if exit_code == 0:
            exit_code = -1
    else:
        passed = exit_code == 0
        error_type = None if passed else extract_error_type(stderr, stdout)
        error_message = None if passed else extract_error_message(stderr, stdout)
        if exit_code in _INVALID_EXIT_CODES:
            invalid, invalid_reason = True, _INVALID_EXIT_CODES[exit_code]

    extra: dict = {}
    stack_trace = None if passed else extract_stack_trace(stderr)
    if stack_trace:
        extra["stack_trace"] = stack_trace
    if timed_out:
        extra["timed_out"] = True
    if limit_notes:
        extra["rlimit_notes"] = limit_notes

    return RunResult(
        run_id=_new_run_id(),
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
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
        invalid=invalid,
        invalid_reason=invalid_reason,
        command=command,
        seed=seed,
        morph_version=morph_version(),
        host_fingerprint=host_fingerprint(),
    )
