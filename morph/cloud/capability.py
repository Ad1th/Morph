"""Can this host actually satisfy the profile, and if not, would a bigger one?

PRD section 10 is the rule this file exists to enforce:

    Requested: 16 GB RAM
    Local:      8 GB RAM
    Result:    NOT_REPRODUCIBLE_LOCALLY

Morph must never fake hardware equivalence. So before a run, compare what the
profile asks for against what this machine physically has, and separate two
different kinds of "cannot":

  * a shortfall a LARGER machine would fix (not enough RAM, not enough cores,
    the wrong OS or architecture) -- route the run to a worker that has it;
  * a limit no machine fixes (an adapter Morph simply does not implement) --
    that is reported honestly and stays reported honestly.

Only the first kind justifies reaching for the cloud.
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

from morph.schema.profile import EnvironmentProfile

# Memory totals disagree slightly between code paths: the profiler and this
# module both convert bytes to MB but round differently, so capturing a profile
# on this very host and assessing it reported a 1 MB shortfall and would have
# sent the run to the cloud for nothing. Anything within this margin counts as
# fitting -- the OS never hands a process all of physical RAM anyway.
MEMORY_TOLERANCE = 0.02

# Architectures that name the same machine.
_ARCH_ALIASES = {
    "x86_64": {"x86_64", "amd64", "x64"},
    "amd64": {"x86_64", "amd64", "x64"},
    "arm64": {"arm64", "aarch64"},
    "aarch64": {"arm64", "aarch64"},
}

# platform.system() spellings against EnvironmentProfile os.family values.
_OS_ALIASES = {
    "darwin": {"darwin", "macos", "mac", "osx"},
    "windows": {"windows", "win32", "win"},
    "linux": {"linux"},
}


@dataclass(frozen=True)
class Shortfall:
    """One way this host falls short of the profile."""

    field_path: str
    requested: object
    available: object
    detail: str

    def __str__(self) -> str:  # pragma: no cover - display only
        return f"{self.field_path}: requested {self.requested}, host has {self.available}"


@dataclass
class HostCapability:
    """What this machine can do, and where the profile exceeds it."""

    total_memory_mb: int
    logical_cores: int
    architecture: str
    os_family: str
    shortfalls: list[Shortfall] = field(default_factory=list)

    @property
    def reproducible_locally(self) -> bool:
        """True when nothing in the profile exceeds this machine."""
        return not self.shortfalls

    def summary(self) -> str:
        if self.reproducible_locally:
            return "profile fits this host"
        return "; ".join(str(s) for s in self.shortfalls)


def _host_memory_mb() -> int:
    try:
        import psutil

        return int(psutil.virtual_memory().total / (1024 * 1024))
    except Exception:
        # Without psutil we cannot prove a shortfall, and inventing one would
        # push runs to the cloud for no reason. Report an unbounded host and
        # let the memory check pass.
        return 1 << 30


def _same_arch(requested: str, actual: str) -> bool:
    r, a = requested.strip().lower(), actual.strip().lower()
    return r == a or a in _ARCH_ALIASES.get(r, {r})


def _same_os(requested: str, actual: str) -> bool:
    r, a = requested.strip().lower(), actual.strip().lower()
    return r == a or r in _OS_ALIASES.get(a, {a})


def assess_locally(profile: EnvironmentProfile) -> HostCapability:
    """Compare `profile` against this machine's physical resources.

    Only counts shortfalls a different machine could genuinely fix. Software
    conditions (locale, timezone, network shaping) are deliberately excluded:
    they are the adapters' business, and reconcile_profile_statuses already
    reports those honestly as APPROXIMATED or UNAVAILABLE.
    """
    cap = HostCapability(
        total_memory_mb=_host_memory_mb(),
        logical_cores=os.cpu_count() or 1,
        architecture=platform.machine(),
        os_family=platform.system().lower(),
    )

    # --- memory: the PRD's motivating case ---
    requested_mb = _as_int(profile.memory.total_mb.value if profile.memory else None)
    if requested_mb and requested_mb > cap.total_memory_mb * (1 + MEMORY_TOLERANCE):
        cap.shortfalls.append(
            Shortfall(
                "memory.total_mb",
                requested_mb,
                cap.total_memory_mb,
                "a host with less RAM cannot be made to behave like one with more",
            )
        )

    # --- CPU quota (cgroup cpu.max throttling) ---
    requested_quota = _as_float(
        profile.cpu.quota_percent.value if (profile.cpu and profile.cpu.quota_percent) else None
    )
    if requested_quota is not None and requested_quota < 100.0 and not _same_os("linux", cap.os_family):
        cap.shortfalls.append(
            Shortfall(
                "cpu.quota_percent",
                requested_quota,
                100.0,
                "CPU quota throttling needs cgroups, which only Linux has",
            )
        )

    # --- cores ---
    requested_cores = _as_int(profile.cpu.cores.value if profile.cpu else None)
    if requested_cores and requested_cores > cap.logical_cores:
        cap.shortfalls.append(
            Shortfall(
                "cpu.cores",
                requested_cores,
                cap.logical_cores,
                "cores can be taken away from a process, not added",
            )
        )

    # --- architecture ---
    requested_arch = _as_str(profile.cpu.architecture.value if profile.cpu else None)
    if requested_arch and not _same_arch(requested_arch, cap.architecture):
        cap.shortfalls.append(
            Shortfall(
                "cpu.architecture",
                requested_arch,
                cap.architecture,
                "a different instruction set needs a machine that has it",
            )
        )

    # --- OS family ---
    requested_os = _as_str(profile.os.family.value if profile.os else None)
    if requested_os and not _same_os(requested_os, cap.os_family):
        cap.shortfalls.append(
            Shortfall(
                "os.family",
                requested_os,
                cap.os_family,
                "Morph does not turn one OS into another (PRD section 5)",
            )
        )

    return cap


def _as_int(value: object) -> int | None:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_float(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _as_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
