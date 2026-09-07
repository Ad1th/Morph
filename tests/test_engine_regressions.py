"""Regression tests for the engine audit findings (C1-C11), the statistical
rigor changes (one-sided Fisher, Holm, CI-based classification), schema
hygiene (Literals, computed failure_rate, ThresholdResult.outcome, JSON
round-trips) and the invalid-trial convention."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from morph.engine.blame import analyze_differential_blame
from morph.engine.boundary import locate_boundary
from morph.engine.classifier import (
    APPLICATION_INTERNAL,
    ENVIRONMENT_EXPOSED,
    baseline_is_internally_flaky,
    classify_failure,
)
from morph.engine.errors import InvalidTrialError
from morph.engine.experiment import (
    detect_interaction,
    isolate_variables,
    run_experiment,
    run_trials,
)
from morph.engine.exporter import generate_invariant_test_code
from morph.engine.progress import coerce_result
from morph.engine.runners import set_profile_parameter
from morph.engine.sequential import run_sequential_experiment
from morph.engine.surface import boundary_pair
from morph.engine.threshold import search_threshold
from morph.engine.validator import check_cross_field_rules, check_thresholds, check_worker_required
from morph.schema.comparison import ComparisonResult, ThresholdResult
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult, TrialBatch
from morph.schema.profile import EnvironmentProfile, FieldStatus
from morph.schema.surface import SurfaceGridPoint
from morph.schema.telemetry import RunResult
from tests.test_schema import sample_profile_dict


def always_pass() -> bool:
    return True


def always_fail() -> bool:
    return False


def batch(label: str, n: int, f: int) -> TrialBatch:
    return TrialBatch(condition_label=label, total_runs=n, failures=f)


# --------------------------------------------------------------------- C1 / C5


@pytest.mark.parametrize(
    "kwargs", [{"trials": 0}, {"precision": 0.0}, {"precision": -1.0}, {"low": 5, "high": 5}]
)
def test_c5_search_threshold_validates_its_arguments(kwargs):
    args = {"low": 0.0, "high": 100.0, "trials": 1, "precision": 5.0}
    args.update(kwargs)
    with pytest.raises(ValueError):
        search_threshold("p", lambda v: v < 50, **args)


def test_c1_bisection_declares_its_method_and_trials():
    result = search_threshold("p", lambda v: v < 50, low=0, high=100, trials=3, precision=5)
    assert result.method == "bisection"
    assert result.trials == 3
    assert result.outcome == "boundary_found"
    assert all(p.failure_rate is not None for p in result.search_points)


def test_c1_precision_wider_than_range_uses_only_the_endpoints():
    result = search_threshold("p", lambda v: v < 50, low=0, high=100, trials=1, precision=500)
    assert len(result.search_points) == 2
    assert result.boundary_estimate == 50.0


def test_c1_boundary_module_is_the_noise_aware_alternative():
    import morph.engine.threshold as threshold_mod

    assert "locate_boundary" in threshold_mod.__doc__
    assert "locate_boundary" in search_threshold.__doc__ or "boundary" in search_threshold.__doc__


# ------------------------------------------------------------------------ C2


def _cells(neither: int, a: int, b: int, both: int, n: int):
    def gen(f: int):
        seq = iter([False] * f + [True] * (n - f))
        return lambda: next(seq)

    return dict(run_neither=gen(neither), run_a=gen(a), run_b=gen(b), run_both=gen(both))


def test_c2_additive_2x2_is_not_an_interaction():
    out = detect_interaction(**_cells(0, 4, 4, 8, 10), label_a="lat", label_b="loss", n=10)
    assert out["interaction_confirmed"] is False
    assert 0.3 < out["interaction_probability"] < 0.7
    assert out["excess_failure_rate"] == pytest.approx(0.0)


def test_c2_weak_singles_at_small_n_do_not_confirm_an_interaction():
    out = detect_interaction(**_cells(0, 2, 2, 5, 5), label_a="lat", label_b="loss", n=5)
    assert out["interaction_confirmed"] is False
    assert out["interaction_probability"] < 0.95


def test_c2_genuine_interaction_is_confirmed_with_probability_on_the_verdict():
    events: list[TrialEvent] = []
    out = detect_interaction(
        **_cells(0, 0, 0, 10, 10), label_a="lat", label_b="loss", n=10, on_event=events.append
    )
    assert out["interaction_confirmed"] is True
    assert out["interaction_probability"] > 0.99
    verdict = next(e for e in events if e.kind == "verdict")
    assert verdict.extra["interaction_probability"] == out["interaction_probability"]
    assert verdict.extra["interaction_confirmed"] is True
    assert verdict.extra["single_rates"] == {"lat": 0.0, "loss": 0.0}


def test_c2_interaction_probability_is_seeded_and_reproducible():
    a = detect_interaction(**_cells(0, 1, 1, 9, 10), label_a="a", label_b="b", n=10)
    b = detect_interaction(**_cells(0, 1, 1, 9, 10), label_a="a", label_b="b", n=10)
    assert a["interaction_probability"] == b["interaction_probability"]


# ------------------------------------------------------------------------ C3


def test_c3_too_few_trials_warns_instead_of_silently_saying_no_effect():
    result = run_experiment(always_pass, {"c": always_fail}, n=3)
    assert result.classification == "no_effect"
    assert result.warnings and "n=3" in result.warnings[0] and "n=4" in result.warnings[0]
    assert result.summary.startswith("WARNING")


def test_c3_enough_trials_produce_no_warning():
    result = run_experiment(always_pass, {"c": always_fail}, n=4)
    assert result.warnings == []
    assert result.classification == "environment_caused"


def test_c3_warning_accounts_for_holm_across_candidates():
    # 4 candidates need n=5: 1/C(8,4) = 0.0143 is not below 0.05/4.
    result = run_experiment(
        always_pass, {"a": always_pass, "b": always_pass, "c": always_pass, "d": always_fail}, n=4
    )
    assert result.warnings and "across 4 candidates" in result.warnings[0]


def test_c3_warning_is_on_the_phase_start_and_verdict_events():
    events: list[TrialEvent] = []
    run_experiment(always_pass, {"c": always_fail}, n=2, on_event=events.append)
    assert events[0].kind == "phase_start" and events[0].extra["warnings"]
    assert events[-1].kind == "verdict" and events[-1].extra["warnings"]


def test_run_trials_rejects_zero_trials():
    with pytest.raises(ValueError):
        run_trials(always_pass, 0, "c")
    with pytest.raises(ValueError):
        isolate_variables(always_pass, {}, n=5)


# ------------------------------------------------------------------------ C4


def test_c4_none_from_run_fn_is_a_programming_error_not_a_failure():
    with pytest.raises(TypeError):
        coerce_result(None)
    with pytest.raises(TypeError):
        run_trials(lambda: None, 3, "forgot_return")  # type: ignore[arg-type,return-value]
    assert coerce_result(True) == (True, None)
    rr = RunResult(exit_code=1, passed=False)
    assert coerce_result(rr) == (False, rr)


# ------------------------------------------------------------------------ C6


def _profile(**sections) -> EnvironmentProfile:
    data = sample_profile_dict()
    for name, fields in sections.items():
        data.setdefault(name, {}).update(fields)
    return EnvironmentProfile.model_validate(data)


def test_c6_validator_tolerates_none_values():
    profile = _profile(
        cpu={
            "cores": {"value": None, "status": "unavailable"},
            "quota_percent": {"value": 200, "status": "requested"},
        },
        network={
            "latency_ms": {"value": None, "status": "unavailable"},
            "jitter_ms": {"value": 5, "status": "requested"},
        },
    )
    check_thresholds(profile)
    issues = check_cross_field_rules(profile)
    # jitter 5 vs unknown latency (treated as 0) is still flagged; no crash on cores=None.
    assert all(i.field != "cpu.quota_percent" for i in issues)


def test_c6_worker_check_tolerates_none_and_bools():
    requested = _profile(
        cpu={"cores": {"value": None, "status": "unavailable"}},
        memory={"total_mb": {"value": True, "status": "requested"}},
    )
    host = _profile(
        cpu={"logical_processors": {"value": 8, "status": "captured"}},
        memory={"total_mb": {"value": 16384, "status": "captured"}},
    )
    assert check_worker_required(requested, host) == []


def test_c6_thresholds_skip_booleans():
    profile = _profile(network={"latency_ms": {"value": True, "status": "requested"}})
    assert check_thresholds(profile) == []


# ------------------------------------------------------------------------ C7


def test_c7_blame_never_fabricates_a_culprit():
    blame = analyze_differential_blame("", "", "a", "b")
    assert blame.culpable_file is None
    assert blame.culpable_line is None
    assert blame.culpable_code is None
    assert blame.suggested_fix is None
    assert blame.fail_trace.status_or_exception is None
    assert blame.fail_trace.file is None and blame.fail_trace.line is None
    assert "nothing to blame" in blame.explanation
    assert "app.py" not in blame.divergence_summary


def test_c7_chained_traceback_reports_the_last_exception_and_project_frame(tmp_path: Path):
    (tmp_path / "svc.py").write_text("x = 1\nraise RuntimeError('pool exhausted')\n")
    fail = (
        "Traceback (most recent call last):\n"
        '  File "/usr/lib/python3.12/socket.py", line 10, in create_connection\n'
        "ConnectionRefusedError: [Errno 111]\n\n"
        "The above exception was the direct cause of the following exception:\n\n"
        "Traceback (most recent call last):\n"
        f'  File "{tmp_path / "svc.py"}", line 2, in <module>\n'
        '  File "C:\\Python312\\Lib\\site-packages\\httpx\\_client.py", line 900, in get\n'
        "RuntimeError: pool exhausted\n"
    )
    blame = analyze_differential_blame("ok", fail, "170ms", "185ms", project_dir=tmp_path)
    assert blame.culpable_file == "svc.py"
    assert blame.culpable_line == 2
    assert blame.culpable_code == "raise RuntimeError('pool exhausted')"
    assert blame.fail_trace.status_or_exception == "RuntimeError: pool exhausted"
    assert blame.fail_trace.function == "<module>"
    assert blame.suggested_fix is None
    assert "svc.py:2" in blame.explanation


def test_c7_windows_lib_frames_are_skipped_case_insensitively():
    fail = (
        'File "C:\\Users\\me\\proj\\app.py", line 7, in main\n'
        'File "C:\\Python312\\Lib\\json\\decoder.py", line 355, in raw_decode\n'
        "json.decoder.JSONDecodeError: Expecting value\n"
    )
    blame = analyze_differential_blame("", fail)
    assert blame.culpable_file == "app.py" and blame.culpable_line == 7
    assert blame.fail_trace.status_or_exception.startswith("json.decoder.JSONDecodeError")


def test_c7_structured_log_gives_status_but_no_line():
    blame = analyze_differential_blame(
        "[timeout] PASS in 204ms (timeout=250ms)",
        "[timeout] FAIL in 255ms (timeout=250ms, signal=TimeoutException)",
    )
    assert blame.pass_trace.duration_ms == 204.0
    assert blame.fail_trace.duration_ms == 255.0
    assert "TimeoutException" in blame.fail_trace.status_or_exception
    assert blame.culpable_file is None and blame.culpable_code is None


# ------------------------------------------------------------------------ C8


def _grid(cells: dict[tuple[float, float], tuple[bool, float]]):
    return {
        (x, y): SurfaceGridPoint(x=x, y=y, passed=ok, failure_rate=rate, stdout=f"cell {x},{y}")
        for (x, y), (ok, rate) in cells.items()
    }


def test_c8_blamed_pair_is_adjacent_along_the_sweep():
    xs, ys = [100.0, 200.0, 300.0], [0.0, 5.0, 10.0]
    cells = {}
    for x in xs:
        for y in ys:
            fails = x + 20 * y >= 300  # (300,0) fails; (200,5) fails; (100,10) fails
            cells[(x, y)] = (not fails, 1.0 if fails else 0.0)
    pair = boundary_pair(_grid(cells), xs, ys)
    assert pair is not None
    lo, hi = pair
    assert lo.passed and not hi.passed
    assert lo.x == hi.x and abs(ys.index(hi.y) - ys.index(lo.y)) == 1
    # The lexicographic max/min the old code used, (300, 0)/(100, 10), is not adjacent.
    assert not (lo.x == 300.0 and hi.x == 100.0)


def test_c8_largest_failure_rate_jump_wins_and_row_fallback_applies():
    xs, ys = [1.0, 2.0], [0.0, 1.0]
    # Column sweep: at x=1, (1,0) passes 0.0 -> (1,1) fails 0.6; at x=2, 0.2 -> 1.0.
    cells = {(1.0, 0.0): (True, 0.0), (1.0, 1.0): (False, 0.6),
             (2.0, 0.0): (True, 0.2), (2.0, 1.0): (False, 1.0)}
    lo, hi = boundary_pair(_grid(cells), xs, ys)
    assert (lo.x, lo.y, hi.x, hi.y) == (2.0, 0.0, 2.0, 1.0)
    # No pass->fail transition within any column: fall back to rows.
    cells = {(1.0, 0.0): (True, 0.0), (2.0, 0.0): (False, 1.0),
             (1.0, 1.0): (True, 0.0), (2.0, 1.0): (False, 1.0)}
    lo, hi = boundary_pair(_grid(cells), xs, ys)
    assert lo.y == hi.y and lo.x == 1.0 and hi.x == 2.0
    # Everything passes: nothing to blame.
    cells = {(x, y): (True, 0.0) for x in xs for y in ys}
    assert boundary_pair(_grid(cells), xs, ys) is None


# ------------------------------------------------------------------------ C9


def test_c9_exported_test_compiles_with_hostile_command_and_name():
    code = generate_invariant_test_code(
        project_name="My Service 2.0 (beta)",
        command='python -c "print(\'a\\\\b\')"',
        param_name="network.packet_loss_percent",
        safe_packet_loss=2.5,
        boundary_estimate=3.0,
        divergence_summary='PASS: x\nFAIL: y """ done',
    )
    compile(code, "test_morph_invariant.py", "exec")
    assert "def test_my_service_2_0_beta_environment_tolerance" in code
    assert "network.packet_loss_percent <= 2.5%" in code
    assert "pytest.mark" not in code
    assert "__main__" not in code
    ns: dict = {}
    exec(compile(code, "gen", "exec"), ns)  # the generated file must import cleanly
    assert ns["TARGET_COMMAND"] == 'python -c "print(\'a\\\\b\')"'


def test_c9_exporter_rejects_empty_command():
    with pytest.raises(ValueError):
        generate_invariant_test_code(command="   ")


# ----------------------------------------------------------------------- C10


def test_c10_set_profile_parameter_marks_the_field_requested():
    profile = _profile(network={"latency_ms": {"value": 12.0, "status": "captured"}})
    updated = set_profile_parameter(profile, "network.latency_ms", 180.0)
    assert updated.network.latency_ms.value == 180.0
    assert updated.network.latency_ms.status == FieldStatus.REQUESTED
    assert profile.network.latency_ms.status == FieldStatus.CAPTURED  # original untouched


# ----------------------------------------------------------------------- C11


def test_c11_strongest_is_chosen_by_p_value_then_rate_and_keeps_its_batch():
    result = run_experiment(
        always_pass, {"latency_only": always_fail, "full_treatment": always_fail}, n=10
    )
    by = {c.condition_label: c for c in result.comparisons}
    assert by["latency_only"].treatment is not None
    assert by["latency_only"].treatment.total_runs == 10
    assert result.strongest_condition == "latency_only"  # tie: insertion order, stated
    assert isinstance(by["latency_only"].p_value, float)
    assert result.classification == "environment_caused"


def test_c11_treatment_run_results_survive_into_the_result():
    def run_fn() -> RunResult:
        return RunResult(exit_code=1, passed=False, stderr="boom")

    result = run_experiment(always_pass, {"c": run_fn}, n=5)
    assert result.comparisons[0].treatment.run_results[0].stderr == "boom"


def test_c11_no_significant_candidate_uses_the_classifier_rule():
    flaky = iter([False] * 3 + [True] * 7)
    result = run_experiment(lambda: next(flaky), {"c": always_pass}, n=10)
    assert result.classification == APPLICATION_INTERNAL


# --------------------------------------------------------------- Holm / rigor


def test_holm_is_applied_across_candidates_in_isolate_variables():
    events: list[TrialEvent] = []
    weak = iter([False] * 4 + [True] * 6)
    _base, comparisons = isolate_variables(
        always_pass, {"weak": lambda: next(weak), "none": always_pass, "strong": always_fail},
        n=10, on_event=events.append,
    )
    by = {c.condition_label: c for c in comparisons}
    assert all(c.method == "fisher_holm" for c in comparisons)
    assert by["weak"].p_value == pytest.approx(0.0433, abs=1e-3)
    assert by["weak"].p_value_adjusted == pytest.approx(0.0867, abs=1e-3)
    assert by["weak"].is_significant is False and by["weak"].effect_label == "no_effect"
    assert by["strong"].is_significant is True
    cmp_event = next(e for e in events if e.kind == "comparison" and e.condition == "weak")
    assert cmp_event.extra["method"] == "fisher_holm"
    assert cmp_event.extra["p_value_adjusted"] == by["weak"].p_value_adjusted


def test_single_candidate_stays_plain_fisher():
    _base, (cmp,) = isolate_variables(always_pass, {"c": always_fail}, n=5)
    assert cmp.method == "fisher" and cmp.p_value_adjusted == cmp.p_value


def test_summary_mentions_one_sided_p_and_risk_difference():
    result = run_experiment(always_pass, {"c": always_fail}, n=5)
    assert "one-sided p=" in result.summary
    assert "risk difference +1.00" in result.summary


def test_classifier_uses_the_wilson_lower_bound_for_flakiness():
    assert not baseline_is_internally_flaky(batch("b", 5, 1))  # 0.20 but CI reaches 0.01
    assert baseline_is_internally_flaky(batch("b", 100, 20))
    assert classify_failure(batch("b", 5, 1), batch("t", 5, 5), True) == ENVIRONMENT_EXPOSED


# -------------------------------------------------------------------- schema


def test_trialbatch_failure_rate_is_always_consistent_with_counts():
    b = TrialBatch(condition_label="c", total_runs=5, failures=5, failure_rate=0.0)
    assert b.failure_rate == 1.0
    assert TrialBatch(condition_label="c", total_runs=0, failures=0).failure_rate == 0.0
    assert TrialBatch.model_validate_json(b.model_dump_json()).failure_rate == 1.0


def test_literal_fields_reject_unknown_values():
    with pytest.raises(ValidationError):
        ComparisonResult(effect_label="huge_effect")
    with pytest.raises(ValidationError):
        ComparisonResult(method="t_test")
    with pytest.raises(ValidationError):
        ExperimentResult(classification="compliant")
    with pytest.raises(ValidationError):
        ThresholdResult(parameter="p", outcome="maybe")


def test_comparison_counts_default_from_embedded_batches():
    cmp = ComparisonResult(baseline=batch("baseline", 5, 0), treatment=batch("t", 5, 4))
    assert (cmp.condition_label, cmp.baseline_total, cmp.treatment_failures) == ("t", 5, 4)
    explicit = ComparisonResult(treatment=batch("t", 5, 4), treatment_total=0, treatment_failures=0)
    assert explicit.treatment_total == 0  # explicit counts are never overridden


def test_experiment_result_json_round_trip():
    def run_fn() -> RunResult:
        return RunResult(exit_code=1, passed=False, stderr="err")

    result = run_experiment(always_pass, {"a": run_fn, "b": always_pass}, n=5)
    dumped = result.model_dump_json()
    back = ExperimentResult.model_validate_json(dumped)
    assert back == result
    assert isinstance(back.comparisons[0].treatment, TrialBatch)
    assert back.comparisons[0].risk_difference_ci == result.comparisons[0].risk_difference_ci
    assert json.loads(dumped)["warnings"] == []


def test_threshold_result_json_round_trip_for_both_methods():
    bisect = search_threshold("p", lambda v: v < 50, low=0, high=100, trials=1, precision=10)
    assert ThresholdResult.model_validate_json(bisect.model_dump_json()) == bisect
    pb = locate_boundary("p", lambda v: v < 50, 0.0, 100.0, max_trials=12)
    back = ThresholdResult.model_validate_json(pb.model_dump_json())
    assert back == pb
    assert back.outcome in {"boundary_found", "never_fails", "always_fails", "inconclusive"}
    assert back.method == "probabilistic_bisection"


def test_locate_boundary_populates_outcome():
    assert locate_boundary("p", lambda v: True, 0.0, 100.0, max_trials=20).outcome == "never_fails"
    assert locate_boundary("p", lambda v: False, 0.0, 100.0, max_trials=20).outcome == "always_fails"
    found = locate_boundary("p", lambda v: v < 50, 0.0, 100.0, max_trials=40)
    assert found.outcome == "boundary_found" and found.boundary_estimate is not None
    with pytest.raises(ValueError):
        locate_boundary("p", lambda v: True, 10.0, 10.0)


# ------------------------------------------------------------ invalid trials


class _InvalidRunResult(RunResult):
    """Stands in for the runtime's RunResult.invalid convention."""

    invalid: bool = True
    invalid_reason: str | None = "command not found (exit 127)"


def _invalid() -> RunResult:
    return _InvalidRunResult(exit_code=127, passed=False)


def _flaky_setup(invalid_first: int, then: bool):
    seq = iter([_invalid()] * invalid_first + [RunResult(exit_code=0 if then else 1, passed=then)] * 100)
    return lambda: next(seq)


def test_invalid_trial_is_retried_and_not_counted_as_a_failure():
    events: list[TrialEvent] = []
    result = run_trials(_flaky_setup(2, True), 3, "c", on_event=events.append)
    assert result.failures == 0 and result.total_runs == 3
    invalid_events = [e for e in events if e.kind == "trial" and e.extra.get("invalid")]
    assert len(invalid_events) == 2
    assert invalid_events[0].passed is None
    assert invalid_events[0].extra["reason"] == "command not found (exit 127)"
    assert invalid_events[1].extra["attempt"] == 2
    assert sum(1 for e in events if e.kind == "trial" and not e.extra.get("invalid")) == 3


def test_persistently_invalid_trial_raises_instead_of_a_verdict():
    with pytest.raises(InvalidTrialError) as exc:
        run_experiment(always_pass, {"broken": _flaky_setup(3, True)}, n=5)
    assert exc.value.condition == "broken"
    assert exc.value.reason == "command not found (exit 127)"
    assert exc.value.attempts == 3


def test_invalid_trials_are_handled_in_sequential_threshold_and_boundary():
    seq = run_sequential_experiment(always_pass, {"c": _flaky_setup(1, False)}, max_rounds=6)
    assert seq.comparisons[0].treatment_failures == 6

    calls = {"n": 0}

    def run_at(v: float) -> RunResult:
        calls["n"] += 1
        if calls["n"] == 1:
            return _invalid()
        return RunResult(exit_code=0 if v < 50 else 1, passed=v < 50)

    assert search_threshold("p", run_at, 0, 100, trials=1, precision=10).outcome == "boundary_found"
    calls["n"] = 0
    assert locate_boundary("p", run_at, 0.0, 100.0, max_trials=20).trials <= 20

    with pytest.raises(InvalidTrialError):
        search_threshold("p", lambda v: _invalid(), 0, 100, trials=1, precision=10)
    with pytest.raises(InvalidTrialError):
        run_sequential_experiment(lambda: _invalid(), {"c": always_pass}, max_rounds=3)
