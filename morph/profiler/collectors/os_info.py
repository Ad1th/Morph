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


def _kernel_version(system: str) -> str:
    # platform.uname().release on Windows is just the marketing release
    # ("10", "11"), not a build number; platform.version() gives the real
    # NT build ("10.0.26200"). Linux/Darwin's uname().release is already
    # the actual kernel version (e.g. "6.8.0", "23.4.0").
    if system == "Windows":
        return platform.version()
    return platform.uname().release


def collect_os() -> OSInfo:
    system = platform.system()
    family = _FAMILY_MAP.get(system, system.lower())

    return OSInfo(
        family=ProfileField(value=family, status=FieldStatus.CAPTURED),
        version=ProfileField(value=_version(system), status=FieldStatus.CAPTURED),
        kernel_version=ProfileField(value=_kernel_version(system), status=FieldStatus.CAPTURED),
    )
