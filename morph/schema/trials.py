"""TrialBatch: the tally of one condition's repeated runs.

Lives in its own module so both :mod:`morph.schema.comparison` (which embeds
the batches a comparison was computed from) and :mod:`morph.schema.experiment`
can import it without a cycle.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, computed_field

from morph.schema.telemetry import RunResult


class TrialBatch(BaseModel):
    condition_label: str
    profile_overrides: dict[str, Any] = Field(default_factory=dict)
    total_runs: int
    failures: int
    run_results: list[RunResult] = Field(default_factory=list)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def failure_rate(self) -> float:
        """Always ``failures / total_runs`` (0.0 for an empty batch); it cannot be
        set to a value that disagrees with the counts."""
        return self.failures / self.total_runs if self.total_runs else 0.0
