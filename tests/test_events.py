"""The engine's optional `on_event` progress hook.

Covers: event sequencing, the statistical-honesty guarantee (no p-value on
per-trial events), RunResult-returning trial callbacks, threshold search
probes, and that omitting `on_event` changes nothing.
"""

from __future__ import annotations

from morph.engine.experiment import detect_interaction, run_experiment, run_trials
from morph.engine.threshold import search_threshold
from morph.schema.events import TrialEvent
from morph.schema.telemetry import RunResult


def _collector() -> tuple[list[TrialEvent], callable]:
    events: list[TrialEvent] = []
    return events, events.append


def test_run_trials_emits_start_trials_and_done():
    events, on_event = _collector()
    batch = run_trials(lambda: True, 5, "baseline", on_event=on_event)

    kinds = [e.kind for e in events]
    assert kinds == ["condition_start"] + ["trial"] * 5 + ["condition_done"]
    assert batch.failures == 0

    trials = [e for e in events if e.kind == "trial"]
    assert [t.trial_index for t in trials] == [0, 1, 2, 3, 4]
    assert all(t.total == 5 for t in trials)
    assert all(t.passed is True for t in trials)
    assert [t.failures_so_far for t in trials] == [0, 0, 0, 0, 0]

    done = events[-1]
    assert done.kind == "condition_done"
    assert done.failures == 0
    assert done.failure_rate == 0.0


def test_per_trial_events_never_carry_a_p_value():
    """The optional-stopping guard: significance is only ever computed once,
    over a full fixed-size batch -- never mid-stream."""
    events, on_event = _collector()
    flip = iter([True, False, False, True, False])
    run_experiment(
        baseline_run_fn=lambda: True,
        candidates={"cond": lambda: next(flip)},
        n=5,
        on_event=on_event,
    )
    for e in events:
        if e.kind == "trial":
            assert e.p_value is None
            assert e.is_significant is None
        if e.kind == "comparison":
            assert e.p_value is not None


def test_run_trials_accepts_runresult_and_keeps_it():
    events, on_event = _collector()

    def run_fn() -> RunResult:
        return RunResult(
            exit_code=1, passed=False, stdout="hello out",
            stderr="Traceback...\nValueError: boom", duration_ms=12.5,
            error_type="ValueError",
        )

    batch = run_trials(run_fn, 3, "cond", on_event=on_event)
    assert batch.failures == 3
    assert len(batch.run_results) == 3

    trial = next(e for e in events if e.kind == "trial")
    assert trial.passed is False
    assert trial.error_type == "ValueError"
    assert trial.stderr_tail is not None and "boom" in trial.stderr_tail
    assert trial.stdout_tail == "hello out"
    assert trial.duration_ms == 12.5


def test_run_experiment_emits_phase_comparison_and_verdict():
    events, on_event = _collector()
    always_fail = {"bad_condition": lambda: False}
    result = run_experiment(
        baseline_run_fn=lambda: True, candidates=always_fail, n=6, on_event=on_event
    )

    kinds = [e.kind for e in events]
    assert kinds[0] == "phase_start"
    assert "comparison" in kinds
    assert kinds[-1] == "verdict"

    comparison = next(e for e in events if e.kind == "comparison")
    assert comparison.condition == "bad_condition"
    assert comparison.p_value is not None
    assert comparison.is_significant is True

    verdict = events[-1]
    assert verdict.classification == result.classification == "environment_caused"
    assert verdict.strongest_condition == "bad_condition"
    assert verdict.extra.get("summary")


def test_detect_interaction_emits_events_and_matches_return():
    events, on_event = _collector()
    out = detect_interaction(
        run_neither=lambda: True,
        run_a=lambda: True,
        run_b=lambda: True,
        run_both=lambda: False,
        label_a="latency",
        label_b="loss",
        n=6,
        on_event=on_event,
    )
    assert out["interaction_confirmed"] is True

    verdict = next(e for e in events if e.kind == "verdict")
    assert verdict.extra.get("interaction_confirmed") is True
    assert verdict.condition == "latency+loss"
    kinds = [e.kind for e in events]
    assert kinds[0] == "phase_start"
    assert kinds[-1] == "phase_done"


def test_search_threshold_emits_probes_and_final_bracket():
    events, on_event = _collector()

    # Passes below 180, fails at/above it.
    result = search_threshold(
        parameter="network.latency_ms",
        run_at=lambda v: v < 180.0,
        low=0.0,
        high=500.0,
        trials=3,
        precision=5.0,
        on_event=on_event,
    )

    probes = [e for e in events if e.kind == "search_probe"]
    assert probes, "expected at least one search_probe event"
    assert all(p.param_value is not None for p in probes)
    assert all(p.total == 3 for p in probes)

    done = events[-1]
    assert done.kind == "phase_done"
    assert done.phase == "threshold"
    assert done.boundary_estimate == result.boundary_estimate
    assert abs(result.boundary_estimate - 180.0) <= 10.0


def test_no_on_event_is_unchanged():
    """Omitting on_event must not alter results."""
    with_hook = run_experiment(
        baseline_run_fn=lambda: True,
        candidates={"c": lambda: False},
        n=8,
        on_event=lambda _e: None,
    )
    without_hook = run_experiment(
        baseline_run_fn=lambda: True,
        candidates={"c": lambda: False},
        n=8,
    )
    assert with_hook.classification == without_hook.classification
    assert with_hook.strongest_condition == without_hook.strongest_condition
    assert without_hook.baseline.run_results == []
