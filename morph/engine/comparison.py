"""Statistical comparison: does a treatment fail more often than baseline?

Fisher's exact test is appropriate for the small trial counts an experiment
loop actually runs (each cell is a handful of runs). The hypothesis Morph asks
is directional -- "this condition makes the application fail MORE" -- so the
decision uses the one-sided test (``alternative="greater"`` on the odds that
the treatment row fails). The mirror-image one-sided test labels a
``significant_decrease`` for fix verification. One-sided p-values are roughly
half the two-sided ones at small n: 0/5 vs 4/5 is p = 0.024 rather than 0.048.

Alongside the p-value every comparison reports the risk difference
(treatment rate - baseline rate) with a 95 % Newcombe hybrid-score interval
(Newcombe 1998, *Statistics in Medicine* 17:873-890, method 10), built from
Wilson score intervals on each rate. That interval is what a UI should draw:
it says how big the effect is, not only whether it exists.

Also here: Holm's step-down adjustment (Holm 1979, *Scand. J. Statist.*
6:65-70) for the K candidate comparisons one experiment runs, and the smallest
n at which perfect separation can reach significance at all.
"""

from __future__ import annotations

from math import comb, sqrt

from scipy.stats import fisher_exact, norm

from morph.schema.comparison import ComparisonResult

SIGNIFICANCE_LEVEL = 0.05


def wilson_interval(failures: int, total: int, confidence: float = 0.95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion; (0, 0) for an empty batch."""
    if total <= 0:
        return (0.0, 0.0)
    if not 0 <= failures <= total:
        raise ValueError(f"need 0 <= failures <= total, got {failures}/{total}")
    z = float(norm.ppf(1.0 - (1.0 - confidence) / 2.0))
    p = failures / total
    denom = 1.0 + z * z / total
    centre = (p + z * z / (2.0 * total)) / denom
    half = z * sqrt(p * (1.0 - p) / total + z * z / (4.0 * total * total)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def newcombe_risk_difference_ci(
    baseline_failures: int,
    baseline_total: int,
    treatment_failures: int,
    treatment_total: int,
    confidence: float = 0.95,
) -> tuple[float, float] | None:
    """Newcombe hybrid-score CI for ``treatment rate - baseline rate``.

    ``None`` when either batch is empty (no rate to compare).
    """
    if baseline_total <= 0 or treatment_total <= 0:
        return None
    p_t = treatment_failures / treatment_total
    p_b = baseline_failures / baseline_total
    l_t, u_t = wilson_interval(treatment_failures, treatment_total, confidence)
    l_b, u_b = wilson_interval(baseline_failures, baseline_total, confidence)
    d = p_t - p_b
    lower = d - sqrt((p_t - l_t) ** 2 + (u_b - p_b) ** 2)
    upper = d + sqrt((u_t - p_t) ** 2 + (p_b - l_b) ** 2)
    return (max(-1.0, lower), min(1.0, upper))


def compare_failure_rates(
    condition_label: str,
    baseline_failures: int,
    baseline_total: int,
    treatment_failures: int,
    treatment_total: int,
    *,
    alpha: float = SIGNIFICANCE_LEVEL,
) -> ComparisonResult:
    """One-sided Fisher exact tests of a treatment against the baseline.

    ``p_value`` is P(data at least this extreme | H0) for H1 "treatment fails
    more"; ``p_value_decrease`` for H1 "treatment fails less". The effect label
    is ``significant_increase`` when the first is below ``alpha``,
    ``significant_decrease`` when only the second is, else ``no_effect``.
    """
    for name, value in (
        ("baseline_failures", baseline_failures), ("baseline_total", baseline_total),
        ("treatment_failures", treatment_failures), ("treatment_total", treatment_total),
    ):
        if value < 0:
            raise ValueError(f"{name} must be >= 0, got {value}")
    if baseline_failures > baseline_total or treatment_failures > treatment_total:
        raise ValueError("failures cannot exceed total")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    # Treatment row first, so alternative="greater" tests "treatment odds of
    # failure exceed baseline's".
    table = [
        [treatment_failures, treatment_total - treatment_failures],
        [baseline_failures, baseline_total - baseline_failures],
    ]
    _, p_increase = fisher_exact(table, alternative="greater")
    _, p_decrease = fisher_exact(table, alternative="less")
    p_increase, p_decrease = float(p_increase), float(p_decrease)

    if p_increase < alpha:
        effect_label, is_significant = "significant_increase", True
    elif p_decrease < alpha:
        effect_label, is_significant = "significant_decrease", True
    else:
        effect_label, is_significant = "no_effect", False

    baseline_rate = baseline_failures / baseline_total if baseline_total else 0.0
    treatment_rate = treatment_failures / treatment_total if treatment_total else 0.0

    return ComparisonResult(
        condition_label=condition_label,
        baseline_failures=baseline_failures,
        baseline_total=baseline_total,
        treatment_failures=treatment_failures,
        treatment_total=treatment_total,
        p_value=p_increase,
        p_value_decrease=p_decrease,
        is_significant=bool(is_significant),
        effect_label=effect_label,
        method="fisher",
        alpha=alpha,
        risk_difference=treatment_rate - baseline_rate,
        risk_difference_ci=newcombe_risk_difference_ci(
            baseline_failures, baseline_total, treatment_failures, treatment_total
        ),
    )


def holm_adjust(p_values: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order.

    Rejecting every hypothesis whose adjusted p is below alpha controls the
    family-wise error rate at alpha with no independence assumption.
    """
    k = len(p_values)
    if k == 0:
        return []
    order = sorted(range(k), key=lambda i: p_values[i])
    adjusted = [0.0] * k
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, (k - rank) * p_values[idx])
        adjusted[idx] = min(1.0, running)
    return adjusted


def apply_holm(
    comparisons: list[ComparisonResult], alpha: float = SIGNIFICANCE_LEVEL
) -> list[ComparisonResult]:
    """Holm-adjust the increase p-values of one experiment's candidate comparisons.

    With two or more candidates, sets ``p_value_adjusted``, ``method =
    "fisher_holm"`` and re-derives ``is_significant`` / ``effect_label`` from
    the adjusted p. A ``significant_decrease`` label is left as the raw
    one-sided test found it: it is not part of the "does it increase" family.
    With a single candidate nothing changes (Holm is the identity).
    """
    if len(comparisons) < 2:
        return [c.model_copy(update={"p_value_adjusted": c.p_value}) for c in comparisons]
    raw = [c.p_value if c.p_value is not None else 1.0 for c in comparisons]
    adjusted = holm_adjust(raw)
    out: list[ComparisonResult] = []
    for cmp, p_adj in zip(comparisons, adjusted, strict=True):
        if p_adj < alpha:
            label, sig = "significant_increase", True
        elif cmp.effect_label == "significant_decrease":
            label, sig = "significant_decrease", True
        else:
            label, sig = "no_effect", False
        out.append(cmp.model_copy(update={
            "p_value_adjusted": p_adj,
            "method": "fisher_holm",
            "alpha": alpha,
            "is_significant": sig,
            "effect_label": label,
        }))
    return out


def minimum_trials_for_significance(
    alpha: float = SIGNIFICANCE_LEVEL, hypotheses: int = 1, *, one_sided: bool = True
) -> int:
    """Smallest n per arm at which even perfect separation (0/n vs n/n) can be
    significant. Below this, an experiment can only ever say "no effect".

    With perfect separation the one-sided Fisher p is 1 / C(2n, n) (two-sided:
    twice that). ``hypotheses`` accounts for Holm across K candidates, whose
    smallest p must clear alpha / K.
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")
    bar = alpha / max(1, hypotheses)
    n = 1
    while True:
        p = (1.0 if one_sided else 2.0) / comb(2 * n, n)
        if p < bar:
            return n
        n += 1
