"""CPU collector: architecture, core counts, clock speed."""

import platform

import psutil

from morph.schema.profile import CPUInfo, FieldStatus, ProfileField


def collect_cpu() -> CPUInfo:
    clock_mhz = None
    freq = psutil.cpu_freq()
    if freq is not None:
        clock_mhz = round(freq.max or freq.current)

    physical_cores = psutil.cpu_count(logical=False) or psutil.cpu_count()

    return CPUInfo(
        architecture=ProfileField(value=platform.machine(), status=FieldStatus.CAPTURED),
        cores=ProfileField(value=physical_cores, status=FieldStatus.CAPTURED),
        logical_processors=ProfileField(
            value=psutil.cpu_count(logical=True), status=FieldStatus.CAPTURED
        ),
        clock_mhz=ProfileField(value=clock_mhz, status=FieldStatus.CAPTURED),
        quota_percent=ProfileField(value=100.0, status=FieldStatus.CAPTURED),
    )

