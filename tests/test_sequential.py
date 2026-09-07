"""morph.engine.sequential: paired round-robin isolation with early stopping."""

import random

import pytest

from morph.engine.sequential import run_sequential_experiment


def test_obvious_effect_stops_early_and_is_environment_caused():
    events = []
    result = run_sequential_experiment(
        lambda: True,
        {"cpu_only": lambda: True, "latency+loss": lambda: False},
        max_rounds=20,
        on_event=events.append,
    )
    assert result.classification == "environment_caused"
    assert result.strongest_condition == "latency+loss"
    by = {c.condition_label: c for c in result.comparisons}
    assert by["latency+loss"].is_significant and by["latency+loss"].stopped_early
    assert by["latency+loss"].method == "paired_e_value"
    assert by["latency+loss"].pairs < 20  # decided long before the budget
    assert not by["cpu_only"].is_significant and by["cpu_only"].pairs == 20
    # Baseline ran once per round, the decided arm stopped consuming trials.
    assert result.baseline.total_runs == 20
    assert by["latency+loss"].treatment_total == by["latency+loss"].pairs
    kinds = [e.kind for e in events]
    assert "evidence" in kinds and kinds[-1] == "verdict"
    ev = [e for e in events if e.kind == "evidence" and e.condition == "latency+loss"][-1]
    assert ev.decisive and ev.e_value >= ev.evidence_threshold == pytest.approx(2 / 0.05)


def test_no_effect_runs_full_budget_and_reports_no_effect():
    result = run_sequential_experiment(lambda: True, {"a": lambda: True}, max_rounds=6)
    assert result.classification == "no_effect"
    cmp = result.comparisons[0]
    assert cmp.e_value == 1.0 and cmp.p_value == 1.0 and not cmp.is_significant
    assert cmp.pairs == 6 and cmp.stopped_early is False


def test_flaky_baseline_is_application_internal():
    result = run_sequential_experiment(lambda: False, {"a": lambda: False}, max_rounds=6)
    assert result.classification == "application_internal"


def test_family_wise_threshold_scales_with_candidates():
    events = []
    run_sequential_experiment(lambda: True, {f"c{i}": (lambda: True) for i in range(4)}, max_rounds=2,
                              on_event=events.append)
    ev = next(e for e in events if e.kind == "evidence")
    assert ev.evidence_threshold == pytest.approx(4 / 0.05)


def test_noisy_effect_is_still_found():
    rng = random.Random(11)
    result = run_sequential_experiment(
        lambda: rng.random() > 0.05,
        {"latency": lambda: rng.random() > 0.15, "latency+loss": lambda: rng.random() > 0.8},
        max_rounds=25,
    )
    assert result.strongest_condition == "latency+loss"
    assert result.classification in ("environment_caused", "environment_exposed")


def test_rejects_empty_candidates():
    with pytest.raises(ValueError):
        run_sequential_experiment(lambda: True, {}, max_rounds=3)
