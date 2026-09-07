"""Shared pytest plumbing for the demo-app self-checks.

Two tiers of test live under ``apps/``:

* the **contract tier** (default): baseline passes, the condition fails at
  least once, exit codes and the JSON line are right. A handful of subprocess
  runs per app; blocking in CI.
* the **statistical tier** (``@pytest.mark.slow``): the acceptance rates from
  ``docs/faultyapps.md`` section 7, measured over enough trials for a binomial
  bound to mean something. Advisory in CI (``pytest apps -m slow``).

Markers are registered in ``pyproject.toml`` (``--strict-markers``), not here.
"""

from __future__ import annotations

import json
import locale
import os
import platform
import subprocess
import sys
from math import comb

import pytest

# Environment the developer's shell may leak into a fixture. Every helper strips
# these so a German LANG or a Sao Paulo TZ on the dev box does not turn a
# baseline into a treatment.
_LEAKY_VARS = (
    "LC_ALL", "LC_NUMERIC", "LANG", "TZ",
    "MORPH_NET_LATENCY_MS", "MORPH_NET_PACKET_LOSS_PCT", "MORPH_NET_BANDWIDTH_KBPS",
    "MORPH_SEED", "MORPH_LATENCY_MS", "MORPH_PACKET_LOSS",
)

IS_LINUX = platform.system() == "Linux"
IS_ROOT = os.name != "nt" and hasattr(os, "geteuid") and os.geteuid() == 0


def run_app(
    name: str,
    *args: str,
    env: dict[str, str] | None = None,
    fixed: bool = False,
    timeout: float = 60.0,
) -> tuple[int, dict, str]:
    """Run ``python -m apps.<name> test [args] [--fixed]`` in a clean environment.

    Returns ``(exit_code, json_payload, stderr)``. The payload is the last
    stdout line, which the interface contract says is the JSON result object.
    """
    clean = {k: v for k, v in os.environ.items() if k not in _LEAKY_VARS}
    clean.update(env or {})
    cmd = [sys.executable, "-m", f"apps.{name}", "test", *args]
    if fixed:
        cmd.append("--fixed")
    proc = subprocess.run(cmd, capture_output=True, text=True, env=clean, timeout=timeout)
    lines = proc.stdout.strip().splitlines()
    payload = json.loads(lines[-1]) if lines else {}
    return proc.returncode, payload, proc.stderr


def failure_rate(name: str, trials: int, **kw) -> tuple[int, int]:
    """``(failures, invalid)`` over ``trials`` runs of ``run_app``.

    Exit 1 is a failure, exit 0 a pass; exit 2 is an *invalid* trial and is
    counted separately, never as a failure (the engine discards those too).
    """
    failures = invalid = 0
    for _ in range(trials):
        code, _payload, _err = run_app(name, **kw)
        if code == 1:
            failures += 1
        elif code == 2:
            invalid += 1
        else:
            assert code == 0, f"unexpected exit code {code}"
    return failures, invalid


def binomial_tail(n: int, k: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p)."""
    return sum(comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k, n + 1))


def max_failures(n: int, true_rate: float, confidence: float = 0.99) -> int:
    """Largest failure count that is still consistent with ``true_rate``.

    The smallest ``k`` such that ``P(X > k) <= 1 - confidence`` under
    Binomial(n, true_rate). A test asserting ``failures <= max_failures(...)``
    rejects a healthy fixture at most ``1 - confidence`` of the time, which is
    what "never assert zero failures over eight trials" means in practice:
    ``max_failures(8, 0.05)`` is 2, not 0.
    """
    for k in range(n + 1):
        if binomial_tail(n, k + 1, true_rate) <= 1 - confidence:
            return k
    return n


def min_failures(n: int, true_rate: float, confidence: float = 0.99) -> int:
    """Smallest failure count consistent with a fixture that fails at ``true_rate``.

    Mirror of :func:`max_failures` for the "must fail" legs: the largest ``k``
    such that ``P(X < k) <= 1 - confidence``.
    """
    for k in range(n, -1, -1):
        below = 1.0 - binomial_tail(n, k, true_rate)
        if below <= 1 - confidence:
            return k
    return 0


def locale_available(name: str, decimal_point: str) -> bool:
    """True when ``name`` can be applied here and produces ``decimal_point``."""
    saved = locale.setlocale(locale.LC_ALL)
    try:
        for candidate in (name, f"{name}.UTF-8", f"{name}.utf8"):
            try:
                locale.setlocale(locale.LC_ALL, candidate)
            except locale.Error:
                continue
            return locale.localeconv()["decimal_point"] == decimal_point
        return False
    finally:
        locale.setlocale(locale.LC_ALL, saved)


def pytest_collection_modifyitems(config, items):
    """Skip platform-bound tests instead of failing them.

    ``needs_linux`` / ``needs_root`` are registered in ``pyproject.toml``; this
    turns them into skips on hosts that cannot satisfy them (macOS, Windows,
    unprivileged CI runners) so the corpus job can be blocking everywhere.
    """
    skip_linux = pytest.mark.skip(reason="needs a Linux host (cgroups / tc netem)")
    skip_root = pytest.mark.skip(reason="needs root")
    for item in items:
        if "needs_linux" in item.keywords and not IS_LINUX:
            item.add_marker(skip_linux)
        if "needs_root" in item.keywords and not IS_ROOT:
            item.add_marker(skip_root)
