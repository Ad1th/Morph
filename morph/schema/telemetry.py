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
