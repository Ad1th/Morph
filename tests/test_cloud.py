"""Tests for remote execution: when a run must leave this machine, and how."""

from __future__ import annotations

import json

import pytest

from morph.cloud import capability as cap_mod
from morph.cloud.capability import assess_locally
from morph.cloud.dispatch import NotReproducibleAnywhere, run_anywhere
from morph.cloud.worker import RemoteWorker, WorkerUnavailable, _last_json_object, resolve_config
from morph.schema.config import CloudConfig
from morph.schema.profile import (
    CPUInfo,
    EnvironmentProfile,
    FieldStatus,
    LocaleInfo,
    MemoryInfo,
    OSInfo,
    ProfileField,
)
from morph.schema.telemetry import RunResult


def make_profile(*, memory_mb=4096, cores=2, arch="x86_64", os_family="linux"):
    f = lambda v: ProfileField(value=v, status=FieldStatus.REQUESTED)  # noqa: E731
    return EnvironmentProfile(
        version="1.0",
        os=OSInfo(family=f(os_family), version=f("1.0")),
        cpu=CPUInfo(architecture=f(arch), cores=f(cores), logical_processors=f(cores)),
        memory=MemoryInfo(total_mb=f(memory_mb)),
        locale=LocaleInfo(locale=f("en_US.UTF-8"), timezone=f("UTC")),
    )


@pytest.fixture
def host(monkeypatch):
    """Pin the "physical machine" so these tests do not depend on the runner."""
    monkeypatch.setattr(cap_mod, "_host_memory_mb", lambda: 16384)
    monkeypatch.setattr(cap_mod.os, "cpu_count", lambda: 8)
    monkeypatch.setattr(cap_mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(cap_mod.platform, "system", lambda: "Linux")


# --------------------------------------------------------------- assessment


def test_profile_within_host_is_reproducible_locally(host):
    cap = assess_locally(make_profile(memory_mb=8192, cores=4))
    assert cap.reproducible_locally
    assert cap.shortfalls == []


def test_more_memory_than_the_host_has_is_a_shortfall(host):
    cap = assess_locally(make_profile(memory_mb=65536))
    assert not cap.reproducible_locally
    assert [s.field_path for s in cap.shortfalls] == ["memory.total_mb"]


def test_more_cores_than_the_host_has_is_a_shortfall(host):
    cap = assess_locally(make_profile(cores=64))
    assert [s.field_path for s in cap.shortfalls] == ["cpu.cores"]


def test_rounding_noise_is_not_a_shortfall(host):
    """Regression: the profiler and this module round MB differently.

    Capturing a profile on a machine and immediately assessing it reported a
    1 MB shortfall, which would have routed the run to a worker for nothing.
    """
    cap = assess_locally(make_profile(memory_mb=16385))
    assert cap.reproducible_locally


def test_different_architecture_needs_another_machine(host):
    cap = assess_locally(make_profile(arch="arm64"))
    assert [s.field_path for s in cap.shortfalls] == ["cpu.architecture"]


def test_architecture_aliases_are_the_same_machine(host):
    """amd64 and x86_64 name one instruction set; that is not a shortfall."""
    assert assess_locally(make_profile(arch="amd64")).reproducible_locally


def test_different_os_needs_another_machine(host):
    cap = assess_locally(make_profile(os_family="windows"))
    assert [s.field_path for s in cap.shortfalls] == ["os.family"]


def test_software_conditions_are_not_shortfalls(host):
    """Locale and network are the adapters' business, not the cloud's.

    reconcile_profile_statuses already reports those honestly; treating them
    as shortfalls here would send every shaped run to a worker.
    """
    profile = make_profile()
    profile.locale.locale.value = "tr_TR.UTF-8"
    assert assess_locally(profile).reproducible_locally


# ------------------------------------------------------------------- worker


def test_ssh_argv_never_prompts_and_carries_the_key():
    worker = RemoteWorker(CloudConfig(host="10.0.0.5", user="dev", ssh_key="/keys/id"))
    argv = worker.ssh_argv("true")
    assert "BatchMode=yes" in argv, "a password prompt mid-demo looks like a hang"
    assert argv[argv.index("-i") + 1].endswith("id")
    assert "dev@10.0.0.5" in argv


def test_remote_command_expands_a_tilde_workdir():
    """shlex.quote('~/morph') gives '~/morph', and `cd '~/morph'` fails."""
    worker = RemoteWorker(CloudConfig(host="h", workdir="~/morph"))
    remote = worker.build_run_command("echo hi", 5)
    assert 'cd "$HOME"/morph' in remote
    assert "'~/morph'" not in remote


def test_remote_command_quotes_the_target_command_and_asks_for_json():
    worker = RemoteWorker(CloudConfig(host="h"))
    remote = worker.build_run_command("pytest -k 'a b'", 12.5)
    assert "--json" in remote
    assert "--timeout 12.5" in remote
    # The command must survive a shell that would otherwise split it.
    assert "pytest -k 'a b'" in remote.replace("'\"'\"'", "'")


def test_remote_command_cleans_up_its_temp_profile():
    remote = RemoteWorker(CloudConfig(host="h")).build_run_command("true", 1)
    assert "trap" in remote and "rm -f" in remote, "a leaked file per trial poisons a batch"


def test_config_comes_from_the_environment(monkeypatch):
    monkeypatch.setenv("MORPH_CLOUD_HOST", "1.2.3.4")
    monkeypatch.setenv("MORPH_CLOUD_USER", "ci")
    cfg = resolve_config(CloudConfig())
    assert (cfg.host, cfg.user, cfg.enabled) == ("1.2.3.4", "ci", True)


def test_run_result_is_read_from_the_last_json_line():
    """Workers print banners; only the final document is the result."""
    assert _last_json_object('Warning: something\n{"a": 1}\n') == {"a": 1}
    assert _last_json_object("no json here") is None


def test_worker_reports_unavailable_when_it_returns_nothing(monkeypatch):
    worker = RemoteWorker(CloudConfig(host="h"))
    monkeypatch.setattr(
        worker,
        "_ssh",
        lambda *a, **k: type("P", (), {"stdout": "", "stderr": "boom", "returncode": 255})(),
    )
    with pytest.raises(WorkerUnavailable, match="no run result"):
        worker.run(make_profile(), "true")


# ----------------------------------------------------------------- dispatch


class FakeWorker:
    """Stands in for a reachable machine, so no SSH happens in tests."""

    configured = True
    target = "worker@cloud"

    def __init__(self, result=None, raises=None):
        self._result = result
        self._raises = raises
        self.calls = []

    def run(self, profile, command, timeout=30.0):
        self.calls.append((command, timeout))
        if self._raises:
            raise self._raises
        return self._result


def _ok_result():
    return RunResult(exit_code=0, passed=True, stdout="", stderr="")


def test_a_fitting_profile_runs_locally(host):
    class FakeController:
        def __init__(self):
            self.ran = False

        def run(self, profile, command, timeout=30.0, cwd=None):
            self.ran = True
            self.cwd = cwd
            return _ok_result()

    controller = FakeController()
    worker = FakeWorker(_ok_result())
    _, placement = run_anywhere(
        make_profile(), "true", controller=controller, worker=worker
    )

    assert placement.location == "local"
    assert controller.ran and worker.calls == [], "cloud is a fallback, not a default"


def test_an_oversized_profile_is_routed_to_the_worker(host):
    worker = FakeWorker(_ok_result())
    result, placement = run_anywhere(make_profile(memory_mb=65536), "pytest", worker=worker)

    assert placement.location == "cloud"
    assert placement.worker_target == "worker@cloud"
    assert worker.calls == [("pytest", 30.0)]
    assert result.passed


def test_no_worker_means_an_honest_refusal(host):
    """Never silently run on a machine that does not match (PRD section 10)."""
    nowhere = FakeWorker()
    nowhere.configured = False
    with pytest.raises(NotReproducibleAnywhere, match="NOT_REPRODUCIBLE_LOCALLY"):
        run_anywhere(make_profile(memory_mb=65536), "true", worker=nowhere)


def test_a_broken_worker_refuses_rather_than_falling_back_to_local(host):
    worker = FakeWorker(raises=WorkerUnavailable("connection refused"))
    with pytest.raises(NotReproducibleAnywhere, match="connection refused"):
        run_anywhere(make_profile(memory_mb=65536), "true", worker=worker)


def test_cloud_can_be_refused_for_a_run(host):
    worker = FakeWorker(_ok_result())
    with pytest.raises(NotReproducibleAnywhere, match="not permitted"):
        run_anywhere(
            make_profile(memory_mb=65536), "true", worker=worker, allow_cloud=False
        )
    assert worker.calls == []


def test_refusal_names_what_fell_short(host):
    with pytest.raises(NotReproducibleAnywhere) as exc:
        run_anywhere(make_profile(memory_mb=65536, cores=99), "true", allow_cloud=False)
    message = str(exc.value)
    assert "memory.total_mb" in message and "cpu.cores" in message


def test_the_profile_sent_to_the_worker_is_the_one_requested(host):
    """The worker must reproduce the TARGET profile, not the local host's."""
    worker = FakeWorker(_ok_result())
    profile = make_profile(memory_mb=65536)
    captured = {}

    def capture_run(profile, command, timeout=30.0):
        captured["mem"] = json.loads(profile.model_dump_json())["memory"]["total_mb"]["value"]
        return _ok_result()

    worker.run = capture_run
    run_anywhere(profile, "true", worker=worker)
    assert captured["mem"] == 65536


def test_worker_config_roundtrip():
    from morph.schema.config import MorphConfig, WorkerConfig

    w_cfg = WorkerConfig(
        enabled=True,
        provider="pi",
        host="rbpi.local",
        user="rbpi",
        python="~/morph/.venv/bin/python",
        workdir="~/morph",
        connect_timeout=10.0,
    )
    raw = w_cfg.model_dump()
    reconstructed = WorkerConfig.model_validate(raw)
    assert reconstructed == w_cfg

    m_cfg = MorphConfig(worker=w_cfg)
    m_raw = m_cfg.model_dump()
    m_reconstructed = MorphConfig.model_validate(m_raw)
    assert m_reconstructed.worker.host == "rbpi.local"
    assert m_reconstructed.worker.user == "rbpi"


def test_worker_config_env_vars(monkeypatch):
    monkeypatch.setenv("MORPH_WORKER_HOST", "192.168.1.100")
    monkeypatch.setenv("MORPH_WORKER_USER", "pi_user")
    cfg = resolve_config(None)
    assert cfg.host == "192.168.1.100"
    assert cfg.user == "pi_user"
    assert cfg.enabled is True

