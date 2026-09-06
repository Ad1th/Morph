"""OS collector: family and version, normalized across platforms."""

import platform

from morph.schema.profile import FieldStatus, OSInfo, ProfileField

_FAMILY_MAP = {
    "Windows": "windows",
    "Darwin": "darwin",
    "Linux": "linux",
}


def collect_os() -> OSInfo:
    system = platform.system()
    family = _FAMILY_MAP.get(system, system.lower())
    version = platform.mac_ver()[0] if system == "Darwin" else platform.release()

    return OSInfo(
        family=ProfileField(value=family, status=FieldStatus.CAPTURED),
        version=ProfileField(value=version, status=FieldStatus.CAPTURED),
    )
