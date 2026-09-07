"""Pydantic schemas for Differential Runtime Blame analysis."""

from __future__ import annotations

from pydantic import BaseModel


class BlameTrace(BaseModel):
    run_type: str  # "PASS" | "FAIL"
    parameter_val: str
    file: str | None = None
    line: int | None = None
    function: str | None = None
    operation: str | None = None
    status_or_exception: str | None = None
    duration_ms: float | None = None
    summary_line: str = ""


class DifferentialBlameResult(BaseModel):
    culpable_file: str | None = None
    culpable_line: int | None = None
    culpable_code: str | None = None
    pass_trace: BlameTrace | None = None
    fail_trace: BlameTrace | None = None
    divergence_summary: str = ""
    explanation: str = ""
    suggested_fix: str | None = None
