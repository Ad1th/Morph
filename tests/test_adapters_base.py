from morph.runtime.adapters.base import BaseAdapter, ProxyAdapter


class DummyAdapter(BaseAdapter):
    def apply_network(self, latency_ms=0.0, packet_loss_percent=0.0, bandwidth_mbps=None):
        self._env_overrides["NET_LATENCY"] = str(latency_ms)

    def apply_cpu(self, max_cores=None, quota_percent=None):
        if max_cores:
            self._env_overrides["MAX_CORES"] = str(max_cores)
        if quota_percent:
            self._env_overrides["CPU_QUOTA_PERCENT"] = str(quota_percent)

    def apply_memory(self, limit_mb=None):
        if limit_mb:
            self._env_overrides["MEM_LIMIT"] = str(limit_mb)

    def apply_locale(self, locale_str=None, timezone=None):
        if locale_str:
            self._env_overrides["LC_ALL"] = locale_str
        if timezone:
            self._env_overrides["TZ"] = timezone

    def cleanup(self):
        self._env_overrides.clear()

    def capabilities(self):
        return {"network": True, "cpu": True, "memory": True, "locale": True}


def test_base_adapter_contract():
    adapter = DummyAdapter()
    assert adapter.capabilities()["network"] is True
    adapter.apply_locale("en_US.UTF-8", "UTC")
    adapter.apply_cpu(4)
    overrides = adapter.get_env_overrides()
    assert overrides["LC_ALL"] == "en_US.UTF-8"
    assert overrides["TZ"] == "UTC"
    assert overrides["MAX_CORES"] == "4"

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


def test_base_adapter_context_manager():
    with DummyAdapter() as adapter:
        adapter.apply_network(latency_ms=100.0)
        assert adapter.get_env_overrides()["NET_LATENCY"] == "100.0"
    assert adapter.get_env_overrides() == {}


def test_proxy_adapter_capabilities_and_locale():
    adapter = ProxyAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is False
    assert caps["memory"] is False
    assert caps["locale"] is True

    adapter.apply_locale("de_DE.UTF-8", "Europe/Berlin")
    overrides = adapter.get_env_overrides()
    assert overrides["LC_ALL"] == "de_DE.UTF-8"
    assert overrides["TZ"] == "Europe/Berlin"

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}
