"""Crash-safe record of native side effects (tc rules, dnctl pipes, cgroup limits).

`finally:` does not run on SIGKILL, an OOM kill, or a pulled plug. Every native
change an adapter makes is therefore written here BEFORE it is applied and
removed after it is reverted, so a later run -- or `morph doctor` -- can find
and undo what a dead process left behind.

    ~/.morph/state/shaping.json
    {"entries": [{"id": ..., "kind": "tc"|"dnctl"|"cgroup", "pid": ..., "created": ...,
                  "undo": ["sudo", "-n", "tc", "qdisc", "del", ...] | null,
                  "restore": {"path": ..., "value": ...} | null, "detail": ...}]}
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

STATE_DIR = Path.home() / ".morph" / "state"
STATE_FILE_NAME = "shaping.json"


@dataclass
class StateEntry:
    kind: str  # "tc" | "dnctl" | "cgroup"
    detail: str = ""
    undo: list[str] | None = None  # argv that reverts the change
    restore: dict | None = None  # {"path": ..., "value": ...} written to revert
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    pid: int = field(default_factory=os.getpid)
    created: float = field(default_factory=time.time)


def state_file(base: Path | None = None) -> Path:
    return (base or STATE_DIR) / STATE_FILE_NAME


def _read(base: Path | None = None) -> list[dict]:
    path = state_file(base)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return list(data.get("entries", []))
    except (OSError, ValueError):
        return []


def _write(entries: list[dict], base: Path | None = None) -> None:
    path = state_file(base)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if entries:
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"entries": entries}, indent=2), encoding="utf-8")
            os.replace(tmp, path)
        elif path.exists():
            path.unlink()
    except OSError:
        pass  # a state file we cannot write must never block a run


def record(entry: StateEntry, base: Path | None = None) -> StateEntry:
    """Append `entry` (call BEFORE applying the side effect)."""
    entries = _read(base)
    entries.append(asdict(entry))
    _write(entries, base)
    return entry


def forget(entry_id: str, base: Path | None = None) -> None:
    """Remove an entry (call AFTER reverting the side effect)."""
    entries = [e for e in _read(base) if e.get("id") != entry_id]
    _write(entries, base)


def pending(base: Path | None = None) -> list[dict]:
    """Every recorded side effect not yet reverted -- this process's or a dead one's."""
    return _read(base)


def _pid_alive(pid: int) -> bool:
    if pid == os.getpid():
        return True
    try:
        import psutil

        return psutil.pid_exists(pid)
    except Exception:
        return False


def stale(base: Path | None = None) -> list[dict]:
    """Entries whose owning process no longer exists: leftovers from a crash."""
    return [e for e in _read(base) if not _pid_alive(int(e.get("pid", -1)))]


def _revert(entry: dict) -> bool:
    ok = True
    restore = entry.get("restore")
    if restore:
        try:
            with open(restore["path"], "w") as f:
                f.write(str(restore["value"]))
        except OSError:
            ok = False
    undo = entry.get("undo")
    if undo:
        try:
            res = subprocess.run(list(undo), capture_output=True, timeout=15, check=False)
            ok = ok and res.returncode == 0
        except (OSError, subprocess.SubprocessError):
            ok = False
    return ok


def cleanup_stale(base: Path | None = None) -> list[tuple[dict, bool]]:
    """Revert every stale entry; return (entry, reverted_ok). For `morph doctor`.

    Entries are forgotten whether or not the revert succeeded: a rule that is
    already gone (the box rebooted) fails to delete, and keeping it would make
    every future doctor run report the same ghost.
    """
    results = []
    for entry in stale(base):
        results.append((entry, _revert(entry)))
        forget(entry["id"], base)
    return results


def describe(base: Path | None = None) -> list[str]:
    """Human-readable lines for `morph doctor`."""
    lines = []
    for e in pending(base):
        owner = "this process" if e.get("pid") == os.getpid() else (
            f"pid {e.get('pid')}" + ("" if _pid_alive(int(e.get("pid", -1))) else " (dead)")
        )
        lines.append(f"{e.get('kind')}: {e.get('detail')} [{owner}]")
    return lines
