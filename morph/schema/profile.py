from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class FieldStatus(str, Enum):
    CAPTURED = "captured"         # Measured from a real machine
    REQUESTED = "requested"       # Defined manually by the developer
    REPRODUCED = "reproduced"     # Successfully applied on the test machine
    APPROXIMATED = "approximated" # Best-effort (e.g. CPU throttled but not identical)
    UNAVAILABLE = "unavailable"   # Cannot be reproduced locally


class ProfileField(BaseModel):
    value: Any
    status: FieldStatus = FieldStatus.REQUESTED


class OSInfo(BaseModel):
    family: ProfileField          # "windows" | "darwin" | "linux"
    version: ProfileField         # "11", "14.5", "22.04"


class CPUInfo(BaseModel):
    architecture: ProfileField    # "x86_64" | "arm64"
    cores: ProfileField           # Physical core count
    logical_processors: ProfileField
    clock_mhz: Optional[ProfileField] = None


class MemoryInfo(BaseModel):
    total_mb: ProfileField


class LocaleInfo(BaseModel):
    locale: ProfileField          # "en-IN", "en-US", etc.
    timezone: ProfileField        # "Asia/Kolkata", "UTC", etc.


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
    network: NetworkInfo
