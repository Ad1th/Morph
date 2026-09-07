"""Process limits collector: max processes, timeout, and open-file-descriptor limits."""

import os

from morph.schema.profile import FieldStatus, ProcessInfo, ProfileField


def collect_process_limits() -> ProcessInfo:
    max_processes = None
    fd_limit = None

    if os.name == "posix":
        import resource

        max_processes = resource.getrlimit(resource.RLIMIT_NPROC)[0]
        fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]
    elif os.name == "nt":
        try:
            import ctypes

            fd_limit = int(ctypes.cdll.msvcrt._getmaxstdio())
        except Exception:
            pass

    return ProcessInfo(
        timeout_s=ProfileField(value=0.0, status=FieldStatus.CAPTURED),
        max_processes=ProfileField(value=max_processes, status=FieldStatus.CAPTURED)
        if max_processes is not None
        else None,
        fd_limit=ProfileField(value=fd_limit, status=FieldStatus.CAPTURED) if fd_limit is not None else None,
    )
