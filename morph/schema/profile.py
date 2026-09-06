"""EnvironmentProfile: the portable JSON description of a machine's conditions."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class FieldStatus(StrEnum):
    CAPTURED = "captured"
    REQUESTED = "requested"
    REPRODUCED = "reproduced"
    APPROXIMATED = "approximated"
    UNAVAILABLE = "unavailable"


class ProfileField(BaseModel):
    value: Any
    status: FieldStatus = FieldStatus.REQUESTED


class OSInfo(BaseModel):
    family: ProfileField
    version: ProfileField
    kernel_version: ProfileField | None = None


class CPUInfo(BaseModel):
    architecture: ProfileField
    cores: ProfileField
    logical_processors: ProfileField
    clock_mhz: ProfileField | None = None
    quota_percent: ProfileField | None = None


class MemoryInfo(BaseModel):
    total_mb: ProfileField
    swap_mb: ProfileField | None = None
    pressure_percent: ProfileField | None = None


class LocaleInfo(BaseModel):
    locale: ProfileField
    timezone: ProfileField


class FilesystemInfo(BaseModel):
    case_sensitive: ProfileField
    filesystem_type: ProfileField | None = None
    read_only: ProfileField | None = None
    disk_space_limit_mb: ProfileField | None = None
    disk_read_latency_ms: ProfileField | None = None
    disk_write_latency_ms: ProfileField | None = None


class NetworkInfo(BaseModel):
    latency_ms: ProfileField
    packet_loss_percent: ProfileField
    bandwidth_mbps: ProfileField | None = None
    jitter_ms: ProfileField | None = None
    available: ProfileField | None = None
    connection_type: ProfileField | None = None


class ProcessInfo(BaseModel):
    timeout_s: ProfileField | None = None
    max_processes: ProfileField | None = None
    thread_limit: ProfileField | None = None
    fd_limit: ProfileField | None = None


class EnvironmentProfile(BaseModel):
    version: str = "1.0"
    os: OSInfo
    cpu: CPUInfo
    memory: MemoryInfo
    locale: LocaleInfo
    filesystem: FilesystemInfo | None = None
    network: NetworkInfo | None = None
    process: ProcessInfo | None = None
    env_vars: dict[str, str] = {}
