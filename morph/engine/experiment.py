"""Experiment loop: baseline/treatment trial runner, single-variable isolation,
and two-variable interaction detection.

Trials are driven by a caller-supplied ``run_fn`` callback rather than a real
subprocess, so the engine is testable without a target application or the
runtime controller wired up. ``run_fn`` may return a plain ``bool`` (passed) or
a full ``RunResult`` -- the latter lets progress events carry stdout/stderr and
timing for a live UI.

Every function takes an optional keyword ``on_event``. When supplied, the engine
emits :class:`~morph.schema.events.TrialEvent` objects as it goes. Default is
``None`` -- behaviour and return values are then byte-for-byte identical to
before this hook existed.
"""

import time
from collections.abc import Callable

from morph.engine.classifier import classify_failure
from morph.engine.comparison import compare_failure_rates
from morph.engine.progress import TAIL_CHARS, OnEvent, coerce_result, emit
from morph.schema.comparison import ComparisonResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult, TrialBatch
from morph.schema.telemetry import RunResult

RunFn = Callable[[], bool]  # may also return RunResult


def _tail(text: str | None) -> str | None:
    if not text:
        return None
    return text[-TAIL_CHARS:]


def run_trials(
    run_fn: RunFn,
    n: int,
    condition_label: str,
    profile_overrides: dict | None = None,
    *,
    on_event: OnEvent | None = None,
) -> TrialBatch:
    emit(on_event, TrialEvent(kind="condition_start", condition=condition_label, total=n))

    failures = 0
    run_results: list[RunResult] = []
    for i in range(n):
        start = time.perf_counter()
        raw = run_fn()
        elapsed_ms = (time.perf_counter() - start) * 1000.0

        passed, result = coerce_result(raw)
        if result is not None:
            run_results.append(result)
            if result.duration_ms:
                elapsed_ms = result.duration_ms
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
                stdout_tail=_tail(result.stdout) if result else None,
                stderr_tail=_tail(result.stderr) if result else None,
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


def compare_batches(baseline: TrialBatch, treatment: TrialBatch) -> ComparisonResult:
    return compare_failure_rates(
        treatment.condition_label,
        baseline.failures,
        baseline.total_runs,
        treatment.failures,
        treatment.total_runs,
    )


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
        ),
    )


def isolate_variables(
    baseline_run_fn: RunFn,
    candidates: dict[str, RunFn],
    n: int = 5,
    *,
    on_event: OnEvent | None = None,
) -> tuple[TrialBatch, list[ComparisonResult]]:
    """Runs a shared baseline, then each candidate variable's treatment, and
    compares each treatment against that baseline."""
    emit(on_event, TrialEvent(kind="phase_start", phase="isolation"))

    baseline = run_trials(baseline_run_fn, n, "baseline", on_event=on_event)
    comparisons: list[ComparisonResult] = []
    for label, run_fn in candidates.items():
        treatment = run_trials(run_fn, n, label, on_event=on_event)
        cmp = compare_batches(baseline, treatment)
        comparisons.append(cmp)
        _emit_comparison(on_event, treatment, cmp)

    emit(on_event, TrialEvent(kind="phase_done", phase="isolation"))
    return baseline, comparisons


def detect_interaction(
    run_neither: RunFn,
    run_a: RunFn,
    run_b: RunFn,
    run_both: RunFn,
    label_a: str,
    label_b: str,
    n: int = 5,
    *,
    on_event: OnEvent | None = None,
) -> dict:
    """Runs all four cells of a 2x2 design. An interaction is confirmed only
    when A alone and B alone show no effect but A+B does: this proves the
    failure depends on the combination, not either condition individually."""
    emit(on_event, TrialEvent(kind="phase_start", phase="interaction"))

    both_label = f"{label_a}+{label_b}"
    neither = run_trials(run_neither, n, "neither", on_event=on_event)
    a_only = run_trials(run_a, n, label_a, on_event=on_event)
    b_only = run_trials(run_b, n, label_b, on_event=on_event)
    both = run_trials(run_both, n, both_label, on_event=on_event)

    a_alone = compare_batches(neither, a_only)
    b_alone = compare_batches(neither, b_only)
    combined = compare_batches(neither, both)
    for treatment, cmp in ((a_only, a_alone), (b_only, b_alone), (both, combined)):
        _emit_comparison(on_event, treatment, cmp)

    interaction_confirmed = (
        a_alone.effect_label == "no_effect"
        and b_alone.effect_label == "no_effect"
        and combined.effect_label == "significant_increase"
    )

    emit(
        on_event,
        TrialEvent(
            kind="verdict",
            phase="interaction",
            condition=both_label,
            is_significant=combined.is_significant,
            p_value=combined.p_value,
            extra={"interaction_confirmed": interaction_confirmed},
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
        "interaction_confirmed": interaction_confirmed,
    }


def run_experiment(
    baseline_run_fn: RunFn,
    candidates: dict[str, RunFn],
    n: int = 5,
    *,
    on_event: OnEvent | None = None,
) -> ExperimentResult:
    """End-to-end single-variable isolation: baseline + each candidate, picks the
    strongest significant condition, and classifies the failure."""
    baseline, comparisons = isolate_variables(baseline_run_fn, candidates, n, on_event=on_event)

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

    emit(
        on_event,
        TrialEvent(
            kind="verdict",
            phase="isolation",
            classification=classification,
            strongest_condition=strongest_condition,
            p_value=strongest.p_value if strongest else None,
            is_significant=strongest.is_significant if strongest else None,
            extra={"summary": summary},
        ),
    )

    return ExperimentResult(
        baseline=baseline,
        comparisons=comparisons,
        classification=classification,
        strongest_condition=strongest_condition,
        summary=summary,
    )
