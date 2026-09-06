"""Threshold checker: bounds-checks a requested EnvironmentProfile and enforces
the cross-field rules from docs/ui-spec.md section 5.

Per ui-spec.md section 5: "block or warn, never silently clamp without
telling the user" -- so every issue here is reported, never auto-corrected.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from morph.profiler.capture import capture_environment
from morph.runtime.adapters.base import BaseAdapter
from morph.runtime.controller import get_default_adapter
from morph.schema.parameters import PARAMETER_CATALOG
from morph.schema.profile import EnvironmentProfile, FieldStatus

Severity = Literal["block", "warn"]


class ValidationIssue(BaseModel):
    field: str
    severity: Severity
    message: str


class ValidationResult(BaseModel):
    issues: list[ValidationIssue] = []

    @property
    def is_valid(self) -> bool:
        return not any(issue.severity == "block" for issue in self.issues)


def _resolve(profile: EnvironmentProfile, field_path: str):
    """Walks a dotted field_path (e.g. "network.bandwidth_mbps") and returns
    the ProfileField at the end, or None if any hop along the way is absent."""
    obj = profile
    for part in field_path.split("."):
        obj = getattr(obj, part, None)
        if obj is None:
            return None
    return obj


def check_thresholds(profile: EnvironmentProfile) -> list[ValidationIssue]:
    """Bounds-checks every catalog parameter present in `profile` against its
    metadata min/max (ui-spec.md sections 2-3)."""
    issues: list[ValidationIssue] = []
    for meta in PARAMETER_CATALOG.values():
        field = _resolve(profile, meta.field_path)
        if field is None or not isinstance(field.value, (int, float)):
            continue
        value = field.value
        if meta.min is not None and value < meta.min:
            issues.append(ValidationIssue(
                field=meta.field_path, severity="block",
                message=f"{meta.name} ({value} {meta.unit}) is below the minimum of {meta.min} {meta.unit}",
            ))
        if meta.max is not None and value > meta.max:
            issues.append(ValidationIssue(
                field=meta.field_path, severity="block",
                message=f"{meta.name} ({value} {meta.unit}) exceeds the maximum of {meta.max} {meta.unit}",
            ))
    return issues


def check_cross_field_rules(profile: EnvironmentProfile) -> list[ValidationIssue]:
    """ui-spec.md section 5 rules relating two fields to each other:
    jitter <= latency, and CPU quota <= cores * 100%."""
    issues: list[ValidationIssue] = []

    latency = _resolve(profile, "network.latency_ms")
    jitter = _resolve(profile, "network.jitter_ms")
    if latency and jitter and isinstance(jitter.value, (int, float)) and jitter.value > (latency.value or 0):
        issues.append(ValidationIssue(
            field="network.jitter_ms", severity="block",
            message=f"jitter ({jitter.value} ms) must not exceed latency ({latency.value} ms)",
        ))

    cores = _resolve(profile, "cpu.cores")
    quota = _resolve(profile, "cpu.quota_percent")
    if cores and quota and isinstance(quota.value, (int, float)):
        ceiling = cores.value * 100
        if quota.value > ceiling:
            issues.append(ValidationIssue(
                field="cpu.quota_percent", severity="block",
                message=f"CPU quota ({quota.value}%) exceeds {cores.value} cores x 100% = {ceiling}%",
            ))

    return issues


def check_worker_required(
    profile: EnvironmentProfile, host: EnvironmentProfile | None = None
) -> list[ValidationIssue]:
    """Flags parameters that exceed host capability (ui-spec.md section 5:
    "RAM / cores / disk space > host capability -> run target auto-switches
    to worker"). Disk space isn't modeled in EnvironmentProfile yet, so only
    CPU cores and RAM are checked here."""
    host = host or capture_environment()
    issues: list[ValidationIssue] = []

    requested_cores = _resolve(profile, "cpu.cores")
    host_cores = _resolve(host, "cpu.logical_processors")
    if requested_cores and host_cores and requested_cores.value > host_cores.value:
        issues.append(ValidationIssue(
            field="cpu.cores", severity="warn",
            message=f"needs a worker for: CPU cores {requested_cores.value} (host has {host_cores.value})",
        ))

    requested_ram = _resolve(profile, "memory.total_mb")
    host_ram = _resolve(host, "memory.total_mb")
    if requested_ram and host_ram and requested_ram.value > host_ram.value:
        issues.append(ValidationIssue(
            field="memory.total_mb", severity="warn",
            message=f"needs a worker for: RAM {requested_ram.value} MiB (host has {host_ram.value} MiB)",
        ))

    return issues


def check_platform_restrictions(
    profile: EnvironmentProfile, adapter: BaseAdapter
) -> list[ValidationIssue]:
    """Flags a field the current adapter cannot control at all (ui-spec.md
    section 5: "macOS host + CPU quota / memory limit / FS type / case
    sensitivity -> not controllable on macOS -- routes to a Linux worker").

    Only the memory-limit half of that rule is checkable today: BaseAdapter's
    capabilities() contract has no "filesystem" or "cpu_quota" key, so FS
    type/case-sensitivity/CPU-quota restrictions can't be represented without
    extending that contract too.
    """
    caps = adapter.capabilities()
    issues: list[ValidationIssue] = []

    memory_field = _resolve(profile, "memory.total_mb")
    if memory_field and memory_field.status == FieldStatus.REQUESTED and not caps.get("memory", True):
        issues.append(ValidationIssue(
            field="memory.total_mb", severity="warn",
            message="memory limit is not controllable on this host -- routes to a worker",
        ))

    return issues


def validate_profile(
    profile: EnvironmentProfile,
    host: EnvironmentProfile | None = None,
    adapter: BaseAdapter | None = None,
) -> ValidationResult:
    """Runs every check: bounds, cross-field rules, worker-routing, and
    platform restrictions."""
    issues = check_thresholds(profile)
    issues += check_cross_field_rules(profile)
    issues += check_worker_required(profile, host)
    issues += check_platform_restrictions(profile, adapter or get_default_adapter())
    return ValidationResult(issues=issues)
