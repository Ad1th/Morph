"""Tests for morph.schema.parameters: the MVP parameter metadata catalog."""

from morph.schema.parameters import MVP_PARAMETERS


def test_catalog_covers_every_mvp_param_from_the_ui_spec():
    expected = {
        "cpu_cores", "ram_limit", "network_latency", "packet_loss",
        "bandwidth", "locale", "timezone",
    }
    assert set(MVP_PARAMETERS) == expected


def test_every_entry_has_a_resolvable_field_path_and_unit():
    for key, meta in MVP_PARAMETERS.items():
        assert meta.field_path, f"{key} is missing a field_path"
        assert meta.unit, f"{key} is missing a unit"


def test_numeric_bounds_are_internally_consistent():
    for key, meta in MVP_PARAMETERS.items():
        if meta.min is not None and meta.max is not None:
            assert meta.min < meta.max, f"{key}: min must be < max"


def test_experimentable_params_match_the_ui_spec_section_2():
    # Section 2's MVP table doesn't mark locale/timezone as sweepable; the
    # numeric network/resource params are.
    experimentable = {k for k, m in MVP_PARAMETERS.items() if m.experimentable}
    assert experimentable == {"cpu_cores", "ram_limit", "network_latency", "packet_loss", "bandwidth"}
