"""Memory collector: total physical RAM."""

import psutil

from morph.schema.profile import FieldStatus, MemoryInfo, ProfileField


def collect_memory() -> MemoryInfo:
    total_mb = round(psutil.virtual_memory().total / (1024 * 1024))
    return MemoryInfo(total_mb=ProfileField(value=total_mb, status=FieldStatus.CAPTURED))
