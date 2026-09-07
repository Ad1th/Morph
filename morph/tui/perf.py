"""Rolling performance history for the Monitor screen.

One :class:`Sample` per app run: the slider values it ran under, plus the run's
duration / CPU / memory and whether it passed. Feeds the sparklines and the
live boundary warnings.

Boundaries are direction-aware. For latency and loss *more* is worse, so the
learned boundary is the lowest failing value; for CPU cores and RAM *less* is
worse, so it is the highest failing value. ``direction="up"`` means "failures
appear as the value goes up".
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Literal

from morph.schema.telemetry import RunResult

Direction = Literal["up", "down"]


@dataclass(frozen=True)
class Sample:
    params: dict[str, float]
    duration_ms: float
    cpu_percent: float
    peak_mem_mb: float
    passed: bool
    run: RunResult | None = None


class PerfHistory:
    def __init__(self, capacity: int = 60) -> None:
        self._samples: deque[Sample] = deque(maxlen=capacity)

    def add(self, params: dict[str, float], run: RunResult) -> Sample:
        tele = run.telemetry
        sample = Sample(
            params=dict(params),
            duration_ms=float(run.duration_ms or 0.0),
            cpu_percent=float((tele.cpu_percent if tele else None) or 0.0),
            peak_mem_mb=float(run.peak_memory_mb or (tele.memory_rss_mb if tele else 0.0) or 0.0),
            passed=bool(run.passed),
            run=run,
        )
        self._samples.append(sample)
        return sample

    def __len__(self) -> int:
        return len(self._samples)

    @property
    def durations(self) -> list[float]:
        return [s.duration_ms for s in self._samples]

    @property
    def cpu(self) -> list[float]:
        return [s.cpu_percent for s in self._samples]

    @property
    def memory(self) -> list[float]:
        return [s.peak_mem_mb for s in self._samples]

    @property
    def outcomes(self) -> list[bool]:
        return [s.passed for s in self._samples]

    @property
    def latest(self) -> Sample | None:
        return self._samples[-1] if self._samples else None

    @property
    def last_failure(self) -> RunResult | None:
        for s in reversed(self._samples):
            if not s.passed and s.run is not None:
                return s.run
        return None

    def _values(self, param: str, *, passed: bool) -> list[float]:
        return [
            s.params[param]
            for s in self._samples
            if s.passed is passed and s.params.get(param) is not None
        ]

    def first_failure_value(self, param: str, direction: Direction = "up") -> float | None:
        """The failing value of ``param`` nearest the safe side: the lowest
        failing value when more is worse, the highest when less is worse."""
        fails = self._values(param, passed=False)
        if not fails:
            return None
        return min(fails) if direction == "up" else max(fails)

    def last_pass_value(self, param: str, direction: Direction = "up") -> float | None:
        """The passing value of ``param`` nearest the failing side."""
        passes = self._values(param, passed=True)
        if not passes:
            return None
        return max(passes) if direction == "up" else min(passes)

    def implicates(self, param: str, direction: Direction = "up") -> float | None:
        """A boundary for ``param`` only if the runs actually blame it: some run
        passed strictly on the safe side of it, and nothing on the failing side
        (or at it) passed. Rejects params that just happened to be set during a
        failure caused by another.
        """
        boundary = self.first_failure_value(param, direction)
        if boundary is None:
            return None
        passes = self._values(param, passed=True)
        if not passes:
            return None
        if direction == "up":
            safe_side = any(v < boundary for v in passes)
            leak = any(v >= boundary for v in passes)
        else:
            safe_side = any(v > boundary for v in passes)
            leak = any(v <= boundary for v in passes)
        if not safe_side or leak:
            return None
        return boundary

    @staticmethod
    def near_boundary(value: float, boundary: float, direction: Direction = "up") -> str | None:
        """``"past"`` / ``"approaching"`` / ``None`` for ``value`` against ``boundary``."""
        if direction == "up":
            if value >= boundary:
                return "past"
            return "approaching" if value >= boundary * 0.9 else None
        if value <= boundary:
            return "past"
        return "approaching" if value <= boundary * 1.1 else None
