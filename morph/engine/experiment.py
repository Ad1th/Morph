"""Experiment loop: baseline/treatment trial runner, single-variable isolation,
and two-variable interaction detection.

Trials are driven by a caller-supplied ``run_fn`` callback rather than a real
subprocess, so the engine is testable without a target application or the
runtime controller wired up. ``run_fn`` may return a plain ``bool`` (passed) or
a full ``RunResult`` -- the latter lets progress events carry stdout/stderr and
timing for a live UI. A ``RunResult`` flagged ``invalid`` (setup error) is
retried and, if it stays invalid, raises
:class:`~morph.engine.errors.InvalidTrialError` instead of counting as a
failure.

Every function takes an optional keyword ``on_event``. When supplied, the engine
emits :class:`~morph.schema.events.TrialEvent` objects as it goes. Default is
``None`` -- return values are then identical to running without the hook.

Statistics: each candidate is tested against the shared baseline with a
one-sided Fisher exact test; with two or more candidates the p-values are
Holm-adjusted so the family-wise false-positive rate stays at ``alpha``. The
2x2 interaction test is Bayesian: the posterior probability that the excess
``p_both - p_a - p_b + p_neither`` is positive, under Jeffreys Beta(f+1/2,
n-f+1/2) posteriors per cell (Rothman's additive-interaction contrast).
"""

from __future__ import annotations

import numpy as np

from morph.engine.classifier import (
    APPLICATION_INTERNAL,
    NO_EFFECT,
    baseline_is_internally_flaky,
    classify_failure,
)
from morph.engine.comparison import (
    SIGNIFICANCE_LEVEL,
    apply_holm,
    compare_failure_rates,
    minimum_trials_for_significance,
)
from morph.engine.progress import OnEvent, RunFn, emit, run_valid_trial, tail
from morph.schema.comparison import ComparisonResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult, TrialBatch
from morph.schema.telemetry import RunResult

__all__ = [
    "RunFn",
    "compare_batches",
    "detect_interaction",
    "interaction_probability",
    "isolate_variables",
    "run_experiment",
    "run_trials",
    "small_sample_warning",
]

INTERACTION_CONFIRMATION_PROBABILITY = 0.95
INTERACTION_DRAWS = 20_000


def run_trials(
    run_fn: RunFn,
    n: int,
    condition_label: str,
    profile_overrides: dict | None = None,
    *,
    on_event: OnEvent | None = None,
) -> TrialBatch:
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    emit(on_event, TrialEvent(kind="condition_start", condition=condition_label, total=n))

    failures = 0
    run_results: list[RunResult] = []
    for i in range(n):
        passed, result, elapsed_ms = run_valid_trial(
            run_fn, condition_label, on_event, trial_index=i, total=n
        )
        if result is not None:
            run_results.append(result)
        if not passed:
            failures += 1

        emit(
            on_event,
            TrialEvent(
                kind="trial",
                condition=condition_label,
                trial_index=i,
                total=n,
                passed=passed,
                duration_ms=elapsed_ms,
                failures_so_far=failures,
                error_type=result.error_type if result else None,
                stdout_tail=tail(result.stdout) if result else None,
                stderr_tail=tail(result.stderr) if result else None,
            ),
        )

    batch = TrialBatch(
        condition_label=condition_label,
        profile_overrides=profile_overrides or {},
        total_runs=n,
        failures=failures,
        run_results=run_results,
    )
    emit(
        on_event,
        TrialEvent(
            kind="condition_done",
            condition=condition_label,
            total=n,
            failures=failures,
            failure_rate=batch.failure_rate,
        ),
    )
    return batch


def compare_batches(
    baseline: TrialBatch, treatment: TrialBatch, *, alpha: float = SIGNIFICANCE_LEVEL
) -> ComparisonResult:
    cmp = compare_failure_rates(
        treatment.condition_label,
        baseline.failures,
        baseline.total_runs,
        treatment.failures,
        treatment.total_runs,
        alpha=alpha,
    )
    # Keep the real treatment batch (with its run_results) so blame and
    # regression export can see the failing runs' stdout/stderr.
    return cmp.model_copy(update={"treatment": treatment})


def _emit_comparison(on_event: OnEvent | None, treatment: TrialBatch, cmp: ComparisonResult) -> None:
    emit(
        on_event,
        TrialEvent(
            kind="comparison",
            condition=treatment.condition_label,
            failures=treatment.failures,
            failure_rate=treatment.failure_rate,
            p_value=cmp.p_value,
            is_significant=cmp.is_significant,
            effect_label=cmp.effect_label,
            extra={
                "method": cmp.method,
                "p_value_adjusted": cmp.p_value_adjusted,
                "risk_difference": cmp.risk_difference,
                "risk_difference_ci": cmp.risk_difference_ci,
            },
        ),
    )


def small_sample_warning(n: int, hypotheses: int, alpha: float = SIGNIFICANCE_LEVEL) -> str | None:
    """The warning to attach when ``n`` trials per arm cannot reach significance."""
    minimum = minimum_trials_for_significance(alpha, hypotheses)
    if n >= minimum:
        return None
    return (
        f"n={n} trials per condition can never reach significance at alpha={alpha:g}"
        f"{f' across {hypotheses} candidates' if hypotheses > 1 else ''}: even 0/{n} vs {n}/{n} "
        f"is not significant. Use at least n={minimum}. Any 'no_effect' verdict below is "
        "absence of evidence, not evidence of absence."
    )


def isolate_variables(
    baseline_run_fn: RunFn,
    candidates: dict[str, RunFn],
    n: int = 5,
    *,
    alpha: float = SIGNIFICANCE_LEVEL,
    on_event: OnEvent | None = None,
) -> tuple[TrialBatch, list[ComparisonResult]]:
    """Runs a shared baseline, then each candidate variable's treatment, and
    compares each treatment against that baseline.

    With two or more candidates the comparisons come back Holm-adjusted
    (``method == "fisher_holm"``, ``p_value_adjusted`` set) so that
    ``is_significant`` is honest for the whole family of K tests.
    """
    if not candidates:
        raise ValueError("at least one candidate condition is required")
    warning = small_sample_warning(n, len(candidates), alpha)
    emit(
        on_event,
        TrialEvent(
            kind="phase_start",
            phase="isolation",
            extra={"warnings": [warning] if warning else [], "n": n, "alpha": alpha},
        ),
    )

    baseline = run_trials(baseline_run_fn, n, "baseline", on_event=on_event)
    raw: list[ComparisonResult] = []
    for label, run_fn in candidates.items():
        treatment = run_trials(run_fn, n, label, on_event=on_event)
        raw.append(compare_batches(baseline, treatment, alpha=alpha))

    comparisons = apply_holm(raw, alpha)
    for cmp in comparisons:
        _emit_comparison(on_event, cmp.treatment, cmp)

    emit(on_event, TrialEvent(kind="phase_done", phase="isolation"))
    return baseline, comparisons


def interaction_probability(
    neither: TrialBatch,
    a_only: TrialBatch,
    b_only: TrialBatch,
    both: TrialBatch,
    *,
    draws: int = INTERACTION_DRAWS,
    seed: int = 0,
) -> float:
    """Posterior probability that the 2x2 design is super-additive:
    ``p_both - p_a - p_b + p_neither > 0``, under independent Jeffreys
    Beta(f + 1/2, n - f + 1/2) posteriors for the four cell rates.

    Values near 0.5 mean "no evidence either way" (e.g. an exactly additive
    table, or every cell at n=0); near 1 means the combination fails more than
    the two conditions' separate effects would add up to.
    """
    rng = np.random.default_rng(seed)

    def draw(batch: TrialBatch) -> np.ndarray:
        return rng.beta(batch.failures + 0.5, batch.total_runs - batch.failures + 0.5, size=draws)

    excess = draw(both) - draw(a_only) - draw(b_only) + draw(neither)
    return float(np.mean(excess > 0.0))


def detect_interaction(
    run_neither: RunFn,
    run_a: RunFn,
    run_b: RunFn,
    run_both: RunFn,
    label_a: str,
    label_b: str,
    n: int = 5,
    *,
    alpha: float = SIGNIFICANCE_LEVEL,
    seed: int = 0,
    on_event: OnEvent | None = None,
) -> dict:
    """Runs all four cells of a 2x2 design and tests the interaction term.

    An interaction is *confirmed* only when (1) the posterior probability of
    super-additivity (:func:`interaction_probability`) exceeds 0.95 -- so an
    additive table such as 0/10, 4/10, 4/10, 8/10 is not called an interaction
    -- and (2) neither single condition is on its own a significant increase
    at least as strong as the combination. "A alone was not significant at
    n=5" is never, by itself, treated as "A alone has no effect".
    """
    emit(on_event, TrialEvent(kind="phase_start", phase="interaction"))

    both_label = f"{label_a}+{label_b}"
    neither = run_trials(run_neither, n, "neither", on_event=on_event)
    a_only = run_trials(run_a, n, label_a, on_event=on_event)
    b_only = run_trials(run_b, n, label_b, on_event=on_event)
    both = run_trials(run_both, n, both_label, on_event=on_event)

    a_alone = compare_batches(neither, a_only, alpha=alpha)
    b_alone = compare_batches(neither, b_only, alpha=alpha)
    combined = compare_batches(neither, both, alpha=alpha)
    for treatment, cmp in ((a_only, a_alone), (b_only, b_alone), (both, combined)):
        _emit_comparison(on_event, treatment, cmp)

    prob = interaction_probability(neither, a_only, b_only, both, seed=seed)
    excess = both.failure_rate - a_only.failure_rate - b_only.failure_rate + neither.failure_rate

    def single_is_weaker(cmp: ComparisonResult, batch: TrialBatch) -> bool:
        return cmp.effect_label != "significant_increase" or batch.failure_rate < both.failure_rate

    interaction_confirmed = (
        prob > INTERACTION_CONFIRMATION_PROBABILITY
        and combined.effect_label == "significant_increase"
        and single_is_weaker(a_alone, a_only)
        and single_is_weaker(b_alone, b_only)
    )

    emit(
        on_event,
        TrialEvent(
            kind="verdict",
            phase="interaction",
            condition=both_label,
            is_significant=combined.is_significant,
            p_value=combined.p_value,
            extra={
                "interaction_confirmed": interaction_confirmed,
                "interaction_probability": prob,
                "excess_failure_rate": excess,
                "single_rates": {label_a: a_only.failure_rate, label_b: b_only.failure_rate},
                "combined_rate": both.failure_rate,
            },
        ),
    )
    emit(on_event, TrialEvent(kind="phase_done", phase="interaction"))

    return {
        "neither": neither,
        "a_only": a_only,
        "b_only": b_only,
        "both": both,
        "a_alone_comparison": a_alone,
        "b_alone_comparison": b_alone,
        "combined_comparison": combined,
        "interaction_probability": prob,
        "excess_failure_rate": excess,
        "interaction_confirmed": interaction_confirmed,
    }


def run_experiment(
    baseline_run_fn: RunFn,
    candidates: dict[str, RunFn],
    n: int = 5,
    *,
    alpha: float = SIGNIFICANCE_LEVEL,
    on_event: OnEvent | None = None,
) -> ExperimentResult:
    """End-to-end single-variable isolation: baseline + each candidate, picks the
    strongest significant condition (smallest adjusted p, then highest failure
    rate), and classifies the failure."""
    baseline, comparisons = isolate_variables(
        baseline_run_fn, candidates, n, alpha=alpha, on_event=on_event
    )
    warnings: list[str] = []
    warning = small_sample_warning(n, len(candidates), alpha)
    if warning:
        warnings.append(warning)

    increases = [c for c in comparisons if c.effect_label == "significant_increase"]
    strongest = min(
        increases,
        key=lambda c: (c.p_value_adjusted if c.p_value_adjusted is not None else c.p_value,
                       -c.treatment_failure_rate),
        default=None,
    )

    k = len(comparisons)
    family = f" (K={k} candidates, family-wise error controlled at alpha={alpha:g} by Holm)" if k > 1 else ""
    if strongest is None:
        classification = APPLICATION_INTERNAL if baseline_is_internally_flaky(baseline) else NO_EFFECT
        strongest_condition = "none"
        summary = (
            "No candidate condition produced a statistically significant increase "
            f"in failures{family}."
        )
    else:
        treatment_batch = strongest.treatment or TrialBatch(
            condition_label=strongest.condition_label,
            total_runs=strongest.treatment_total,
            failures=strongest.treatment_failures,
        )
        classification = classify_failure(baseline, treatment_batch, strongest.is_significant)
        strongest_condition = strongest.condition_label
        p_text = f"one-sided p={strongest.p_value:.4g}"
        if k > 1 and strongest.p_value_adjusted is not None:
            p_text += f", Holm-adjusted p={strongest.p_value_adjusted:.4g}"
        rd = strongest.risk_difference or 0.0
        ci = strongest.risk_difference_ci
        ci_text = f", risk difference {rd:+.2f} (95% CI {ci[0]:+.2f} to {ci[1]:+.2f})" if ci else ""
        summary = (
            f"Baseline failed {baseline.failures}/{baseline.total_runs} runs; "
            f"'{strongest_condition}' failed {strongest.treatment_failures}/{strongest.treatment_total} "
            f"({p_text}{ci_text}){family}."
        )
    if warnings:
        summary = "WARNING: " + " ".join(warnings) + " " + summary

    emit(
        on_event,
        TrialEvent(
            kind="verdict",
            phase="isolation",
            classification=classification,
            strongest_condition=strongest_condition,
            p_value=strongest.p_value if strongest else None,
            is_significant=strongest.is_significant if strongest else None,
            extra={"summary": summary, "warnings": warnings, "n": n, "alpha": alpha},
        ),
    )

    return ExperimentResult(
        baseline=baseline,
        comparisons=comparisons,
        classification=classification,
        strongest_condition=strongest_condition,
        summary=summary,
        warnings=warnings,
    )
