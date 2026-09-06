"""Statistical comparison: is a treatment's failure rate significantly different
from baseline? Fisher's exact test is appropriate for the small trial counts a
hackathon-scale experiment loop actually runs (each cell is a handful of runs)."""

from scipy.stats import fisher_exact

from morph.schema.comparison import ComparisonResult

SIGNIFICANCE_LEVEL = 0.05


def compare_failure_rates(
    condition_label: str,
    baseline_failures: int,
    baseline_total: int,
    treatment_failures: int,
    treatment_total: int,
) -> ComparisonResult:
    table = [
        [baseline_failures, baseline_total - baseline_failures],
        [treatment_failures, treatment_total - treatment_failures],
    ]
    _, p_value = fisher_exact(table)

    baseline_rate = baseline_failures / baseline_total if baseline_total else 0.0
    treatment_rate = treatment_failures / treatment_total if treatment_total else 0.0
    is_significant = p_value < SIGNIFICANCE_LEVEL

    if not is_significant:
        effect_label = "no_effect"
    elif treatment_rate > baseline_rate:
        effect_label = "significant_increase"
    else:
        effect_label = "significant_decrease"

    return ComparisonResult(
        condition_label=condition_label,
        baseline_failures=baseline_failures,
        baseline_total=baseline_total,
        treatment_failures=treatment_failures,
        treatment_total=treatment_total,
        p_value=p_value,
        is_significant=is_significant,
        effect_label=effect_label,
    )
