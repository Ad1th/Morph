"""Live progress events emitted by the experiment engine.

The engine is normally fire-and-forget: `run_trials()` tallies pass/fail and
returns a `TrialBatch`. Passing an `on_event` callback into the engine makes
every step observable in real time -- for the TUI, the dashboard WebSocket, or
a plain progress bar.

Statistics stay honest. Per-trial events never carry a p-value; a Fisher
p-value is reported once, on the `comparison` / `verdict` event, computed over
the whole fixed-size batch. The one statistic that *may* be streamed live is
the e-value on `evidence` events: it is anytime-valid (see
:mod:`morph.engine.anytime`), so watching it and stopping when it crosses the
threshold does not inflate the false-positive rate.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

EventKind = Literal[
    "phase_start",      # a named phase begins: "isolation" | "interaction" | "threshold"
    "condition_start",  # trials for one condition begin
    "trial",            # one trial finished (pass/fail + timing only -- never a p-value)
    "condition_done",   # every trial for one condition finished; TrialBatch is ready
    "comparison",       # one treatment compared against baseline (carries the p-value)
    "evidence",         # running anytime-valid e-value for one treatment (sequential mode)
    "search_probe",     # threshold search evaluated one parameter value
    "verdict",          # final classification for the experiment
    "phase_done",
]


class TrialEvent(BaseModel):
    """One observable step of an experiment. Fields are populated per `kind`."""

    kind: EventKind

    # --- identity / progress ---
    condition: str = ""
    phase: str = ""
    trial_index: int | None = None   # 0-based, for kind="trial"
    total: int | None = None         # trial count for this condition

    # --- per-trial outcome (kind="trial") ---
    passed: bool | None = None
    duration_ms: float | None = None
    failures_so_far: int | None = None
    error_type: str | None = None
    stdout_tail: str | None = None
    stderr_tail: str | None = None

    # --- aggregate outcome (kind="condition_done") ---
    failures: int | None = None
    failure_rate: float | None = None

    # --- statistics (kind="comparison" / "verdict") -- never on a per-trial event ---
    p_value: float | None = None
    is_significant: bool | None = None
    effect_label: str | None = None
    classification: str | None = None
    strongest_condition: str | None = None

    # --- sequential evidence (kind="evidence") -- anytime-valid, safe to show live ---
    e_value: float | None = None
    evidence_threshold: float | None = None   # e-value needed to reject at this alpha
    pairs: int | None = None                  # matched baseline/treatment pairs so far
    decisive: bool | None = None

    # --- threshold search (kind="search_probe" / phase="threshold") ---
    param_value: float | None = None
    safe_value: float | None = None
    failure_value: float | None = None
    boundary_estimate: float | None = None

    # --- escape hatch ---
    extra: dict[str, Any] = Field(default_factory=dict)
