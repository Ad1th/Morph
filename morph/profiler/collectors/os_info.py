"""OS collector: family and version, normalized across platforms."""

import platform

import distro

from morph.schema.profile import FieldStatus, OSInfo, ProfileField

_FAMILY_MAP = {
    "Windows": "windows",
    "Darwin": "darwin",
    "Linux": "linux",
}


def _version(system: str) -> str:
    if system == "Darwin":
        return platform.mac_ver()[0]
    if system == "Linux":
        # platform.release() is the kernel version (e.g. "6.8.0"), not the
        # distribution version a target profile actually cares about
        # (e.g. Ubuntu "22.04"). distro reads /etc/os-release for that.
        version = distro.version()
        return version or platform.release()
    return platform.release()


def collect_os() -> OSInfo:
    system = platform.system()
    family = _FAMILY_MAP.get(system, system.lower())

    return OSInfo(
        family=ProfileField(value=family, status=FieldStatus.CAPTURED),
        version=ProfileField(value=_version(system), status=FieldStatus.CAPTURED),
    )
