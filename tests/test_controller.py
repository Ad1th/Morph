import pytest
from morph.runtime.adapters.base import BaseAdapter
from morph.runtime.controller import (
    RuntimeController,
    get_default_adapter,
    reconcile_profile_statuses,
)
from morph.schema.profile import (
    CPUInfo,
    EnvironmentProfile,
    FieldStatus,
    LocaleInfo,
    MemoryInfo,
    NetworkInfo,
    OSInfo,
    ProfileField,
)
from morph.schema.telemetry import RunResult


def make_test_profile():
    return EnvironmentProfile(
        version="1.0",
        os=OSInfo(
            family=ProfileField(value="darwin", status=FieldStatus.REQUESTED),
            version=ProfileField(value="14.5", status=FieldStatus.REQUESTED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="arm64", status=FieldStatus.REQUESTED),
            cores=ProfileField(value=4, status=FieldStatus.REQUESTED),
            logical_processors=ProfileField(value=4, status=FieldStatus.REQUESTED),
        ),
        memory=MemoryInfo(
            total_mb=ProfileField(value=8192, status=FieldStatus.REQUESTED)
        ),
        locale=LocaleInfo(
            locale=ProfileField(value="en_US.UTF-8", status=FieldStatus.REQUESTED),
            timezone=ProfileField(value="UTC", status=FieldStatus.REQUESTED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=50.0, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=1.0, status=FieldStatus.REQUESTED),
        ),
    )


class MockAdapter(BaseAdapter):
    def __init__(self):
        super().__init__()
        self.applied_network = None
        self.applied_cpu = None
        self.applied_memory = None
        self.applied_locale = None
        self.cleanup_called = False

    def capabilities(self):
        return {"network": True, "cpu": True, "memory": True, "locale": True}

    def apply_network(self, latency_ms=0.0, packet_loss_percent=0.0, bandwidth_mbps=None):
        self.applied_network = (latency_ms, packet_loss_percent, bandwidth_mbps)

    def apply_cpu(self, max_cores=None):
        self.applied_cpu = max_cores

    def apply_memory(self, limit_mb=None):
        self.applied_memory = limit_mb

    def apply_locale(self, locale_str=None, timezone=None):
        self.applied_locale = (locale_str, timezone)
        if locale_str:
            self._env_overrides["LC_ALL"] = locale_str

    def cleanup(self):
        self.cleanup_called = True
        self._env_overrides.clear()


def test_get_default_adapter():
    adapter = get_default_adapter()
    assert isinstance(adapter, BaseAdapter)

    proxy_adapter = get_default_adapter(force_proxy=True)
    assert proxy_adapter.capabilities()["network"] is True


def test_reconcile_profile_statuses():
    profile = make_test_profile()
    mock_adapter = MockAdapter()
    reconciled = reconcile_profile_statuses(profile, adapter=mock_adapter)

    assert reconciled.network.latency_ms.status == FieldStatus.REPRODUCED
    assert reconciled.locale.locale.status == FieldStatus.REPRODUCED
    assert reconciled.cpu.cores.status == FieldStatus.APPROXIMATED
    assert reconciled.memory.total_mb.status == FieldStatus.APPROXIMATED


def test_runtime_controller_run_success():
    profile = make_test_profile()
    mock_adapter = MockAdapter()
    controller = RuntimeController(adapter=mock_adapter)

    res = controller.run(profile, "python3 -c \"print('ran successfully')\"")

    assert isinstance(res, RunResult)
    assert res.passed is True
    assert "ran successfully" in res.stdout
    assert mock_adapter.applied_network == (50.0, 1.0, None)
    assert mock_adapter.applied_cpu == 4
    assert mock_adapter.applied_memory == 8192
    assert mock_adapter.applied_locale == ("en_US.UTF-8", "UTC")
    assert mock_adapter.cleanup_called is True


def test_runtime_controller_guarantees_cleanup_on_error():
    profile = make_test_profile()
    mock_adapter = MockAdapter()
    controller = RuntimeController(adapter=mock_adapter)

    res = controller.run(profile, "python3 -c \"raise RuntimeError('crash')\"")

    assert res.passed is False
    assert res.error_type == "RuntimeError"
    assert mock_adapter.cleanup_called is True
