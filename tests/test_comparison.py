"""Tests for morph.engine.comparison: Fisher exact test wrapper."""

from morph.engine.comparison import compare_failure_rates


def test_identical_rates_are_not_significant():
    result = compare_failure_rates("baseline", 2, 100, 2, 100)
    assert result.is_significant is False
    assert result.effect_label == "no_effect"


def test_large_increase_is_significant_increase():
    result = compare_failure_rates("latency+loss", 1, 50, 37, 50)
    assert result.is_significant is True
    assert result.effect_label == "significant_increase"
    assert result.p_value < 0.05


def test_large_decrease_is_significant_decrease():
    result = compare_failure_rates("fix_applied", 37, 50, 1, 50)
    assert result.is_significant is True
    assert result.effect_label == "significant_decrease"


def test_small_noisy_difference_is_not_significant():
    # 1 extra failure out of 5 trials is not statistically distinguishable from noise.
    result = compare_failure_rates("cpu_only", 0, 5, 1, 5)
    assert result.is_significant is False
    assert result.effect_label == "no_effect"


def test_failure_rate_properties():
    result = compare_failure_rates("x", 2, 100, 71, 100)
    assert result.baseline_failure_rate == 0.02
    assert result.treatment_failure_rate == 0.71
