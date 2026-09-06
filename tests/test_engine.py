"""Tests for morph.engine: experiment loop, threshold search, classifier."""

import itertools

from morph.engine.classifier import (
    APPLICATION_INTERNAL,
    ENVIRONMENT_CAUSED,
    ENVIRONMENT_EXPOSED,
    NO_EFFECT,
    classify_failure,
)
from morph.engine.experiment import (
    detect_interaction,
    isolate_variables,
    run_experiment,
    run_trials,
)
from morph.engine.threshold import search_threshold
from morph.schema.experiment import TrialBatch


def always_pass():
    return True


def always_fail():
    return False


def test_run_trials_counts_failures():
    batch = run_trials(always_fail, 5, "cond")
    assert batch.total_runs == 5
    assert batch.failures == 5
    assert batch.failure_rate == 1.0


def test_run_trials_all_pass():
    batch = run_trials(always_pass, 5, "cond")
    assert batch.failures == 0
    assert batch.failure_rate == 0.0


def test_isolate_variables_flags_the_failing_candidate():
    baseline, comparisons = isolate_variables(
        always_pass,
        {"cpu_only": always_pass, "latency_only": always_pass, "latency+loss": always_fail},
        n=10,
    )
    by_label = {c.condition_label: c for c in comparisons}
    assert by_label["cpu_only"].effect_label == "no_effect"
    assert by_label["latency_only"].effect_label == "no_effect"
    assert by_label["latency+loss"].effect_label == "significant_increase"


def test_run_experiment_picks_strongest_and_classifies_environment_caused():
    result = run_experiment(
        always_pass,
        {"cpu_only": always_pass, "latency+loss": always_fail},
        n=10,
    )
    assert result.strongest_condition == "latency+loss"
    assert result.classification == ENVIRONMENT_CAUSED


def test_run_experiment_no_candidate_significant():
    result = run_experiment(always_pass, {"cpu_only": always_pass}, n=5)
    assert result.strongest_condition == "none"
    assert result.classification == NO_EFFECT


def test_detect_interaction_confirms_combination_only_failure():
    # A alone and B alone pass; only the combination fails -> interaction.
    outcome = detect_interaction(
        run_neither=always_pass,
        run_a=always_pass,
        run_b=always_pass,
        run_both=always_fail,
        label_a="latency",
        label_b="packet_loss",
        n=10,
    )
    assert outcome["interaction_confirmed"] is True
    assert outcome["combined_comparison"].effect_label == "significant_increase"


def test_detect_interaction_rejects_when_a_alone_already_fails():
    # A alone already fails -> not a genuine interaction, A is independently sufficient.
    outcome = detect_interaction(
        run_neither=always_pass,
        run_a=always_fail,
        run_b=always_pass,
        run_both=always_fail,
        label_a="latency",
        label_b="packet_loss",
        n=10,
    )
    assert outcome["interaction_confirmed"] is False


def test_search_threshold_converges_on_boundary():
    def run_at(latency_ms: float) -> bool:
        return latency_ms < 180  # ground truth boundary for this fake target

    result = search_threshold("network.latency_ms", run_at, low=0, high=400, trials=3, precision=5)
    assert result.safe_value <= 180 <= result.failure_value + 5
    assert 150 <= result.boundary_estimate <= 210


def test_search_threshold_search_points_recorded():
    calls = itertools.count()

    def run_at(value: float) -> bool:
        next(calls)
        return value < 100

    result = search_threshold("param", run_at, low=0, high=200, trials=1, precision=10)
    assert len(result.search_points) > 0
    assert all("value" in p and "failure_rate" in p for p in result.search_points)


def test_classify_application_internal_when_baseline_already_flaky():
    baseline = TrialBatch(condition_label="baseline", total_runs=100, failures=20)
    treatment = TrialBatch(condition_label="treatment", total_runs=100, failures=25)
    assert classify_failure(baseline, treatment, is_significant=True) == APPLICATION_INTERNAL


def test_classify_environment_caused_when_baseline_clean():
    baseline = TrialBatch(condition_label="baseline", total_runs=100, failures=0)
    treatment = TrialBatch(condition_label="treatment", total_runs=100, failures=71)
    assert classify_failure(baseline, treatment, is_significant=True) == ENVIRONMENT_CAUSED


def test_classify_environment_exposed_when_baseline_has_low_nonzero_rate():
    baseline = TrialBatch(condition_label="baseline", total_runs=100, failures=1)
    treatment = TrialBatch(condition_label="treatment", total_runs=100, failures=48)
    assert classify_failure(baseline, treatment, is_significant=True) == ENVIRONMENT_EXPOSED


def test_classify_no_effect_when_not_significant():
    baseline = TrialBatch(condition_label="baseline", total_runs=100, failures=0)
    treatment = TrialBatch(condition_label="treatment", total_runs=100, failures=1)
    assert classify_failure(baseline, treatment, is_significant=False) == NO_EFFECT
