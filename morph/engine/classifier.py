"""Causal classification: distinguishes an application bug from a failure that
is genuinely introduced or merely amplified by an environmental condition."""

from morph.engine.comparison import wilson_interval
from morph.schema.trials import TrialBatch

# The baseline is "internally flaky" when the LOWER bound of the 95 % Wilson
# interval on its failure rate exceeds this -- i.e. we are confident it fails
# more than 10 % of the time regardless of environment. A point estimate would
# call 1/5 (rate 0.20, CI 0.01-0.62) an application bug on one bad run.
BASELINE_INTERNAL_FAILURE_THRESHOLD = 0.10

ENVIRONMENT_CAUSED = "environment_caused"
ENVIRONMENT_EXPOSED = "environment_exposed"
APPLICATION_INTERNAL = "application_internal"
NO_EFFECT = "no_effect"


def baseline_is_internally_flaky(baseline: TrialBatch) -> bool:
    """True when the baseline's failure rate is confidently above the threshold."""
    lower, _ = wilson_interval(baseline.failures, baseline.total_runs)
    return lower > BASELINE_INTERNAL_FAILURE_THRESHOLD


def classify_failure(baseline: TrialBatch, treatment: TrialBatch, is_significant: bool) -> str:
    """
    application_internal: baseline already fails often (Wilson lower bound
                          above 10 %), regardless of environment.
    environment_caused:   baseline never failed, treatment significantly worse.
    environment_exposed:  baseline has some (low) failures, treatment amplifies them.
    no_effect:            treatment did not significantly increase the failure rate.
    """
    if baseline_is_internally_flaky(baseline):
        return APPLICATION_INTERNAL

    if not is_significant or treatment.failure_rate <= baseline.failure_rate:
        return NO_EFFECT

    if baseline.failures > 0:
        return ENVIRONMENT_EXPOSED

    return ENVIRONMENT_CAUSED
