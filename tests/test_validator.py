"""Tests for morph.engine.validator: the threshold/bounds checker and
cross-field validation rules from docs/ui-spec.md section 5."""

from morph.engine.validator import (
    check_cross_field_rules,
    check_platform_restrictions,
    check_thresholds,
    check_worker_required,
    validate_profile,
)
from morph.runtime.adapters.base import ProxyAdapter
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


def make_profile(*, cores=4, ram_mb=8192, latency_ms=0, packet_loss=0.0, jitter_ms=None,
                  quota_percent=None, cores_status=FieldStatus.CAPTURED,
                  ram_status=FieldStatus.CAPTURED) -> EnvironmentProfile:
    return EnvironmentProfile(
        os=OSInfo(
            family=ProfileField(value="linux", status=FieldStatus.CAPTURED),
            version=ProfileField(value="1.0", status=FieldStatus.CAPTURED),
        ),
        cpu=CPUInfo(
            architecture=ProfileField(value="x86_64", status=FieldStatus.CAPTURED),
            cores=ProfileField(value=cores, status=cores_status),
            logical_processors=ProfileField(value=cores, status=FieldStatus.CAPTURED),
            quota_percent=ProfileField(value=quota_percent, status=FieldStatus.REQUESTED)
            if quota_percent is not None else None,
        ),
        memory=MemoryInfo(total_mb=ProfileField(value=ram_mb, status=ram_status)),
        locale=LocaleInfo(
            locale=ProfileField(value="en-US", status=FieldStatus.CAPTURED),
            timezone=ProfileField(value="UTC", status=FieldStatus.CAPTURED),
        ),
        network=NetworkInfo(
            latency_ms=ProfileField(value=latency_ms, status=FieldStatus.REQUESTED),
            packet_loss_percent=ProfileField(value=packet_loss, status=FieldStatus.REQUESTED),
            jitter_ms=ProfileField(value=jitter_ms, status=FieldStatus.REQUESTED)
            if jitter_ms is not None else None,
        ),
    )


def test_thresholds_pass_for_in_range_values():
    profile = make_profile(latency_ms=180, packet_loss=2.0)
    assert check_thresholds(profile) == []


def test_thresholds_block_latency_above_max():
    profile = make_profile(latency_ms=6000)
    issues = check_thresholds(profile)
    assert len(issues) == 1
    assert issues[0].severity == "block"
    assert issues[0].field == "network.latency_ms"


def test_thresholds_block_packet_loss_above_max():
    profile = make_profile(packet_loss=50.0)
    issues = check_thresholds(profile)
    assert any(i.field == "network.packet_loss_percent" and i.severity == "block" for i in issues)


def test_thresholds_block_ram_below_min():
    profile = make_profile(ram_mb=64)
    issues = check_thresholds(profile)
    assert any(i.field == "memory.total_mb" and i.severity == "block" for i in issues)


def test_thresholds_never_raise_only_report():
    # "block or warn, never silently clamp" -- values stay as given, not corrected.
    profile = make_profile(latency_ms=999999)
    check_thresholds(profile)
    assert profile.network.latency_ms.value == 999999


def test_cross_field_jitter_within_latency_passes():
    profile = make_profile(latency_ms=180, jitter_ms=15)
    assert check_cross_field_rules(profile) == []


def test_cross_field_jitter_exceeding_latency_blocks():
    profile = make_profile(latency_ms=100, jitter_ms=150)
    issues = check_cross_field_rules(profile)
    assert any(i.field == "network.jitter_ms" and i.severity == "block" for i in issues)


def test_cross_field_cpu_quota_within_ceiling_passes():
    profile = make_profile(cores=4, quota_percent=300)
    assert check_cross_field_rules(profile) == []


def test_cross_field_cpu_quota_exceeding_ceiling_blocks():
    profile = make_profile(cores=4, quota_percent=500)  # ceiling is 4*100=400
    issues = check_cross_field_rules(profile)
    assert any(i.field == "cpu.quota_percent" and i.severity == "block" for i in issues)


def test_worker_required_when_cores_exceed_host():
    host = make_profile(cores=4, ram_mb=8192)
    requested = make_profile(cores=16, ram_mb=8192)
    issues = check_worker_required(requested, host=host)
    assert any(i.field == "cpu.cores" and i.severity == "warn" for i in issues)


def test_worker_required_when_ram_exceeds_host():
    host = make_profile(cores=4, ram_mb=8192)
    requested = make_profile(cores=4, ram_mb=32768)
    issues = check_worker_required(requested, host=host)
    assert any(i.field == "memory.total_mb" and i.severity == "warn" for i in issues)


def test_worker_not_required_when_within_host_capability():
    host = make_profile(cores=8, ram_mb=16384)
    requested = make_profile(cores=4, ram_mb=8192)
    assert check_worker_required(requested, host=host) == []


def test_platform_restriction_warns_when_memory_requested_and_uncontrollable():
    # ProxyAdapter reports memory=False in its capabilities.
    profile = make_profile(ram_mb=4096, ram_status=FieldStatus.REQUESTED)
    issues = check_platform_restrictions(profile, ProxyAdapter())
    assert any(i.field == "memory.total_mb" and i.severity == "warn" for i in issues)


def test_platform_restriction_silent_when_memory_not_requested():
    # CAPTURED (not REQUESTED) means the user didn't ask to change it.
    profile = make_profile(ram_mb=4096, ram_status=FieldStatus.CAPTURED)
    assert check_platform_restrictions(profile, ProxyAdapter()) == []


def test_validate_profile_is_valid_true_when_only_warnings():
    host = make_profile(cores=4, ram_mb=8192)
    requested = make_profile(cores=16, ram_mb=8192, latency_ms=100)
    result = validate_profile(requested, host=host, adapter=ProxyAdapter())
    assert any(i.severity == "warn" for i in result.issues)
    assert result.is_valid is True


def test_validate_profile_is_valid_false_when_any_block():
    requested = make_profile(latency_ms=999999)
    result = validate_profile(requested)
    assert result.is_valid is False
