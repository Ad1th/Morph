"""Experiment loop: baseline/treatment trial runner, single-variable isolation,
and two-variable interaction detection.

Trials are driven by a caller-supplied `run_fn` callback (returns True if the
run passed) rather than a real subprocess, so the engine is testable without a
target application or the runtime controller wired up.
"""

from typing import Callable, Optional

from morph.engine.classifier import classify_failure
from morph.engine.comparison import compare_failure_rates
from morph.schema.comparison import ComparisonResult
from morph.schema.experiment import ExperimentResult, TrialBatch

RunFn = Callable[[], bool]


def run_trials(
    run_fn: RunFn, n: int, condition_label: str, profile_overrides: Optional[dict] = None
) -> TrialBatch:
    failures = sum(1 for _ in range(n) if not run_fn())
    return TrialBatch(
        condition_label=condition_label,
        profile_overrides=profile_overrides or {},
        total_runs=n,
        failures=failures,
    )


def compare_batches(baseline: TrialBatch, treatment: TrialBatch) -> ComparisonResult:
    return compare_failure_rates(
        treatment.condition_label,
        baseline.failures,
        baseline.total_runs,
        treatment.failures,
        treatment.total_runs,
    )


def isolate_variables(
    baseline_run_fn: RunFn, candidates: dict[str, RunFn], n: int = 5
) -> tuple[TrialBatch, list[ComparisonResult]]:
    """Runs a shared baseline, then each candidate variable's treatment, and
    compares each treatment against that baseline."""
    baseline = run_trials(baseline_run_fn, n, "baseline")
    comparisons = [
        compare_batches(baseline, run_trials(run_fn, n, label))
        for label, run_fn in candidates.items()
    ]
    return baseline, comparisons


def detect_interaction(
    run_neither: RunFn,
    run_a: RunFn,
    run_b: RunFn,
    run_both: RunFn,
    label_a: str,
    label_b: str,
    n: int = 5,
) -> dict:
    """Runs all four cells of a 2x2 design. An interaction is confirmed only
    when A alone and B alone show no effect but A+B does — proving the failure
    depends on the combination, not either condition individually."""
    neither = run_trials(run_neither, n, "neither")
    a_only = run_trials(run_a, n, label_a)
    b_only = run_trials(run_b, n, label_b)
    both = run_trials(run_both, n, f"{label_a}+{label_b}")

    a_alone = compare_batches(neither, a_only)
    b_alone = compare_batches(neither, b_only)
    combined = compare_batches(neither, both)

    interaction_confirmed = (
        a_alone.effect_label == "no_effect"
        and b_alone.effect_label == "no_effect"
        and combined.effect_label == "significant_increase"
    )

    return {
        "neither": neither,
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "a_alone_comparison": a_alone,
        "b_alone_comparison": b_alone,
        "combined_comparison": combined,
        "interaction_confirmed": interaction_confirmed,
    }


def run_experiment(baseline_run_fn: RunFn, candidates: dict[str, RunFn], n: int = 5) -> ExperimentResult:
    """End-to-end single-variable isolation: baseline + each candidate, picks the
    strongest significant condition, and classifies the failure."""
    baseline, comparisons = isolate_variables(baseline_run_fn, candidates, n)

    increases = [c for c in comparisons if c.effect_label == "significant_increase"]
    strongest = max(increases, key=lambda c: c.treatment_failure_rate, default=None)

    if strongest is None:
        classification = "application_internal" if baseline.failure_rate > 0.10 else "no_effect"
        strongest_condition = "none"
        summary = "No candidate condition produced a statistically significant increase in failures."
    else:
        treatment_batch = TrialBatch(
            condition_label=strongest.condition_label,
            total_runs=strongest.treatment_total,
            failures=strongest.treatment_failures,
        )
        classification = classify_failure(baseline, treatment_batch, strongest.is_significant)
        strongest_condition = strongest.condition_label
        summary = (
            f"Baseline failed {baseline.failures}/{baseline.total_runs} runs; "
            f"'{strongest_condition}' failed {strongest.treatment_failures}/{strongest.treatment_total} "
            f"(p={strongest.p_value:.4g})."
        )

    return ExperimentResult(
        baseline=baseline,
        comparisons=comparisons,
        classification=classification,
        strongest_condition=strongest_condition,
        summary=summary,
    )
