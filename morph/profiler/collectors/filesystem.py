"""Filesystem collector: case sensitivity, filesystem type, and free space."""

import os
import shutil
import tempfile

import psutil

from morph.schema.profile import FieldStatus, FilesystemInfo, ProfileField


def _fstype_for_path(path: str) -> str | None:
    """Best-effort fstype (NTFS, ext4, apfs, ...) of the partition mounted at
    or above `path` -- the longest matching mountpoint wins."""
    path = os.path.abspath(path)
    best = None
    for part in psutil.disk_partitions(all=False):
        if path.startswith(part.mountpoint) and (best is None or len(part.mountpoint) > len(best.mountpoint)):
            best = part
    return best.fstype if best else None


def collect_filesystem() -> FilesystemInfo:
    with tempfile.TemporaryDirectory() as tmp:
        probe_path = os.path.join(tmp, "morph_case_probe")
        with open(probe_path, "w") as f:
            f.write("x")
        case_sensitive = not os.path.exists(probe_path.upper())

    cwd = os.getcwd()
    fstype = _fstype_for_path(cwd)
    free_mb = round(shutil.disk_usage(cwd).free / (1024 * 1024))

    return FilesystemInfo(
        case_sensitive=ProfileField(value=case_sensitive, status=FieldStatus.CAPTURED),
        filesystem_type=ProfileField(value=fstype, status=FieldStatus.CAPTURED) if fstype else None,
        disk_space_limit_mb=ProfileField(value=free_mb, status=FieldStatus.CAPTURED),
    )
