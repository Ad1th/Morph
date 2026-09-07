"""Tests for morph.engine.comparison: one-sided Fisher exact test wrapper,
Newcombe risk-difference interval, Holm adjustment and minimum-n helper."""

import pytest

from morph.engine.comparison import (
    apply_holm,
    compare_failure_rates,
    holm_adjust,
    minimum_trials_for_significance,
    newcombe_risk_difference_ci,
    wilson_interval,
)


def test_identical_rates_are_not_significant():
    result = compare_failure_rates("baseline", 2, 100, 2, 100)
    assert result.is_significant is False
    assert result.effect_label == "no_effect"
    assert result.method == "fisher"
    assert result.risk_difference == 0.0


def test_large_increase_is_significant_increase():
    result = compare_failure_rates("latency+loss", 1, 50, 37, 50)
    assert result.is_significant is True
    assert result.effect_label == "significant_increase"
    assert result.p_value < 1e-10
    assert result.p_value_decrease > 0.999


def test_large_decrease_is_significant_decrease():
    result = compare_failure_rates("fix_applied", 37, 50, 1, 50)
    assert result.is_significant is True
    assert result.effect_label == "significant_decrease"
    assert result.p_value > 0.999  # "fails more" is not supported at all
    assert result.p_value_decrease < 1e-10


def test_small_noisy_difference_is_not_significant():
    # 1 extra failure out of 5 trials is not statistically distinguishable from noise.
    result = compare_failure_rates("cpu_only", 0, 5, 1, 5)
    assert result.is_significant is False
    assert result.effect_label == "no_effect"
    assert result.p_value == pytest.approx(0.5)


@pytest.mark.parametrize(
    ("b_fail", "b_n", "t_fail", "t_n", "expected_one_sided"),
    [
        (0, 5, 4, 5, 0.023809523809523808),   # two-sided would be 0.0476
        (0, 10, 4, 10, 0.04334365325077399),  # two-sided would be 0.087
        (0, 4, 4, 4, 1 / 70),                 # perfect separation: 1 / C(8, 4)
        (0, 3, 3, 3, 1 / 20),                 # n=3 lands exactly on 0.05: not < alpha
    ],
)
def test_one_sided_fisher_p_values_match_known_values(b_fail, b_n, t_fail, t_n, expected_one_sided):
    result = compare_failure_rates("c", b_fail, b_n, t_fail, t_n)
    assert result.p_value == pytest.approx(expected_one_sided, rel=1e-9)
    assert isinstance(result.p_value, float)
    assert isinstance(result.is_significant, bool)


def test_n3_perfect_separation_is_never_significant():
    assert compare_failure_rates("c", 0, 3, 3, 3).is_significant is False
    assert compare_failure_rates("c", 0, 4, 4, 4).is_significant is True


def test_failure_rate_properties():
    result = compare_failure_rates("x", 2, 100, 71, 100)
    assert result.baseline_failure_rate == 0.02
    assert result.treatment_failure_rate == 0.71


def test_risk_difference_and_newcombe_ci():
    result = compare_failure_rates("x", 0, 5, 4, 5)
    assert result.risk_difference == pytest.approx(0.8)
    lo, hi = result.risk_difference_ci
    assert 0.0 < lo < 0.8 < hi <= 1.0
    assert lo == pytest.approx(0.1926, abs=1e-3)
    assert hi == pytest.approx(0.9638, abs=1e-3)
    # Wilson on 0/5 starts at exactly zero and stays within [0, 1].
    assert wilson_interval(0, 5)[0] == 0.0
    assert wilson_interval(5, 5)[1] == 1.0
    assert newcombe_risk_difference_ci(0, 0, 0, 0) is None


def test_empty_batches_are_handled_without_crashing():
    result = compare_failure_rates("empty", 0, 0, 0, 0)
    assert result.p_value == 1.0
    assert result.is_significant is False
    assert result.risk_difference_ci is None


def test_rejects_impossible_counts():
    with pytest.raises(ValueError):
        compare_failure_rates("x", 6, 5, 0, 5)
    with pytest.raises(ValueError):
        compare_failure_rates("x", -1, 5, 0, 5)


def test_holm_adjustment_is_step_down_and_monotone():
    assert holm_adjust([]) == []
    assert holm_adjust([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm_adjust([0.5, 0.9]) == pytest.approx([1.0, 1.0])
    assert holm_adjust([0.02]) == [0.02]


def test_apply_holm_marks_family_wise_significance():
    a = compare_failure_rates("a", 0, 10, 4, 10)  # raw p 0.043
    b = compare_failure_rates("b", 0, 10, 0, 10)
    c = compare_failure_rates("c", 0, 10, 10, 10)
    adjusted = apply_holm([a, b, c])
    by = {x.condition_label: x for x in adjusted}
    assert all(x.method == "fisher_holm" for x in adjusted)
    assert by["c"].is_significant and by["c"].effect_label == "significant_increase"
    # 0.043 * 2 (second-smallest of three) = 0.087: not significant family-wise.
    assert by["a"].p_value_adjusted == pytest.approx(0.0867, abs=1e-3)
    assert not by["a"].is_significant and by["a"].effect_label == "no_effect"
    assert by["a"].p_value == pytest.approx(0.0433, abs=1e-3)  # raw p kept
    # A single comparison is untouched apart from p_value_adjusted == p_value.
    single = apply_holm([a])[0]
    assert single.method == "fisher" and single.p_value_adjusted == single.p_value


def test_minimum_trials_for_significance():
    assert minimum_trials_for_significance(0.05) == 4
    assert minimum_trials_for_significance(0.05, one_sided=False) == 4
    assert minimum_trials_for_significance(0.05, hypotheses=4) == 5
    assert minimum_trials_for_significance(0.01) == 5
