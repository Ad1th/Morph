"""EnvironmentProfile: the portable JSON description of a machine's conditions."""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel


class FieldStatus(str, Enum):
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


class CPUInfo(BaseModel):
    architecture: ProfileField
    cores: ProfileField
    logical_processors: ProfileField
    clock_mhz: ProfileField


class MemoryInfo(BaseModel):
    total_mb: ProfileField


class LocaleInfo(BaseModel):
    locale: ProfileField
    timezone: ProfileField


class FilesystemInfo(BaseModel):
    case_sensitive: ProfileField


class NetworkInfo(BaseModel):
    latency_ms: ProfileField
    packet_loss_percent: ProfileField
    bandwidth_mbps: Optional[ProfileField] = None


class EnvironmentProfile(BaseModel):
    version: str = "1.0"
    os: OSInfo
    cpu: CPUInfo
    memory: MemoryInfo
    locale: LocaleInfo
    filesystem: Optional[FilesystemInfo] = None
    network: Optional[NetworkInfo] = None
