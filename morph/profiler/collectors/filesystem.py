"""Filesystem collector: detects case sensitivity by probing a temp directory."""

import os
import tempfile

from morph.schema.profile import FieldStatus, FilesystemInfo, ProfileField


def collect_filesystem() -> FilesystemInfo:
    with tempfile.TemporaryDirectory() as tmp:
        probe_path = os.path.join(tmp, "morph_case_probe")
        with open(probe_path, "w") as f:
            f.write("x")
        case_sensitive = not os.path.exists(probe_path.upper())

    return FilesystemInfo(
        case_sensitive=ProfileField(value=case_sensitive, status=FieldStatus.CAPTURED)
    )
