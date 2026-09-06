"""Rolling performance history for the Monitor screen.

One :class:`Sample` per app run: the slider values it ran under, plus the run's
duration / CPU / memory and whether it passed. Feeds the sparklines and the
live threshold warnings.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from morph.schema.telemetry import RunResult


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

    def add_synthetic(self, params: dict[str, float], *, duration_ms: float,
                      cpu_percent: float, peak_mem_mb: float, passed: bool) -> Sample:
        sample = Sample(dict(params), duration_ms, cpu_percent, peak_mem_mb, passed, None)
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

    def first_failure_value(self, param: str) -> float | None:
        """Lowest value of ``param`` at which a run failed so far (a learned boundary)."""
        vals = [s.params.get(param) for s in self._samples if not s.passed and param in s.params]
        vals = [v for v in vals if v is not None]
        return min(vals) if vals else None

    def last_pass_value(self, param: str) -> float | None:
        """Highest value of ``param`` at which a run still passed."""
        vals = [s.params.get(param) for s in self._samples if s.passed and param in s.params]
        vals = [v for v in vals if v is not None]
        return max(vals) if vals else None
