"""Causal classification: distinguishes an application bug from a failure that
is genuinely introduced or merely amplified by an environmental condition."""

from morph.schema.experiment import TrialBatch

BASELINE_INTERNAL_FAILURE_THRESHOLD = 0.10
EXPOSED_MIN_BASELINE_RATE = 0.0

ENVIRONMENT_CAUSED = "environment_caused"
ENVIRONMENT_EXPOSED = "environment_exposed"
APPLICATION_INTERNAL = "application_internal"
NO_EFFECT = "no_effect"


def classify_failure(baseline: TrialBatch, treatment: TrialBatch, is_significant: bool) -> str:
    """
    application_internal: baseline already fails often, regardless of environment.
    environment_caused:   baseline near 0% failures, treatment significantly worse.
    environment_exposed:  baseline has some (low) failures, treatment amplifies them.
    no_effect:            treatment did not significantly change the failure rate.
    """
    if baseline.failure_rate > BASELINE_INTERNAL_FAILURE_THRESHOLD:
        return APPLICATION_INTERNAL

    if not is_significant:
        return NO_EFFECT

    if baseline.failure_rate > EXPOSED_MIN_BASELINE_RATE:
        return ENVIRONMENT_EXPOSED

    return ENVIRONMENT_CAUSED
