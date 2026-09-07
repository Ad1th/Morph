"""Memory collector: total physical RAM and swap."""

import psutil

from morph.schema.profile import FieldStatus, MemoryInfo, ProfileField


def collect_memory() -> MemoryInfo:
    vm = psutil.virtual_memory()
    total_mb = round(vm.total / (1024 * 1024))
    swap_mb = round(psutil.swap_memory().total / (1024 * 1024))
    pressure_pct = round(vm.percent, 1)
    return MemoryInfo(
        total_mb=ProfileField(value=total_mb, status=FieldStatus.CAPTURED),
        swap_mb=ProfileField(value=swap_mb, status=FieldStatus.CAPTURED),
        pressure_percent=ProfileField(value=pressure_pct, status=FieldStatus.CAPTURED),
    )

