"""Sequential causal isolation: interleaved trials, anytime-valid stopping.

The batch engine in :mod:`morph.engine.experiment` runs N baseline trials, then
N trials per candidate condition, then tests once. This module runs the same
question as a *paired, round-robin* design:

    round 1:  baseline, cond A, cond B, cond C
    round 2:  baseline, cond C, cond A, cond B      (order rotates)
    ...

Every round pairs each candidate's trial with that round's baseline trial and
updates the candidate's e-process (:mod:`morph.engine.anytime`). A candidate
stops as soon as its e-value reaches ``K / alpha`` (K candidates sharing one
alpha keeps the family-wise error at alpha) or when the round budget runs out.

Two practical wins over the batch design, beyond honesty under live viewing:
the interleaving cancels host drift (both arms see the same slowly-changing
machine), and an obvious effect is settled in a handful of rounds instead of
a fixed 2N trials -- the flagship latency+loss fault decides in ~7 pairs.

Results come back as the same ``TrialBatch`` / ``ComparisonResult`` /
``ExperimentResult`` types the batch engine produces, so every consumer (CLI,
API, TUI, dashboard, regression export) works unchanged.
"""

from __future__ import annotations

from morph.engine.anytime import PairedEvidence
from morph.engine.classifier import (
    APPLICATION_INTERNAL,
    NO_EFFECT,
    baseline_is_internally_flaky,
    classify_failure,
)
from morph.engine.comparison import SIGNIFICANCE_LEVEL, compare_failure_rates
from morph.engine.progress import OnEvent, RunFn, emit, run_valid_trial, tail
from morph.schema.comparison import ComparisonResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult, TrialBatch
from morph.schema.telemetry import RunResult


class _Arm:
    """Accumulates one condition's trials and turns them into a TrialBatch."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.results: list[RunResult] = []
        self.outcomes: list[bool] = []

    @property
    def failures(self) -> int:
        return sum(1 for ok in self.outcomes if not ok)

    def batch(self) -> TrialBatch:
        return TrialBatch(
            condition_label=self.label,
            total_runs=len(self.outcomes),
            failures=self.failures,
            run_results=self.results,
        )


def _run_one(arm: _Arm, run_fn: RunFn, total: int, on_event: OnEvent | None) -> bool:
    passed, result, elapsed_ms = run_valid_trial(
        run_fn, arm.label, on_event, trial_index=len(arm.outcomes), total=total
    )
    if result is not None:
        arm.results.append(result)
    arm.outcomes.append(passed)
    emit(
        on_event,
        TrialEvent(
            kind="trial",
            condition=arm.label,
            trial_index=len(arm.outcomes) - 1,
            total=total,
            passed=passed,
            duration_ms=elapsed_ms,
            failures_so_far=arm.failures,
            error_type=result.error_type if result else None,
            stdout_tail=tail(result.stdout) if result else None,
            stderr_tail=tail(result.stderr) if result else None,
        ),
    )
    return passed


def run_sequential_experiment(
    baseline_run_fn: RunFn,
    candidates: dict[str, RunFn],
    max_rounds: int = 12,
    *,
    alpha: float = SIGNIFICANCE_LEVEL,
    min_rounds: int = 3,
    on_event: OnEvent | None = None,
) -> ExperimentResult:
    """Paired, round-robin isolation with anytime-valid early stopping.

    ``max_rounds`` bounds the trials per condition (and per baseline). A
    candidate is declared significant when its e-value reaches ``K/alpha``
    with K = number of candidates; it then stops consuming trials. Candidates
    that never get there run the full budget and are reported with their
    final e-value and anytime-valid p-value.
    """
    if not candidates:
        raise ValueError("at least one candidate condition is required")
    if max_rounds < 1:
        raise ValueError("max_rounds must be >= 1")
    labels = list(candidates)
    k = len(labels)
    baseline = _Arm("baseline")
    arms = {label: _Arm(label) for label in labels}
    evidence = {label: PairedEvidence(label) for label in labels}
    active = set(labels)
    stopped_early: dict[str, bool] = dict.fromkeys(labels, False)
    threshold = evidence[labels[0]].threshold(alpha, k)

    emit(on_event, TrialEvent(kind="phase_start", phase="isolation", extra={"mode": "sequential"}))
    emit(on_event, TrialEvent(kind="condition_start", condition="baseline", total=max_rounds))
    for label in labels:
        emit(on_event, TrialEvent(kind="condition_start", condition=label, total=max_rounds))

    for rnd in range(max_rounds):
        if not active:
            break
        base_ok = _run_one(baseline, baseline_run_fn, max_rounds, on_event)
        # Rotate the order so no condition always runs right after baseline.
        order = [labels[(i + rnd) % k] for i in range(k)]
        for label in order:
            if label not in active:
                continue
            ok = _run_one(arms[label], candidates[label], max_rounds, on_event)
            ev = evidence[label]
            ev.update(base_ok, ok)
            decisive = rnd + 1 >= min_rounds and ev.decisive(alpha, k)
            emit(
                on_event,
                TrialEvent(
                    kind="evidence",
                    condition=label,
                    e_value=ev.e_value,
                    evidence_threshold=threshold,
                    pairs=ev.pairs,
                    decisive=decisive,
                    p_value=ev.anytime_p,
                    failures=arms[label].failures,
                    failure_rate=arms[label].failures / len(arms[label].outcomes),
                    extra=ev.summary(),
                ),
            )
            if decisive:
                active.discard(label)
                stopped_early[label] = rnd + 1 < max_rounds

    baseline_batch = baseline.batch()
    emit(
        on_event,
        TrialEvent(
            kind="condition_done",
            condition="baseline",
            total=baseline_batch.total_runs,
            failures=baseline_batch.failures,
            failure_rate=baseline_batch.failure_rate,
        ),
    )

    comparisons: list[ComparisonResult] = []
    for label in labels:
        batch = arms[label].batch()
        ev = evidence[label]
        cmp = compare_failure_rates(
            label,
            baseline_batch.failures,
            baseline_batch.total_runs,
            batch.failures,
            batch.total_runs,
        )
        # The decision is the sequential one; Fisher's p on the final batch is
        # kept in `p_value_adjusted` purely for readers who want the familiar
        # number (it is NOT valid after optional stopping, and says so).
        significant = ev.decisive(alpha, k) and ev.pairs >= min_rounds
        cmp = cmp.model_copy(
            update={
                "method": "paired_e_value",
                "alpha": alpha,
                "treatment": batch,
                "e_value": ev.e_value,
                "pairs": ev.pairs,
                "stopped_early": stopped_early[label],
                "p_value": ev.anytime_p,
                "p_value_adjusted": cmp.p_value,
                "is_significant": significant,
                "effect_label": "significant_increase" if significant else "no_effect",
            }
        )
        comparisons.append(cmp)
        emit(
            on_event,
            TrialEvent(
                kind="condition_done",
                condition=label,
                total=batch.total_runs,
                failures=batch.failures,
                failure_rate=batch.failure_rate,
            ),
        )
        emit(
            on_event,
            TrialEvent(
                kind="comparison",
                condition=label,
                failures=batch.failures,
                failure_rate=batch.failure_rate,
                p_value=cmp.p_value,
                e_value=cmp.e_value,
                pairs=cmp.pairs,
                is_significant=cmp.is_significant,
                effect_label=cmp.effect_label,
                extra={"method": "paired_e_value", "stopped_early": stopped_early[label]},
            ),
        )

    emit(on_event, TrialEvent(kind="phase_done", phase="isolation"))

    increases = [c for c in comparisons if c.effect_label == "significant_increase"]
    strongest = max(increases, key=lambda c: (c.e_value or 0.0, c.treatment_failure_rate), default=None)
    if strongest is None:
        classification = APPLICATION_INTERNAL if baseline_is_internally_flaky(baseline_batch) else NO_EFFECT
        strongest_condition = "none"
        summary = (
            f"No candidate reached the evidence threshold (E >= {threshold:.0f}) "
            f"within {max_rounds} rounds."
        )
    else:
        treatment_batch = arms[strongest.condition_label].batch()
        classification = classify_failure(baseline_batch, treatment_batch, True)
        strongest_condition = strongest.condition_label
        summary = (
            f"Baseline failed {baseline_batch.failures}/{baseline_batch.total_runs}; "
            f"'{strongest_condition}' failed {strongest.treatment_failures}/{strongest.treatment_total} "
            f"(E = {strongest.e_value:.3g} after {strongest.pairs} pairs, "
            f"anytime p = {strongest.p_value:.3g})."
        )

    emit(
        on_event,
        TrialEvent(
            kind="verdict",
            phase="isolation",
            classification=classification,
            strongest_condition=strongest_condition,
            p_value=strongest.p_value if strongest else None,
            e_value=strongest.e_value if strongest else None,
            is_significant=strongest.is_significant if strongest else None,
            extra={"summary": summary, "mode": "sequential"},
        ),
    )
    return ExperimentResult(
        baseline=baseline_batch,
        comparisons=comparisons,
        classification=classification,
        strongest_condition=strongest_condition,
        summary=summary,
    )
