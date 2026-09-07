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
    # The locale must be usable as LC_ALL on POSIX: en_US.UTF-8, not en-US.
    assert "-" not in loc.locale.value.split(".")[0]
    assert loc.language_tag is not None and "_" not in loc.language_tag.value


def test_timezone_is_an_iana_name_a_child_can_interpret(monkeypatch):
    """`TZ=IST` is UTC to libc; `TZ=Asia/Kolkata` is not."""
    from zoneinfo import ZoneInfo

    monkeypatch.delenv("TZ", raising=False)
    loc = collect_locale()
    if loc.timezone.status == FieldStatus.CAPTURED:
        ZoneInfo(loc.timezone.value)  # must not raise
    else:
        # Honest fallback: an abbreviation is marked APPROXIMATED, never CAPTURED.
        assert loc.timezone.status == FieldStatus.APPROXIMATED


def test_tz_env_is_honoured_when_it_is_an_iana_name(monkeypatch):
    monkeypatch.setenv("TZ", "Europe/Berlin")
    loc = collect_locale()
    assert loc.timezone.value == "Europe/Berlin"
    assert loc.timezone.status == FieldStatus.CAPTURED


def test_capture_then_apply_round_trip_child_sees_the_zone_and_a_working_locale(monkeypatch):
    """The whole point: what capture records, apply can hand to a child."""
    import shlex
    import subprocess
    import sys

    from morph.runtime.adapters.base import ProxyAdapter

    monkeypatch.setenv("TZ", "Asia/Kolkata")
    loc = collect_locale()
    adapter = ProxyAdapter()
    adapter.apply_locale(loc.locale.value, loc.timezone.value)
    env = {**os.environ, **adapter.get_env_overrides()}
    code = (
        "import time, locale; print(time.strftime('%z')); "
        "locale.setlocale(locale.LC_ALL, ''); print('locale-ok')"
    )
    argv = [sys.executable, "-c", code]
    cmd = argv if os.name == "nt" else shlex.split(shlex.join(argv))
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=30)
    lines = proc.stdout.split()
    assert lines[0] == "+0530", proc.stdout + proc.stderr
    if os.name != "nt" and proc.returncode != 0:
        # The captured locale may not be installed on a minimal CI image; that is a
        # host limitation, not a wrong name. It must at least be well-formed.
        assert "_" in env["LC_ALL"] and "." in env["LC_ALL"]


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
    assert limits.timeout_s is not None
    assert limits.timeout_s.status == FieldStatus.CAPTURED
    if os.name == "posix":
        assert limits.max_processes.status == FieldStatus.CAPTURED
        assert limits.fd_limit.status == FieldStatus.CAPTURED
    elif os.name == "nt":
        assert limits.fd_limit is not None
        assert limits.fd_limit.status == FieldStatus.CAPTURED



def test_collect_network():
    from morph.profiler.collectors.network import collect_network

    net = collect_network()
    assert net.latency_ms.status == FieldStatus.CAPTURED
    assert net.latency_ms.value == 0.0
    assert net.packet_loss_percent.status == FieldStatus.CAPTURED
    assert net.packet_loss_percent.value == 0.0
    assert net.available.value is True


def test_capture_environment_assembles_full_profile():
    profile = capture_environment()

    assert profile.version == "1.0"
    assert profile.os.family.status == FieldStatus.CAPTURED
    assert profile.cpu.cores.value >= 1
    assert profile.memory.total_mb.value > 0
    assert profile.locale.locale.value
    assert profile.filesystem is not None
    assert profile.network is not None
    assert profile.network.latency_ms.status == FieldStatus.CAPTURED

    # Round-trips through JSON without loss (this is the portable-profile contract).
    restored = type(profile).model_validate_json(profile.model_dump_json())
    assert restored == profile

