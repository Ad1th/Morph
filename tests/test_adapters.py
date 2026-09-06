import os

from morph.runtime.adapters import (
    LinuxAdapter,
    MacOSAdapter,
    WindowsAdapter,
)


def test_macos_adapter_capabilities_and_locale():
    adapter = MacOSAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is True
    assert caps["locale"] is True

    adapter.apply_locale("en_US.UTF-8", "America/New_York")
    adapter.apply_cpu(max_cores=2)
    adapter.apply_memory(limit_mb=1024)
    overrides = adapter.get_env_overrides()

    assert overrides["LC_ALL"] == "en_US.UTF-8"
    assert overrides["TZ"] == "America/New_York"
    assert overrides["MORPH_MAX_CORES"] == "2"
    assert overrides["MORPH_MEMORY_LIMIT_MB"] == "1024"

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


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

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


def test_windows_adapter_capabilities_and_locale():
    adapter = WindowsAdapter()
    caps = adapter.capabilities()
    assert caps["network"] is True
    assert caps["cpu"] is True
    assert caps["memory"] is True
    assert caps["locale"] is True

    adapter.apply_locale("ja_JP.UTF-8", "Asia/Tokyo")
    overrides = adapter.get_env_overrides()

    assert overrides["LC_ALL"] == "ja_JP.UTF-8"
    assert overrides["TZ"] == "Asia/Tokyo"

    adapter.cleanup()
    assert adapter.get_env_overrides() == {}


def test_cpu_quota_hint_on_windows_and_macos():
    # Neither has a wired-up native quota mechanism (needs pywin32 / no
    # cgroups) -- an honest env-var hint, not a fake apply.
    for adapter in (WindowsAdapter(), MacOSAdapter()):
        adapter.apply_cpu(max_cores=2, quota_percent=150.0)
        assert adapter.get_env_overrides()["MORPH_CPU_QUOTA_PERCENT"] == "150.0"
        adapter.cleanup()


def test_linux_cpu_quota_falls_back_to_hint_when_not_root():
    if os.name == "posix" and os.geteuid() == 0:
        return  # can't exercise the non-root fallback path as root
    adapter = LinuxAdapter()
    adapter.apply_cpu(max_cores=2, quota_percent=150.0)
    assert adapter.get_env_overrides()["MORPH_CPU_QUOTA_PERCENT"] == "150.0"
    adapter.cleanup()
