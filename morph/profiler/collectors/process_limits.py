"""Process limits collector: max processes and open-file-descriptor ulimits.

POSIX only (stdlib `resource` module). Windows has no direct equivalent
without a `pywin32` dependency this project doesn't have, so these stay
unset there: an honest gap rather than a fabricated number.
"""

import os

from morph.schema.profile import FieldStatus, ProcessInfo, ProfileField


def collect_process_limits() -> ProcessInfo:
    if os.name != "posix":
        return ProcessInfo()

    import resource

    max_processes = resource.getrlimit(resource.RLIMIT_NPROC)[0]
    fd_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[0]

    return ProcessInfo(
        max_processes=ProfileField(value=max_processes, status=FieldStatus.CAPTURED),
        fd_limit=ProfileField(value=fd_limit, status=FieldStatus.CAPTURED),
    )
