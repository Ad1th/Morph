"""OS adapters: honest capabilities, per-field fidelity, no side effects in unit tests."""

from __future__ import annotations

import os
import subprocess

import pytest

from morph.runtime import state
from morph.runtime.adapters import (
    LinuxAdapter,
    MacOSAdapter,
    WindowsAdapter,
)
from morph.runtime.adapters.base import to_posix_locale
from morph.schema.profile import FieldStatus


@pytest.fixture(autouse=True)
def _no_subprocess(monkeypatch):
    """conftest sets MORPH_NO_NATIVE; this proves it -- any tc/dnctl/sudo call fails the test."""

    def boom(*a, **k):  # pragma: no cover - reaching this is the failure
        raise AssertionError(f"adapter spawned a subprocess in a unit test: {a[0]!r}")

    monkeypatch.setattr(subprocess, "run", boom)


def test_macos_adapter_capabilities_and_locale():
    adapter = MacOSAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is False, "macOS has no cgroups: an env hint is not a capability"
    assert caps["memory"] is False
    assert caps["locale"] is True

    adapter.apply_locale("en_US.UTF-8", "America/New_York")
    adapter.apply_cpu(max_cores=2)
    adapter.apply_memory(limit_mb=1024)
    overrides = adapter.get_env_overrides()

    assert overrides["LC_ALL"] == "en_US.UTF-8"
    assert overrides["TZ"] == "America/New_York"
    assert overrides["MORPH_MAX_CORES"] == "2"
    assert overrides["MORPH_MEMORY_LIMIT_MB"] == "1024"

    fid = adapter.fidelity()
    assert fid["cpu.cores"].status == FieldStatus.UNAVAILABLE
    assert fid["memory.total_mb"].status == FieldStatus.UNAVAILABLE
    assert "MORPH_MEMORY_LIMIT_MB" in fid["memory.total_mb"].detail
    assert fid["locale.locale"].status == FieldStatus.REPRODUCED
    assert fid["locale.timezone"].status == FieldStatus.REPRODUCED

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}
    assert adapter.fidelity() == {}


def test_linux_adapter_capabilities_and_locale():
    adapter = LinuxAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is True
    assert caps["memory"] is True
    assert caps["locale"] is True

    adapter.apply_locale("fr_FR.UTF-8", "Europe/Paris")
    adapter.apply_cpu(max_cores=4)
    overrides = adapter.get_env_overrides()

    assert overrides["LC_ALL"] == "fr_FR.UTF-8"
    assert overrides["TZ"] == "Europe/Paris"
    assert overrides["MORPH_MAX_CORES"] == "4"
    assert adapter.fidelity()["cpu.cores"].status == FieldStatus.UNAVAILABLE

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


def test_windows_adapter_capabilities_and_locale():
    adapter = WindowsAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is False, "no Job Object wiring: an env hint is not a capability"
    assert caps["memory"] is False
    assert caps["locale"] is True

    adapter.apply_locale("ja_JP.UTF-8", "Asia/Tokyo")
    overrides = adapter.get_env_overrides()

    assert overrides["LC_ALL"] == "ja_JP.UTF-8"
    assert overrides["TZ"] == "Asia/Tokyo"
    # The MSVC CRT ignores LC_ALL/TZ: honest APPROXIMATED, not REPRODUCED.
    assert adapter.fidelity()["locale.locale"].status == FieldStatus.APPROXIMATED
    assert adapter.fidelity()["locale.timezone"].status == FieldStatus.APPROXIMATED

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


def test_cpu_quota_hint_on_windows_and_macos():
    # Neither has a wired-up native quota mechanism (needs pywin32 / no
    # cgroups) -- an honest env-var hint, reported UNAVAILABLE.
    for adapter in (WindowsAdapter(), MacOSAdapter()):
        adapter.apply_cpu(max_cores=2, quota_percent=150.0)
        assert adapter.get_env_overrides()["MORPH_CPU_QUOTA_PERCENT"] == "150.0"
        assert adapter.fidelity()["cpu.quota_percent"].status == FieldStatus.UNAVAILABLE
        adapter.cleanup()


def test_linux_cpu_quota_is_a_hint_without_an_opted_in_cgroup():
    """No MORPH_CGROUP_PATH -> nothing is written anywhere (root cgroup included)
    and the field is UNAVAILABLE with a hint on how to enable it."""
    adapter = LinuxAdapter()
    adapter.apply_cpu(max_cores=2, quota_percent=150.0)
    adapter.apply_memory(limit_mb=512)
    assert adapter.get_env_overrides()["MORPH_CPU_QUOTA_PERCENT"] == "150.0"
    fid = adapter.fidelity()
    assert fid["cpu.quota_percent"].status == FieldStatus.UNAVAILABLE
    assert "MORPH_CGROUP_PATH" in fid["cpu.quota_percent"].detail
    assert fid["memory.total_mb"].status == FieldStatus.UNAVAILABLE
    assert adapter.cgroup_path() is None
    assert state.pending() == []
    adapter.cleanup()


def test_linux_cgroup_writes_are_recorded_and_restored(monkeypatch, tmp_path):
    """With an opted-in cgroup dir, cpu.max/memory.max are written, recorded in
    the state file BEFORE the write, and restored on cleanup."""
    import morph.runtime.adapters.linux as linux_mod

    cg = tmp_path / "cg"
    cg.mkdir()
    (cg / "cpu.max").write_text("max 100000")
    (cg / "memory.max").write_text("max")
    monkeypatch.setattr(linux_mod, "_is_linux", lambda: True)
    monkeypatch.setattr(linux_mod, "no_native_side_effects", lambda: False)
    monkeypatch.setenv("MORPH_CGROUP_PATH", str(cg))

    adapter = LinuxAdapter()
    adapter.apply_cpu(max_cores=2, quota_percent=25.0)
    adapter.apply_memory(limit_mb=64)

    assert (cg / "cpu.max").read_text() == "25000 100000"
    assert (cg / "memory.max").read_text() == str(64 * 1024 * 1024)
    assert adapter.cgroup_path() == str(cg)
    assert adapter.fidelity()["cpu.quota_percent"].status == FieldStatus.REPRODUCED
    assert adapter.fidelity()["memory.total_mb"].status == FieldStatus.REPRODUCED
    assert {e["kind"] for e in state.pending()} == {"cgroup"}
    assert "MORPH_CPU_QUOTA_PERCENT" not in adapter.get_env_overrides()

    adapter.cleanup()
    assert (cg / "cpu.max").read_text() == "max 100000"
    assert (cg / "memory.max").read_text() == "max"
    assert state.pending() == []
    adapter.cleanup()  # idempotent


def test_linux_network_uses_tc_replace_and_records_state(monkeypatch):
    """`replace` (idempotent) rather than `add` (fails on a stale root qdisc);
    the rule is recorded before it is applied and forgotten after cleanup."""
    import morph.runtime.adapters.linux as linux_mod

    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(linux_mod, "_is_linux", lambda: True)
    monkeypatch.setattr(linux_mod, "_is_root", lambda: False)
    monkeypatch.setattr(linux_mod, "_tc_bin", lambda: "/sbin/tc")
    monkeypatch.setattr(linux_mod, "no_native_side_effects", lambda: False)

    adapter = LinuxAdapter()
    adapter.apply_network(latency_ms=120, packet_loss_percent=2)
    assert calls[0][:6] == ["sudo", "-n", "/sbin/tc", "qdisc", "replace", "dev"]
    assert "delay" in calls[0] and "120ms" in calls[0] and "2%" in calls[0]
    assert adapter.fidelity()["network.latency_ms"].status == FieldStatus.REPRODUCED
    assert "MORPH_NET_LATENCY_MS" not in adapter.get_env_overrides()
    assert [e["kind"] for e in state.pending()] == ["tc"]

    adapter.cleanup()
    assert calls[-1][:6] == ["sudo", "-n", "/sbin/tc", "qdisc", "del", "dev"]
    assert state.pending() == []


def test_linux_falls_back_to_proxy_when_tc_fails(monkeypatch):
    import morph.runtime.adapters.linux as linux_mod

    def failing_run(cmd, **kwargs):
        raise subprocess.CalledProcessError(2, cmd)

    monkeypatch.setattr(subprocess, "run", failing_run)
    monkeypatch.setattr(linux_mod, "_is_linux", lambda: True)
    monkeypatch.setattr(linux_mod, "_tc_bin", lambda: "/sbin/tc")
    monkeypatch.setattr(linux_mod, "no_native_side_effects", lambda: False)

    adapter = LinuxAdapter()
    adapter.apply_network(latency_ms=50, packet_loss_percent=0)
    try:
        assert adapter.get_env_overrides()["MORPH_NET_LATENCY_MS"] == "50"
        assert adapter.fidelity()["network.latency_ms"].status == FieldStatus.APPROXIMATED
        assert state.pending() == [], "a failed tc must not leave a state record"
    finally:
        adapter.cleanup()


def test_stale_state_from_a_dead_process_is_cleaned_up(monkeypatch):
    """What `morph doctor` does: revert what a SIGKILLed run left behind."""
    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda cmd, **k: calls.append(list(cmd)) or subprocess.CompletedProcess(cmd, 0),
    )
    state.record(state.StateEntry(kind="tc", detail="netem on lo", undo=["tc", "qdisc", "del"],
                                  pid=2_000_000_000))  # no such process
    mine = state.record(state.StateEntry(kind="tc", detail="live", undo=["tc", "qdisc", "del"]))

    assert len(state.stale()) == 1
    results = state.cleanup_stale()
    assert [ok for _e, ok in results] == [True]
    assert calls == [["tc", "qdisc", "del"]]
    assert [e["id"] for e in state.pending()] == [mine.id], "a live run's rule is left alone"
    assert any("(dead)" not in line for line in state.describe())
    state.forget(mine.id)


def test_adapters_on_the_wrong_os_perform_no_native_calls():
    """LinuxAdapter constructed on macOS/Windows (and vice versa) must not run
    sudo, tc or dnctl; the autouse fixture turns any subprocess into a failure."""
    for adapter in (LinuxAdapter(), MacOSAdapter()):
        adapter.apply_network(latency_ms=10, packet_loss_percent=1)
        assert adapter.get_env_overrides()["MORPH_NET_LATENCY_MS"] == "10"
        adapter.apply_cpu(max_cores=1, quota_percent=50)
        adapter.apply_memory(limit_mb=256)
        adapter.cleanup()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("en-IN", "en_IN.UTF-8"),
        ("en-US", "en_US.UTF-8"),
        ("de_DE.UTF-8", "de_DE.UTF-8"),
        ("C", "C"),
        ("tr_TR", "tr_TR"),
        ("pt-BR", "pt_BR.UTF-8"),
    ],
)
def test_bcp47_locales_are_applied_as_posix_names(raw, expected):
    assert to_posix_locale(raw) == expected
    adapter = MacOSAdapter()
    adapter.apply_locale(raw, None)
    assert adapter.get_env_overrides()["LC_ALL"] == expected
    adapter.cleanup()


def test_no_native_guard_is_set_in_tests():
    assert os.environ.get("MORPH_NO_NATIVE") == "1"
