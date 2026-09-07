"""Tests for morph.profiler: each collector and the capture orchestrator."""

import os

from morph.profiler.capture import capture_environment
from morph.profiler.collectors.cpu import collect_cpu
from morph.profiler.collectors.filesystem import collect_filesystem
from morph.profiler.collectors.locale_info import collect_locale
from morph.profiler.collectors.memory import collect_memory
from morph.profiler.collectors.os_info import collect_os
from morph.profiler.collectors.process_limits import collect_process_limits
from morph.schema.profile import FieldStatus


def test_collect_cpu():
    cpu = collect_cpu()
    assert cpu.architecture.status == FieldStatus.CAPTURED
    assert cpu.cores.value >= 1
    assert cpu.logical_processors.value >= cpu.cores.value


def test_collect_memory():
    memory = collect_memory()
    assert memory.total_mb.status == FieldStatus.CAPTURED
    assert memory.total_mb.value > 0
    assert memory.swap_mb.status == FieldStatus.CAPTURED
    assert memory.swap_mb.value >= 0


def test_collect_os():
    os_info = collect_os()
    assert os_info.family.value in ("windows", "darwin", "linux")
    assert os_info.family.status == FieldStatus.CAPTURED
    assert os_info.kernel_version.status == FieldStatus.CAPTURED
    assert os_info.kernel_version.value


def test_collect_locale():
    loc = collect_locale()
    assert loc.locale.status == FieldStatus.CAPTURED
    assert loc.timezone.value


def test_collect_filesystem():
    fs = collect_filesystem()
    assert fs.case_sensitive.status == FieldStatus.CAPTURED
    assert isinstance(fs.case_sensitive.value, bool)
    # fstype detection is best-effort by design: psutil.disk_partitions can
    # miss the mount, and the collector then leaves the field unset rather than
    # inventing one. Check the value only when detection actually succeeded.
    if fs.filesystem_type is not None:
        assert fs.filesystem_type.status == FieldStatus.CAPTURED
        assert fs.filesystem_type.value
    assert fs.disk_space_limit_mb.value > 0


def test_collect_process_limits_posix_reports_real_ulimits():
    limits = collect_process_limits()
    if os.name == "posix":
        assert limits.max_processes.status == FieldStatus.CAPTURED
        assert limits.fd_limit.status == FieldStatus.CAPTURED
    else:
        # No pywin32 dependency: honestly unset rather than a fabricated number.
        assert limits.max_processes is None
        assert limits.fd_limit is None


def test_capture_environment_assembles_full_profile():
    profile = capture_environment()

    assert profile.version == "1.0"
    assert profile.os.family.status == FieldStatus.CAPTURED
    assert profile.cpu.cores.value >= 1
    assert profile.memory.total_mb.value > 0
    assert profile.locale.locale.value
    assert profile.filesystem is not None

    # Round-trips through JSON without loss (this is the portable-profile contract).
    restored = type(profile).model_validate_json(profile.model_dump_json())
    assert restored == profile
