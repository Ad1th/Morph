"""Minimal failing condition set via delta debugging over conditions.

Given a set of named environmental conditions whose combination makes the
application fail, ``ddmin`` (Zeller & Hildebrandt 2002, "Simplifying and
isolating failure-inducing input", *IEEE TSE* 28(2)) finds a *1-minimal*
subset: one that still fails, and from which removing any single condition
makes it pass. That is the README's promised "minimal condition set that
reproduces it" -- e.g. ``{latency_ms, packet_loss_percent}`` out of five
deviating fields.

The oracle ``fails(subset) -> bool`` is the caller's; for a flaky target build
it with :func:`batch_oracle`, which runs a small batch under each subset and
applies a failure-rate threshold, so one lucky pass does not derail the search.
Results are memoised, so ``oracle_calls`` counts distinct subsets evaluated.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field

from morph.engine.progress import RunFn, run_valid_trial

Oracle = Callable[[frozenset[str]], bool]


@dataclass
class MinimizeResult:
    """Outcome of :func:`ddmin`.

    ``reproduced`` is False when the full set did not fail (then ``minimal``
    is empty and nothing was minimised). ``history`` lists every distinct
    subset evaluated with the oracle's answer, in order.
    """

    minimal: frozenset[str]
    reproduced: bool
    oracle_calls: int
    history: list[tuple[frozenset[str], bool]] = field(default_factory=list)


def ddmin(conditions: Iterable[str], fails: Oracle) -> MinimizeResult:
    """Return a 1-minimal subset of ``conditions`` for which ``fails`` is True.

    Assumes ``fails(frozenset())`` is False (the baseline passes) and checks
    ``fails(all)`` first; if the full set does not fail there is nothing to
    minimise. Order of ``conditions`` only affects which of several equally
    minimal answers is found.
    """
    items = list(dict.fromkeys(conditions))
    cache: dict[frozenset[str], bool] = {}
    history: list[tuple[frozenset[str], bool]] = []

    def test(subset: list[str]) -> bool:
        key = frozenset(subset)
        if key not in cache:
            cache[key] = bool(fails(key))
            history.append((key, cache[key]))
        return cache[key]

    if not items or not test(items):
        return MinimizeResult(frozenset(), False, len(cache), history)

    current = items
    n = 2
    while len(current) >= 2:
        chunk = max(1, len(current) // n)
        subsets = [current[i:i + chunk] for i in range(0, len(current), chunk)]
        if len(subsets) > n:  # merge the remainder into the last chunk
            subsets[n - 1:] = [list(itertools.chain.from_iterable(subsets[n - 1:]))]
        reduced = False
        for subset in subsets:  # reduce to subset
            if len(subset) < len(current) and test(subset):
                current, n, reduced = subset, 2, True
                break
        if reduced:
            continue
        if len(subsets) > 1:
            for subset in subsets:  # reduce to complement
                complement = [c for c in current if c not in subset]
                if complement and test(complement):
                    current, n, reduced = complement, max(n - 1, 2), True
                    break
        if reduced:
            continue
        if n >= len(current):
            break
        n = min(len(current), 2 * n)

    return MinimizeResult(frozenset(current), True, len(cache), history)


def batch_oracle(
    run_fn_for: Callable[[frozenset[str]], RunFn],
    *,
    runs: int = 3,
    failure_rate_threshold: float = 0.5,
) -> Oracle:
    """Build a ``fails(subset)`` oracle for a possibly flaky target.

    ``run_fn_for(subset)`` returns a zero-argument trial callback that runs the
    application with exactly those conditions applied. The oracle runs it
    ``runs`` times and answers "fails" when the failure rate is strictly above
    ``failure_rate_threshold`` -- the same majority rule as the threshold
    search, so a single unlucky run does not count as a failure. A trial the
    runtime reports as invalid is retried and, if it stays invalid, raises
    :class:`~morph.engine.errors.InvalidTrialError`.
    """
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")
    if not 0.0 <= failure_rate_threshold < 1.0:
        raise ValueError("failure_rate_threshold must be in [0, 1)")

    def fails(subset: frozenset[str]) -> bool:
        run_fn = run_fn_for(subset)
        label = "+".join(sorted(subset)) or "none"
        failures = 0
        for i in range(runs):
            passed, _result, _ms = run_valid_trial(run_fn, label, None, trial_index=i, total=runs)
            if not passed:
                failures += 1
        return failures / runs > failure_rate_threshold

    return fails
