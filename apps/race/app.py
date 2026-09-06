"""Failure C: a race condition EXPOSED by CPU throttling.

This is the environment-*exposed* fixture, and the distinction is the whole
point of it (PRD section 18, Design Spec section 29):

    The bug is in the application, not the environment. An unlocked
    check-then-act on a shared cache is wrong on any machine. A calm CPU just
    hides it -- each thread finishes the window before it can be preempted.
    Constrain the CPU and the same code starts losing the race constantly.

    Morph must therefore report "CPU constraint strongly increases the
    probability of this failure", NOT "CPU caused this bug".

Mechanism. N threads meet at a barrier, then all run an unlocked
check-then-act: test whether a cache key exists, spin briefly, then populate
it. Exactly one thread should ever do the populate. Under a cgroup CPU quota,
the process is frozen when its budget for the period is exhausted; if that
freeze lands between one thread's check and its act, another thread races in.

    Env knob Morph turns : CPU quota, cgroup cpu.max  (NOT core pinning -- see below)
    Baseline (full CPU)  : double-call rate ~0.00 -> PASS
    Fails when           : quota throttled to <= ~20% of one CPU -> rate 30-60%
    Fix (one line)       : MORPH_C_USE_LOCK / --fixed, wrapping check-then-act in a Lock
    Classification       : environment-EXPOSED

Why a barrier. Thread creation on Windows costs ~50us, far longer than the
check-act window itself, so sequentially started threads never overlap and the
race never fires at all -- measured 0/300 without one. The barrier makes the
threads arrive together, which gives the race a real but still narrow window.
The bug being demonstrated is genuine; the barrier only ensures the threads
actually contend.

Why not taskset. Core pinning is a different mechanism from quota throttling
and can *reduce* this race by removing true parallelism (faultyapps.md
section 10). Use cpu.max.

Tuning knobs:
    MORPH_C_ITERS            iterations per run (default 300)
    MORPH_C_THREADS          threads contending per iteration (default 8)
    MORPH_C_SPIN             width of the race window, in loop steps (default 200)
    MORPH_C_MAX_RATE         double-call rate above which the run FAILS (default 0.05)
    MORPH_C_SWITCH_INTERVAL  verification-only throttling stand-in, see below
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time

ITERS = int(os.getenv("MORPH_C_ITERS", "300"))
THREADS = int(os.getenv("MORPH_C_THREADS", "8"))
SPIN = int(os.getenv("MORPH_C_SPIN", "200"))
MAX_RATE = float(os.getenv("MORPH_C_MAX_RATE", "0.05"))

# Verification-only stand-in for CPU throttling, for machines with no cgroups
# (Windows, macOS). Lowering the interpreter's thread switch interval makes
# preemption frequent, which raises the chance a switch lands inside the race
# window -- the same *direction* of effect as a cgroup freeze, so the fixture
# can be self-checked anywhere.
#
# It is NOT equivalent to real throttling and must never stand in for it in the
# demo: a cgroup quota freezes the whole process at budget exhaustion, while
# this only changes how often the GIL is handed between threads. The real knob
# is cpu.max on Linux/the Pi.
_SWITCH_INTERVAL = os.getenv("MORPH_C_SWITCH_INTERVAL")


def _run_once(use_lock: bool, lock: threading.Lock) -> int:
    """One contended check-then-act. Returns how many threads did the populate
    (correct answer: exactly 1)."""
    cache: dict[str, int] = {}
    calls = [0]
    barrier = threading.Barrier(THREADS)

    def get() -> None:
        barrier.wait()
        if use_lock:
            lock.acquire()
        try:
            if "k" not in cache:          # check
                for _ in range(SPIN):     # the race window
                    pass
                calls[0] += 1             # act
                cache["k"] = calls[0]
        finally:
            if use_lock:
                lock.release()

    threads = [threading.Thread(target=get) for _ in range(THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return calls[0]


def main(machine_mode: bool, fixed: bool) -> int:
    if _SWITCH_INTERVAL:
        sys.setswitchinterval(float(_SWITCH_INTERVAL))

    lock = threading.Lock()
    t0 = time.monotonic()
    doubles = sum(1 for _ in range(ITERS) if _run_once(fixed, lock) != 1)
    duration_ms = (time.monotonic() - t0) * 1000

    rate = doubles / ITERS
    failed = rate > MAX_RATE
    outcome = {
        "result": "fail" if failed else "pass",
        "signal": "RaceDetected" if failed else None,
        "duration_ms": round(duration_ms),
        "detail": (f"{doubles}/{ITERS} iterations double-called "
                   f"(rate {rate:.3f}, threshold {MAX_RATE})"),
        "rate": rate,
    }

    if machine_mode:
        print(json.dumps(outcome))
    else:
        print(f"[race] {'FAIL' if failed else 'PASS'} in {outcome['duration_ms']}ms")
        print(f"  {outcome['detail']}")
        if fixed:
            print("  (--fixed: check-then-act is lock-protected)")

    return 1 if failed else 0
