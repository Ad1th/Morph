"""RunResult: structured outcome of a single application run."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


def _default_run_id() -> str:
    return f"run-{uuid.uuid4().hex[:12]}"


def _default_timestamp() -> str:
    return datetime.now(UTC).isoformat()


class TelemetryData(BaseModel):
    cpu_percent: float | None = None
    memory_rss_mb: float | None = None
    network_rx_bytes: int | None = None
    network_tx_bytes: int | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class FidelityEntry(BaseModel):
    """How faithfully one profile field was applied for this run.

    `status` is a FieldStatus value: "reproduced" (a native mechanism enforced
    it), "approximated" (applied, but only partly or only for cooperating
    targets), or "unavailable" (nothing on this host enforces it).
    """

    status: str
    mechanism: str = ""  # "tc netem on lo", "user-space proxy", "env hint", "none"
    detail: str = ""


class RunResult(BaseModel):
    run_id: str = Field(default_factory=_default_run_id)
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0
    peak_memory_mb: float | None = None
    passed: bool
    error_type: str | None = None
    error_message: str | None = None
    timestamp: str = Field(default_factory=_default_timestamp)
    telemetry: TelemetryData | None = None

    # --- invalid-trial convention -------------------------------------------
    # A trial that could not even attempt the test (exit 2 by the apps/
    # convention, exit 126/127, a command that failed to launch, an rlimit the
    # host refused) is NOT an application failure. `passed` stays False, but
    # `invalid=True` tells the engine to skip or retry it rather than count it
    # as evidence about the environment.
    invalid: bool = False
    invalid_reason: str | None = None

    # --- provenance ---------------------------------------------------------
    # Enough to reproduce and attribute the run: which code, on what kind of
    # machine, under which profile, with which loss pattern.
    command: str | None = None
    seed: int | None = None
    morph_version: str | None = None
    host_fingerprint: str | None = None  # sha256(os|arch|cores|ram)[:16]
    profile_hash: str | None = None  # sha256 of the canonical profile JSON
    adapter: str | None = None  # class name of the adapter that applied conditions
    fidelity: dict[str, FidelityEntry] = Field(default_factory=dict)
