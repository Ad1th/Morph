"""Tests for morph.schema.parameters: the full ui-spec.md parameter metadata catalog."""

from morph.schema.parameters import MVP_PARAMETERS, PARAMETER_CATALOG, PHASE2_PARAMETERS


def test_catalog_covers_every_mvp_param_from_the_ui_spec():
    # Section 2's actual MVP list, including cpu_quota and jitter -- an
    # earlier pass here filed those as Phase 2 before their schema fields
    # existed. They're MVP params per the spec, corrected now that the
    # fields do exist.
    expected = {
        "cpu_cores", "cpu_quota", "ram_limit", "network_latency", "packet_loss",
        "bandwidth", "jitter", "locale", "timezone",
    }
    assert set(MVP_PARAMETERS) == expected


def test_catalog_covers_every_phase2_param_except_the_three_infeasible_ones():
    # system_time_override, clock_offset, and time_speed are cut entirely
    # (no cross-platform mechanism without libfaketime/admin rights) rather
    # than given a permanently-unsupported row -- see the module docstring.
    expected = {
        "memory_pressure", "swap", "cpu_architecture", "os", "os_version",
        "kernel_version", "filesystem_type", "disk_space_limit",
        "disk_read_latency", "disk_write_latency", "read_only_filesystem",
        "case_sensitivity", "process_timeout", "max_processes",
        "thread_limit", "fd_limit", "network_availability", "connection_type",
    }
    assert set(PHASE2_PARAMETERS) == expected


def test_parameter_catalog_is_the_union_with_no_key_collisions():
    assert set(PARAMETER_CATALOG) == set(MVP_PARAMETERS) | set(PHASE2_PARAMETERS)
    assert len(PARAMETER_CATALOG) == len(MVP_PARAMETERS) + len(PHASE2_PARAMETERS)


def test_every_entry_has_a_resolvable_field_path():
    for key, meta in PARAMETER_CATALOG.items():
        assert meta.field_path, f"{key} is missing a field_path"


def test_numeric_bounds_are_internally_consistent():
    for key, meta in PARAMETER_CATALOG.items():
        if meta.min is not None and meta.max is not None:
            assert meta.min < meta.max, f"{key}: min must be < max"


def test_experimentable_params_match_the_ui_spec_section_2():
    # Section 2's MVP table doesn't mark locale/timezone as sweepable; the
    # numeric network/resource params are.
    experimentable = {k for k, m in MVP_PARAMETERS.items() if m.experimentable}
    assert experimentable == {
        "cpu_cores", "cpu_quota", "ram_limit", "network_latency",
        "packet_loss", "bandwidth", "jitter",
    }


def test_uncontrollable_params_are_never_marked_local():
    # A param the profiler/adapters can't actually apply must never claim
    # "local" support -- that's the exact dishonesty docs/architecture.md's
    # section 16 forbids.
    for key, meta in PARAMETER_CATALOG.items():
        if not meta.controllable:
            assert "local" not in meta.platform_support.values(), (
                f"{key} is not controllable but claims local platform support"
            )
