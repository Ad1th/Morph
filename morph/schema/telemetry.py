from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class TelemetryData(BaseModel):
    cpu_percent: Optional[float] = None
    memory_rss_mb: Optional[float] = None
    network_rx_bytes: Optional[int] = None
    network_tx_bytes: Optional[int] = None
    extra: Dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: float
    peak_memory_mb: Optional[float] = None
    passed: bool                  # exit_code == 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: str
    telemetry: Optional[TelemetryData] = None
