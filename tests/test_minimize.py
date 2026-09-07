"""ddmin over named conditions: 1-minimal failing subsets from a boolean or
flaky oracle."""

from __future__ import annotations

import itertools
import random

import pytest

from morph.engine.errors import InvalidTrialError
from morph.engine.minimize import MinimizeResult, batch_oracle, ddmin
from morph.schema.telemetry import RunResult

CONDITIONS = ["cpu", "ram", "locale", "latency_ms", "packet_loss_percent"]


def _is_one_minimal(minimal: frozenset[str], fails) -> bool:
    return fails(minimal) and all(not fails(minimal - {c}) for c in minimal)


def test_single_culprit():
    fails = lambda s: "latency_ms" in s  # noqa: E731
    result = ddmin(CONDITIONS, fails)
    assert isinstance(result, MinimizeResult)
    assert result.minimal == frozenset({"latency_ms"})
    assert result.reproduced is True
    assert result.oracle_calls == len(result.history) <= 8


def test_pair_interaction_is_found_and_is_1_minimal():
    fails = lambda s: {"latency_ms", "packet_loss_percent"} <= s  # noqa: E731
    result = ddmin(CONDITIONS, fails)
    assert result.minimal == frozenset({"latency_ms", "packet_loss_percent"})
    assert _is_one_minimal(result.minimal, fails)
    assert result.history[0] == (frozenset(CONDITIONS), True)


def test_no_failure_means_nothing_to_minimise():
    result = ddmin(CONDITIONS, lambda s: False)
    assert result.minimal == frozenset()
    assert result.reproduced is False
    assert result.oracle_calls == 1
    assert ddmin([], lambda s: True).reproduced is False


def test_every_subset_of_five_conditions_is_minimised_correctly():
    for k in range(1, 4):
        for culprits in itertools.combinations(CONDITIONS, k):
            need = frozenset(culprits)
            fails = lambda s, need=need: need <= s  # noqa: E731
            result = ddmin(CONDITIONS, fails)
            assert result.minimal == need, culprits
            assert result.oracle_calls <= 2 ** len(CONDITIONS)


def test_disjunctive_failure_returns_one_minimal_cause():
    fails = lambda s: "cpu" in s or "ram" in s  # noqa: E731
    result = ddmin(CONDITIONS, fails)
    assert result.minimal in (frozenset({"cpu"}), frozenset({"ram"}))
    assert _is_one_minimal(result.minimal, fails)


def test_oracle_is_memoised():
    seen: list[frozenset[str]] = []

    def fails(s: frozenset[str]) -> bool:
        seen.append(s)
        return "ram" in s

    result = ddmin(CONDITIONS, fails)
    assert len(seen) == len(set(seen)) == result.oracle_calls


def test_batch_oracle_uses_a_majority_rule_on_a_flaky_target():
    rng = random.Random(7)

    def run_fn_for(subset: frozenset[str]):
        p_fail = 0.9 if {"latency_ms", "packet_loss_percent"} <= subset else 0.1
        return lambda: rng.random() >= p_fail  # True == passed

    fails = batch_oracle(run_fn_for, runs=5)
    result = ddmin(CONDITIONS, fails)
    assert result.minimal == frozenset({"latency_ms", "packet_loss_percent"})


def test_batch_oracle_threshold_and_validation():
    fails = batch_oracle(lambda s: (lambda: False), runs=3, failure_rate_threshold=0.5)
    assert fails(frozenset({"x"})) is True
    passes = batch_oracle(lambda s: (lambda: True), runs=3)
    assert passes(frozenset({"x"})) is False
    with pytest.raises(ValueError):
        batch_oracle(lambda s: (lambda: True), runs=0)
    with pytest.raises(ValueError):
        batch_oracle(lambda s: (lambda: True), failure_rate_threshold=1.0)


def test_batch_oracle_propagates_invalid_trials():
    class Invalid(RunResult):
        invalid: bool = True
        invalid_reason: str | None = "exit 126"

    fails = batch_oracle(lambda s: (lambda: Invalid(exit_code=126, passed=False)), runs=2)
    with pytest.raises(InvalidTrialError):
        fails(frozenset({"cpu"}))
