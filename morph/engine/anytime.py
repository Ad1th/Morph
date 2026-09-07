"""Anytime-valid evidence that a condition makes an application fail more often.

Why this exists
---------------
A fixed-size Fisher test is only honest if nobody looks at the p-value before
the last trial lands. Watching a p-value cross 0.05 live and stopping there is
optional stopping: it inflates the false-positive rate far above the nominal 5 %.
Morph's console *is* a live view, so it needs a statistic that stays valid no
matter when you stop looking.

E-values give exactly that guarantee. An e-process is a non-negative
supermartingale under the null with expectation 1, so by Ville's inequality

    P_H0( E_t >= 1/alpha  for some t )  <=  alpha.

Rejecting the moment the running e-value reaches 1/alpha therefore controls the
type-I error at *every* stopping time (Ramdas, Grünwald, Vovk & Shafer 2023;
Turner, Ly & Grünwald 2024 for 2x2 tables).

The design
----------
Trials are run in **matched pairs**: one baseline trial and one treatment
trial back to back, so slow drift on the host (thermal throttling, a backup
kicking in) hits both arms equally. Under H0 (equal failure probability) a
*discordant* pair -- exactly one of the two failed -- is equally likely to be
either way round, so the sequence "which arm failed" is an exact Bernoulli(1/2)
stream. That is a conditional test in the spirit of Fisher's, but sequential.
Concordant pairs (both pass / both fail) carry no information about the
difference and are simply skipped.

Against that fair-coin null we run Robbins' Beta-mixture likelihood ratio
(a "universal" test): with k treatment-failed pairs among m discordant ones,

    E_m  =  2^m * B(a+k, b+m-k) / B(a, b)

for a Beta(a, b) mixture over the alternative q = P(treatment is the failing
arm). One-sided (q >= 1/2, "treatment is worse") restricts the mixture to that
half of the prior. Both are computed in log-space below and stay exact for any
m -- no asymptotics, no simulation.

Reading the number: E = 20 means the data are 20x more likely under
"treatment fails more" than under "no difference". Reject H0 at level alpha
when E >= 1/alpha; an anytime-valid p-value is min(1, 1/E).
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp, inf, log

from scipy.special import betainc, betaln

LOG2 = log(2.0)
DEFAULT_PRIOR = (1.0, 1.0)  # uniform mixture over q, the classic Robbins choice


def log_e_value(
    treatment_worse: int,
    discordant: int,
    *,
    one_sided: bool = True,
    prior: tuple[float, float] = DEFAULT_PRIOR,
) -> float:
    """Natural log of the e-value after ``discordant`` discordant pairs, of which
    ``treatment_worse`` were "treatment failed, baseline passed".

    Exact for any pair count; returns 0.0 (E = 1, no evidence) when nothing
    discordant has been seen yet.
    """
    k, m = treatment_worse, discordant
    if m < 0 or k < 0 or k > m:
        raise ValueError(f"need 0 <= treatment_worse <= discordant, got {k}, {m}")
    if m == 0:
        return 0.0
    a, b = prior
    if a <= 0 or b <= 0:
        raise ValueError("prior parameters must be positive")

    log_e = m * LOG2 + betaln(a + k, b + m - k) - betaln(a, b)
    if one_sided:
        # Restrict the mixture to q >= 1/2. The posterior/prior tail masses use
        # the identity 1 - I_x(a, b) = I_{1-x}(b, a) so nothing underflows to 0
        # for moderate m (betainc is the regularized incomplete beta).
        tail_post = float(betainc(b + m - k, a + k, 0.5))
        tail_prior = float(betainc(b, a, 0.5))
        if tail_post <= 0.0:
            return -inf
        log_e += log(tail_post) - log(tail_prior)
    return float(log_e)


def e_value(treatment_worse: int, discordant: int, **kw) -> float:
    """The e-value itself; see :func:`log_e_value`."""
    return exp(log_e_value(treatment_worse, discordant, **kw))


def anytime_p_value(e: float) -> float:
    """An anytime-valid p-value: valid at every stopping time, unlike Fisher's."""
    if e <= 0.0:
        return 1.0
    return min(1.0, 1.0 / e)


@dataclass
class PairedEvidence:
    """Running evidence for one treatment against its interleaved baseline.

    Feed it one matched pair at a time with :meth:`update`; read ``e_value`` /
    ``anytime_p`` at any moment. ``decisive(alpha, hypotheses)`` applies a
    Bonferroni-style budget so several treatments can be tested against the
    same baseline with family-wise error still capped at ``alpha``.
    """

    label: str
    one_sided: bool = True
    prior: tuple[float, float] = DEFAULT_PRIOR

    pairs: int = 0
    discordant: int = 0
    treatment_worse: int = 0  # treatment failed, baseline passed
    baseline_worse: int = 0  # baseline failed, treatment passed
    both_failed: int = 0
    both_passed: int = 0
    log_e: float = 0.0

    def update(self, baseline_passed: bool, treatment_passed: bool) -> float:
        """Record one matched pair and return the new e-value."""
        self.pairs += 1
        if baseline_passed and not treatment_passed:
            self.discordant += 1
            self.treatment_worse += 1
        elif treatment_passed and not baseline_passed:
            self.discordant += 1
            self.baseline_worse += 1
        elif baseline_passed and treatment_passed:
            self.both_passed += 1
        else:
            self.both_failed += 1
        self.log_e = log_e_value(
            self.treatment_worse, self.discordant, one_sided=self.one_sided, prior=self.prior
        )
        return self.e_value

    @property
    def e_value(self) -> float:
        return exp(self.log_e) if self.log_e > -inf else 0.0

    @property
    def log10_e(self) -> float:
        """Evidence in decibans-friendly units: 1.3 means E = 20."""
        return self.log_e / log(10.0) if self.log_e > -inf else -inf

    @property
    def anytime_p(self) -> float:
        return anytime_p_value(self.e_value)

    def threshold(self, alpha: float, hypotheses: int = 1) -> float:
        """E-value needed to reject when ``hypotheses`` conditions share one alpha."""
        if not 0.0 < alpha < 1.0:
            raise ValueError("alpha must be in (0, 1)")
        return max(1, hypotheses) / alpha

    def decisive(self, alpha: float, hypotheses: int = 1) -> bool:
        return self.e_value >= self.threshold(alpha, hypotheses)

    def summary(self) -> dict:
        return {
            "label": self.label,
            "pairs": self.pairs,
            "discordant": self.discordant,
            "treatment_worse": self.treatment_worse,
            "baseline_worse": self.baseline_worse,
            "both_failed": self.both_failed,
            "both_passed": self.both_passed,
            "e_value": self.e_value,
            "log10_e": self.log10_e,
            "anytime_p": self.anytime_p,
        }
