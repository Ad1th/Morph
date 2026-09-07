"""morph.engine.anytime: exact paired e-values and their anytime validity."""

import random
from math import comb, isclose

import pytest

from morph.engine.anytime import PairedEvidence, anytime_p_value, e_value, log_e_value


def test_no_discordant_pairs_is_no_evidence():
    assert log_e_value(0, 0) == 0.0
    assert e_value(0, 0) == 1.0


def test_two_sided_e_value_matches_beta_binomial_closed_form():
    # Uniform mixture: E = 2^m * B(k+1, m-k+1) = 2^m / ((m+1) * C(m, k)).
    for m in range(1, 12):
        for k in range(m + 1):
            expected = 2**m / ((m + 1) * comb(m, k))
            assert isclose(e_value(k, m, one_sided=False), expected, rel_tol=1e-9)


def test_two_sided_e_value_has_expectation_one_under_the_null():
    # Under H0 each discordant pair is a fair coin: E[E_m] must equal 1 exactly.
    for m in range(1, 15):
        total = sum(comb(m, k) * 0.5**m * e_value(k, m, one_sided=False) for k in range(m + 1))
        assert isclose(total, 1.0, rel_tol=1e-9)


def test_one_sided_e_value_has_expectation_at_most_one_under_the_null():
    for m in range(1, 15):
        total = sum(comb(m, k) * 0.5**m * e_value(k, m, one_sided=True) for k in range(m + 1))
        assert total <= 1.0 + 1e-9


def test_one_sided_evidence_grows_with_treatment_failures_and_shrinks_otherwise():
    assert e_value(6, 6) > e_value(5, 6) > e_value(3, 6) > e_value(0, 6)
    assert e_value(0, 6) < 1.0


def test_invalid_counts_rejected():
    with pytest.raises(ValueError):
        log_e_value(3, 2)
    with pytest.raises(ValueError):
        log_e_value(-1, 2)


def test_anytime_p_value():
    assert anytime_p_value(0.0) == 1.0
    assert anytime_p_value(0.5) == 1.0
    assert isclose(anytime_p_value(20.0), 0.05)


def test_paired_evidence_bookkeeping_and_decision():
    ev = PairedEvidence("x")
    ev.update(True, True)  # both pass: ignored
    ev.update(False, False)  # both fail: ignored
    assert ev.discordant == 0 and ev.e_value == 1.0
    for _ in range(6):
        ev.update(True, False)
    assert ev.pairs == 8 and ev.discordant == 6 and ev.treatment_worse == 6
    assert ev.e_value == pytest.approx(e_value(6, 6))
    assert not ev.decisive(0.05)  # E(6 of 6) = 18.1 < 20: one more discordant pair needed
    ev.update(True, False)
    assert ev.decisive(0.05)
    assert ev.threshold(0.05, hypotheses=3) == 60.0


def test_paired_evidence_six_of_six_is_borderline_for_alpha_005():
    # E(6/6, one-sided uniform) = 2^6 * B(7,1) * 2 * (1 - 2^-7)... = 18.14: honest
    # about needing one more discordant pair, unlike Fisher on 6 vs 0 (p = 0.0022).
    assert 18.0 < e_value(6, 6) < 19.0
    assert e_value(7, 7) > 20.0


def test_type_one_error_is_controlled_under_continuous_monitoring():
    rng = random.Random(2024)
    alpha, pairs, sims = 0.05, 40, 1500
    false_positives = 0
    for _ in range(sims):
        ev = PairedEvidence("h0")
        for _ in range(pairs):
            ev.update(rng.random() > 0.3, rng.random() > 0.3)
            if ev.decisive(alpha):
                false_positives += 1
                break
    # Ville's inequality: <= alpha at any stopping rule. Allow Monte Carlo slack.
    assert false_positives / sims < alpha + 0.015


def test_power_against_a_real_effect():
    rng = random.Random(7)
    decided = 0
    for _ in range(300):
        ev = PairedEvidence("h1")
        for _ in range(30):
            ev.update(rng.random() > 0.05, rng.random() > 0.7)
            if ev.decisive(0.05):
                decided += 1
                break
    assert decided / 300 > 0.95
