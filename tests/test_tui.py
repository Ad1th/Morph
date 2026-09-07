"""TUI: navigation, the orchestrator, and the live experiment console wiring."""

from __future__ import annotations

import pytest

from morph.schema.events import TrialEvent
from morph.schema.profile import (
    CPUInfo,
    EnvironmentProfile,
    FieldStatus,
    LocaleInfo,
    MemoryInfo,
    NetworkInfo,
    OSInfo,
    ProfileField,
)
from morph.schema.telemetry import RunResult
from morph.tui.app import MorphApp
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import (
    RunCancelled,
    build_isolation_runners,
    cancellable,
    run_replay_live,
    set_profile_parameter,
)
from morph.tui.profiles import resolve_profile
from morph.tui.screens.environment import apply_template


def _pf(value, status=FieldStatus.REQUESTED):
    return ProfileField(value=value, status=status)


def _profile(latency=120.0, loss=2.0):
    return EnvironmentProfile(
        os=OSInfo(family=_pf("linux"), version=_pf("6.1")),
        cpu=CPUInfo(architecture=_pf("x86_64"), cores=_pf(4), logical_processors=_pf(4)),
        memory=MemoryInfo(total_mb=_pf(8192)),
        locale=LocaleInfo(locale=_pf("en_US.UTF-8"), timezone=_pf("UTC")),
        network=NetworkInfo(latency_ms=_pf(latency), packet_loss_percent=_pf(loss)),
    )


async def _wait(pilot, pred, tries=200, dt=0.05) -> bool:
    for _ in range(tries):
        await pilot.pause(dt)
        if pred():
            return True
    return False


def _text(widget) -> str:
    """Plain text of a Static's current content (Rich Text / Group or Textual Content)."""
    from rich.console import Console

    content = widget.content
    plain = getattr(content, "plain", None)
    if isinstance(plain, str):
        return plain
    console = Console(width=300, color_system=None, force_terminal=False)
    with console.capture() as cap:
        console.print(content)
    return cap.get()


# --------------------------------------------------------------------------- #
# orchestrator (no Textual, no subprocess)
# --------------------------------------------------------------------------- #

def test_build_isolation_runners_derives_network_candidates():
    _baseline, candidates = build_isolation_runners(_profile(120.0, 2.0), "echo hi", 5.0)
    assert set(candidates) == {"latency_only", "loss_only", "full_target"}


def test_build_isolation_runners_skips_zero_variables():
    _baseline, candidates = build_isolation_runners(_profile(0.0, 0.0), "echo hi", 5.0)
    assert set(candidates) == {"full_target"}


def test_set_profile_parameter_sets_nested_value():
    updated = set_profile_parameter(_profile(), "network.latency_ms", 250.0)
    assert updated.network.latency_ms.value == 250.0
    assert updated.cpu.cores.value == 4  # untouched


def test_set_profile_parameter_rejects_bad_path():
    with pytest.raises(ValueError):
        set_profile_parameter(_profile(), "network.nonsense", 1.0)


def test_run_replay_live_emits_trials_and_verdict(tmp_path):
    """Hermetic: the runner is injected, so no subprocess, adapter, or worker."""
    from morph.regression.artifact import save_regression
    from morph.schema.regression import RegressionArtifact

    art = RegressionArtifact(
        regression_id="tui-replay-test",
        environment=_profile(0.0, 0.0),
        command="python -c 'print(1)'",
        expected_exit_code=0,
        expected_max_failure_rate=0.0,
    )
    save_regression(art, base_dir=tmp_path)

    events: list[TrialEvent] = []
    result = run_replay_live(
        art, trials=3, timeout=15.0, on_event=events.append,
        run_fn=lambda: RunResult(exit_code=0, passed=True, duration_ms=1.0),
    )

    assert result.matches_expected is True
    assert result.failures == 0
    assert [e.kind for e in events].count("trial") == 3
    assert events[-1].kind == "verdict"
    assert events[-1].classification == "compliant"


def test_run_replay_live_uses_the_bundle_cwd(monkeypatch):
    """A regression saved from a project replays from that project's directory."""
    import morph.tui.orchestrator as orch
    from morph.schema.regression import RegressionArtifact

    seen: dict = {}

    def fake_runner(command, profile, timeout, controller=None, cwd=None):
        seen["cwd"] = cwd
        return lambda: RunResult(exit_code=0, passed=True, duration_ms=1.0)

    monkeypatch.setattr(orch, "make_result_runner", fake_runner)
    art = RegressionArtifact(
        regression_id="cwd-test", environment=_profile(0.0, 0.0), command="python3 main.py",
        metadata={"cwd": "/tmp/proj"},
    )
    run_replay_live(art, trials=1, timeout=5.0, on_event=lambda e: None, controller=object())
    assert seen["cwd"] == "/tmp/proj"


def test_resolve_profile_rejects_a_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        resolve_profile(str(tmp_path / "typo.json"))


def test_resolve_profile_reads_a_file(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(_profile(33.0, 1.0).model_dump_json())
    assert resolve_profile(str(path)).network.latency_ms.value == 33.0


def test_cancellable_raises_between_events():
    got: list[TrialEvent] = []
    flag = {"cancel": False}
    emit = cancellable(got.append, lambda: flag["cancel"])
    emit(TrialEvent(kind="trial"))
    flag["cancel"] = True
    with pytest.raises(RunCancelled):
        emit(TrialEvent(kind="trial"))
    assert len(got) == 1


def test_apply_template_high_latency_and_constrained():
    base = _profile(0.0, 0.0)
    hl = apply_template(base, "high-latency")
    assert hl.network.latency_ms.value == 180.0
    assert hl.network.packet_loss_percent.value == 2.0

    con = apply_template(base, "constrained")
    assert con.cpu.cores.value == 2
    assert con.memory.total_mb.value == 4096
    # original untouched
    assert base.cpu.cores.value == 4


# --------------------------------------------------------------------------- #
# app navigation, help, theme, palette
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_home_navigation():
    app = MorphApp()
    async with app.run_test() as pilot:
        assert app.screen.__class__.__name__ == "HomeScreen"
        for key, name in [
            ("e", "ExperimentScreen"),
            ("t", "ThresholdScreen"),
            ("n", "EnvironmentScreen"),
            ("r", "RegressionsScreen"),
            ("p", "ProjectsScreen"),
        ]:
            await pilot.press(key)
            await pilot.pause()
            assert app.screen.__class__.__name__ == name
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "HomeScreen"


@pytest.mark.asyncio
async def test_help_overlay_lists_every_binding():
    from morph.tui.screens.help import HelpScreen, binding_rows

    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        experiment = app.screen
        keys = {k for k, _d, _s in binding_rows(experiment)}
        assert {"^r", "^s", "^t", "esc", "c", "^q", "F1", "^p"} <= keys

        await pilot.press("f1")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)
        body = _text(app.screen.query_one("#help-body"))
        assert "Run" in body and "Quit" in body and "Seq/Batch" in body
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen is experiment

        # `?` works too when no Input has focus
        await pilot.press("escape")
        await pilot.pause()
        await pilot.press("question_mark")
        await pilot.pause()
        assert isinstance(app.screen, HelpScreen)


@pytest.mark.asyncio
async def test_theme_toggle_and_palette_colours():
    from morph.tui.theme import palette

    app = MorphApp()
    async with app.run_test() as pilot:
        assert app.theme == "morph-dark"
        dark = palette(app.screen)
        await pilot.press("f2")
        await pilot.pause()
        assert app.theme == "morph-light"
        light = palette(app.screen)
        assert dark.pass_ != light.pass_ and dark.text != light.text


@pytest.mark.asyncio
async def test_command_palette_opens_a_screen():
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("ctrl+p")
        await pilot.pause(0.3)
        for ch in "open threshold":
            await pilot.press("space" if ch == " " else ch)
        await pilot.pause(0.8)
        await pilot.press("enter")
        await _wait(pilot, lambda: app.screen.__class__.__name__ == "ThresholdScreen", tries=60)
        assert app.screen.__class__.__name__ == "ThresholdScreen"


# --------------------------------------------------------------------------- #
# environment: capture, template, reconcile, escaping, unwritable save
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_environment_screen_capture_template_reconcile_and_errors(tmp_path):
    app = MorphApp()
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen
        assert await _wait(pilot, lambda: screen._profile is not None)  # host capture landed

        screen.query_one("#env-template").value = "high-latency"
        await pilot.pause()
        await pilot.pause()
        assert screen._profile.network.latency_ms.value == 180.0

        screen.action_reconcile()
        assert await _wait(pilot, lambda: not screen._busy)
        assert screen.query_one("#env-diff").row_count == 9
        status = _text(screen.query_one("#status-left"))
        assert "reconciled" in status
        statuses = {
            str(getattr(f.status, "value", f.status))
            for f in (screen._profile.cpu.cores, screen._profile.memory.total_mb,
                      screen._profile.network.latency_ms)
        }
        assert statuses <= {"reproduced", "approximated", "unavailable"}

        # hostile text must be shown literally, never parsed as markup (C2)
        load = screen.query_one("#env-load")
        load.value = "[bold]nope[/]"
        load.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert "[bold]nope[/]" in _text(screen.query_one("#status-left"))

        bad = tmp_path / "README.md"
        bad.write_text("# not json\n")
        load.value = str(bad)
        await pilot.press("enter")
        await pilot.pause()
        assert "bad profile" in _text(screen.query_one("#status-left"))

        # an unwritable save path is an error line, not a crash (C1)
        save = screen.query_one("#env-save")
        save.value = str(tmp_path / "no" / "such" / "dir" / "x.json")
        save.focus()
        await pilot.press("enter")
        await pilot.pause()
        assert "save failed" in _text(screen.query_one("#status-left"))
        assert app.screen is screen


# --------------------------------------------------------------------------- #
# demo recording: honest, sequential, early stop
# --------------------------------------------------------------------------- #

def test_demo_events_tell_the_environment_caused_story():
    from morph.tui.demo import demo_events, experiment_recording

    events = demo_events()
    kinds = [e.kind for e in events]
    assert "evidence" in kinds
    evidence = [e for e in events if e.kind == "evidence"]
    decisive = [e for e in evidence if e.decisive]
    assert decisive and all(e.condition == "full_target" for e in decisive)
    assert decisive[0].e_value >= decisive[0].evidence_threshold
    comparisons = [e for e in events if e.kind == "comparison"]
    assert [c.is_significant for c in comparisons] == [False, False, True]
    assert comparisons[-1].extra["stopped_early"] is True
    assert events[-1].kind == "verdict"
    assert events[-1].classification == "environment_caused"
    assert events[-1].strongest_condition == "full_target"
    # no p-value on any per-trial event
    assert all(e.p_value is None for e in events if e.kind == "trial")
    _events, result = experiment_recording()
    assert result.classification == "environment_caused"


def test_demo_threshold_recording_shrinks_the_credible_band():
    from morph.tui.demo import threshold_recording

    events, result = threshold_recording()
    probes = [e for e in events if e.kind == "search_probe"]
    assert len(probes) >= 6
    first = probes[0].failure_value - probes[0].safe_value
    last = probes[-1].failure_value - probes[-1].safe_value
    assert last < first / 3
    assert result.boundary_estimate is not None
    assert result.credible_low < result.boundary_estimate < result.credible_high


@pytest.mark.asyncio
async def test_demo_mode_runs_sequential_and_reveals_the_verdict():
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        screen = app.screen
        assert screen.mode == "sequential"
        screen.action_run()  # no command entered
        assert await _wait(pilot, lambda: not screen.busy and screen._last_verdict, tries=400)
        assert set(screen._lanes) == {"baseline", "latency_only", "loss_only", "full_target"}
        full = screen._lanes["full_target"]
        assert full._decisive and full.has_class("decisive")
        assert full._stopped_early
        assert full._effect == "significant_increase"
        assert not screen.query_one("#verdict").has_class("hidden")
        assert not screen.query_one("#matrix").has_class("hidden")
        assert screen._rates["full_target"] == 1.0
        assert screen._rates["latency_only"] == 0.0

        # the verdict reveals progressively, then is fully shown
        card = screen.query_one("#verdict")
        assert await _wait(pilot, lambda: card.revealed, tries=40)
        text = _text(card)
        assert "ENVIRONMENT-CAUSED" in text and "E = " in text and "pairs" in text
        # status bar carried the leading e-value
        assert "E " in _text(screen.query_one("#status-right"))
        assert screen.query_one("#evidence").has_evidence


@pytest.mark.asyncio
async def test_experiment_screen_saves_regression(tmp_path, monkeypatch):
    import morph.regression.artifact

    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path)

    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        screen = app.screen

        assert screen.query_one("#btn-save").disabled  # nothing to save yet
        screen.action_run()
        assert await _wait(pilot, lambda: not screen.busy and screen._last_verdict, tries=400)

        assert not screen.query_one("#btn-save").disabled  # verdict landed
        screen.query_one("#in-regid").value = "tui-save-001"
        screen.action_save()
        await pilot.pause()

        bundle = tmp_path / "tui-save-001"
        assert (bundle / "environment.json").exists()
        assert (bundle / "command.json").exists()
        assert screen.query_one("#btn-save").disabled  # consumed


@pytest.mark.asyncio
async def test_cancel_stops_a_running_experiment_cooperatively():
    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        screen = app.screen
        screen.action_run()
        assert await _wait(pilot, lambda: len(screen._lanes) >= 2)
        assert screen.busy
        await pilot.press("escape")  # esc = stop while running, not back
        assert await _wait(pilot, lambda: not screen.busy)
        assert app.screen is screen
        assert not screen._last_verdict
        assert all(lane._cancelled for lane in screen._lanes.values())
        assert "cancelled" in _text(screen.query_one("#status-left"))
        await pilot.press("escape")  # now it goes back
        await pilot.pause()
        assert app.screen.__class__.__name__ == "HomeScreen"


@pytest.mark.asyncio
async def test_cancel_unwinds_the_engine_and_runs_cleanup():
    """The on_event callback raises inside the engine, so a `finally` (adapter
    cleanup) runs before the worker reports cancelled."""
    import threading

    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("r")
        await pilot.pause()
        screen = app.screen
        cleaned = threading.Event()
        emitted = {"n": 0}

        def engine(on_event):
            try:
                while True:
                    on_event(TrialEvent(kind="trial", condition="x", trial_index=emitted["n"], passed=True))
                    emitted["n"] += 1
                    threading.Event().wait(0.02)
            finally:
                cleaned.set()

        screen.start(engine, phase="test", total=0)
        assert await _wait(pilot, lambda: emitted["n"] >= 3)
        screen.action_cancel()
        assert await _wait(pilot, lambda: not screen.busy)
        assert cleaned.is_set()
        assert emitted["n"] < 1000


# --------------------------------------------------------------------------- #
# threshold: bayesian gauge, no-boundary outcome, classic bisection
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_threshold_gauge_bayesian_band_and_no_boundary(monkeypatch):
    import morph.tui.screens.threshold as th_mod

    monkeypatch.setattr(th_mod.ThresholdScreen, "start", lambda self, *a, **k: None)

    app = MorphApp()
    async with app.run_test() as pilot:
        await pilot.press("t")
        await pilot.pause()
        screen = app.screen
        assert screen.method == "bayesian"
        screen.query_one("#th-command").value = "noop"
        screen.query_one("#th-param").value = "network.latency_ms"
        await pilot.pause()
        screen.action_run()
        await pilot.pause()
        gauge = screen._gauge
        assert gauge is not None and gauge.bayesian

        probes = [
            (0.0, True, 25.0, 380.0, 200.0),
            (400.0, False, 25.0, 370.0, 199.0),
            (199.0, False, 20.0, 246.0, 114.0),
            (114.0, False, 12.0, 153.0, 69.0),
            (69.0, True, 40.0, 130.0, 86.0),
        ]
        for value, passed, lo, hi, med in probes:
            screen.post_message(EngineEvent(TrialEvent(
                kind="search_probe", phase="threshold", param_value=value, passed=passed,
                failures=0 if passed else 1, total=1, safe_value=lo, failure_value=hi,
                boundary_estimate=med,
                extra={"passed": passed, "boundary_in_range": 0.99, "never_fails": 0.0, "always_fails": 0.01},
            )))
        await pilot.pause()
        await pilot.pause()
        assert len(gauge._probes) == 5
        assert (gauge._safe, gauge._fail) == (40.0, 130.0)
        assert gauge._estimate == 86.0
        assert "credible" in _text(gauge)

        # the engine says: no boundary in range (never fails) -> say so, no "≈ 0"
        screen.post_message(EngineEvent(TrialEvent(
            kind="phase_done", phase="threshold", boundary_estimate=None, safe_value=400.0,
            failure_value=None, extra={"boundary_in_range": 0.1, "never_fails": 0.88, "always_fails": 0.02},
        )))
        screen.post_message(RunFinished(object()))
        await pilot.pause()
        await pilot.pause()
        assert gauge.outcome == "never_fails"
        text = _text(gauge)
        assert "no boundary" in text and "never fails" in text
        assert "≈ 0" not in text


@pytest.mark.asyncio
async def test_threshold_gauge_classic_bisection_converges(monkeypatch):
    import morph.tui.screens.threshold as th_mod

    monkeypatch.setattr(th_mod.ThresholdScreen, "start", lambda self, *a, **k: None)

    app = MorphApp()
    async with app.run_test() as pilot:
        await pilot.press("t")
        await pilot.pause()
        screen = app.screen
        screen.action_toggle_method()
        await pilot.pause()
        assert screen.method == "bisection"
        screen.query_one("#th-command").value = "noop"
        screen.query_one("#th-trials").value = "3"
        await pilot.pause()
        screen.action_run()
        await pilot.pause()
        gauge = screen._gauge
        assert not gauge.bayesian

        for value, passed, safe, fail in [
            (200, False, 0, 200), (100, True, 100, 200), (150, True, 150, 200),
            (175, True, 175, 200), (187, False, 175, 187),
        ]:
            screen.post_message(EngineEvent(TrialEvent(
                kind="search_probe", param_value=float(value), failures=0 if passed else 3, total=3,
                safe_value=float(safe), failure_value=float(fail), extra={"passed": passed},
            )))
        screen.post_message(EngineEvent(TrialEvent(
            kind="phase_done", phase="threshold", boundary_estimate=181.0,
            safe_value=175.0, failure_value=187.0,
        )))
        screen.post_message(RunFinished(object()))
        await pilot.pause()
        await pilot.pause()
        assert len(gauge._probes) == 5
        assert gauge._boundary == 181.0
        assert gauge._safe == 175.0 and gauge._fail == 187.0
        assert gauge.outcome == "boundary"


@pytest.mark.asyncio
async def test_threshold_demo_replays_bayesian_search():
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("t")
        await pilot.pause()
        screen = app.screen
        screen.action_run()
        assert await _wait(pilot, lambda: not screen.busy and screen._gauge is not None, tries=600)
        gauge = screen._gauge
        assert gauge.outcome == "boundary"
        assert gauge._density  # posterior strip drawn from the engine result
        assert "boundary ≈" in _text(gauge)


# --------------------------------------------------------------------------- #
# live experiment console wiring (engine faked)
# --------------------------------------------------------------------------- #

def _event_script(trials: int = 5):
    """A batch experiment's worth of TrialEvents: baseline clean, full_target 5/5."""
    events: list[TrialEvent] = [TrialEvent(kind="phase_start", phase="isolation", extra={"mode": "batch"})]
    for cond, fails in [
        ("baseline", 0),
        ("latency_only", 0),
        ("loss_only", 0),
        ("full_target", trials),
    ]:
        events.append(TrialEvent(kind="condition_start", condition=cond, total=trials))
        f = 0
        for i in range(trials):
            passed = i >= fails
            if not passed:
                f += 1
            events.append(
                TrialEvent(
                    kind="trial", condition=cond, trial_index=i, total=trials,
                    passed=passed, failures_so_far=f, duration_ms=1.0,
                    error_type=None if passed else "ValueError",
                    stderr_tail="ValueError: [red]boom[/red]" if not passed else None,
                )
            )
        events.append(
            TrialEvent(kind="condition_done", condition=cond, total=trials,
                       failures=fails, failure_rate=fails / trials)
        )
        if cond != "baseline":
            sig = cond == "full_target"
            events.append(
                TrialEvent(kind="comparison", condition=cond,
                           p_value=0.001 if sig else 0.9, is_significant=sig,
                           effect_label="significant_increase" if sig else "no_effect")
            )
    events.append(
        TrialEvent(kind="verdict", classification="environment_caused",
                   strongest_condition="full_target", p_value=0.001,
                   extra={"summary": "baseline clean; full_target 5/5"})
    )
    return events


@pytest.mark.asyncio
async def test_experiment_screen_renders_batch_lanes_verdict_and_evidence():
    app = MorphApp()
    async with app.run_test() as pilot:
        await pilot.press("e")
        await pilot.pause()
        screen = app.screen

        for ev in _event_script(5):
            screen.post_message(EngineEvent(ev))
        screen.post_message(RunFinished(object()))
        await pilot.pause()
        await pilot.pause()

        assert screen.mode == "batch"
        assert set(screen._lanes) == {"baseline", "latency_only", "loss_only", "full_target"}
        assert not screen.query_one("#verdict").has_class("hidden")

        full = screen._lanes["full_target"]
        assert full._effect == "significant_increase"
        assert full._failures == 5
        assert full._p_value == 0.001
        assert screen._lanes["baseline"]._failures == 0

        # evidence pane shows the latest failing trial, markup-safe
        pane = screen.query_one("#evidence")
        assert pane.has_evidence
        text = _text(pane)
        assert "full_target" in text and "ValueError" in text and "[red]boom[/red]" in text


@pytest.mark.asyncio
async def test_experiment_screen_renders_live_evidence_bars():
    app = MorphApp()
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("e")
        await pilot.pause()
        screen = app.screen
        screen.status_bar.start_run("isolation", 24)
        screen.post_message(EngineEvent(TrialEvent(
            kind="phase_start", phase="isolation", extra={"mode": "sequential"},
        )))
        for cond in ("baseline", "full_target"):
            screen.post_message(EngineEvent(TrialEvent(kind="condition_start", condition=cond, total=12)))
        e = 1.0
        for i in range(6):
            for cond, passed in (("baseline", True), ("full_target", False)):
                screen.post_message(EngineEvent(TrialEvent(
                    kind="trial", condition=cond, trial_index=i, total=12, passed=passed,
                )))
            e *= 2.5
            screen.post_message(EngineEvent(TrialEvent(
                kind="evidence", condition="full_target", e_value=e, evidence_threshold=60.0,
                pairs=i + 1, decisive=e >= 60.0, failures=i + 1, failure_rate=1.0,
            )))
        await pilot.pause()
        await pilot.pause()
        lane = screen._lanes["full_target"]
        assert lane._e_value == pytest.approx(2.5 ** 6)
        assert len(lane._e_history) == 6
        assert lane._decisive and lane.has_class("decisive")
        text = _text(lane)
        assert "DECISIVE" in text and "│" in text and "60" in text
        # the anytime p-value is fine to show live; a Fisher p never appears mid-run
        assert "p=" not in text
        assert "E " in _text(screen.query_one("#status-right"))
        assert screen.query_one("#status-progress").display


# --------------------------------------------------------------------------- #
# 80x24: nothing clipped on any screen
# --------------------------------------------------------------------------- #

def _clipped(app) -> list[str]:
    """Widgets drawn outside the screen. Children of a scrollable container are
    exempt: being scrolled out of view is not clipping, the container itself
    still has to fit."""
    from textual.containers import VerticalScroll

    width, height = app.size
    bad = []
    for w in app.screen.walk_children(with_self=False):
        r = w.region
        if r.width == 0 or r.height == 0 or not w.display:
            continue
        if any(isinstance(a, VerticalScroll) for a in w.ancestors):
            continue
        if r.x < 0 or r.y < 0 or r.right > width or r.bottom > height:
            bad.append(f"{w!r} {r}")
    return bad


@pytest.mark.asyncio
async def test_every_screen_fits_80x24_without_clipping():
    from textual.widgets import Footer

    app = MorphApp(demo=True)
    async with app.run_test(size=(80, 24)) as pilot:
        assert app.size == (80, 24)
        for key in ("", "e", "m", "t", "n", "p", "r"):
            if key:
                await pilot.press(key)
            await pilot.pause(0.3)
            assert "-compact" in app.screen.classes
            assert _clipped(app) == [], f"{app.screen.__class__.__name__}: {_clipped(app)}"
            footer = app.screen.query_one(Footer)
            assert footer.region.bottom == 24  # footer visible
            assert app.screen.query_one("#status-bar").region.height == 1
            if key:
                await pilot.press("escape")
                await pilot.pause()

        # wide: two panes on the Experiment screen
        await pilot.resize_terminal(200, 60)
        await pilot.press("e")
        await pilot.pause(0.3)
        assert "-wide" in app.screen.classes
        left, right = app.screen.query_one("#exp-left"), app.screen.query_one("#exp-right")
        assert left.region.y == right.region.y and left.region.right <= right.region.x


@pytest.mark.asyncio
async def test_projects_screen_connects_and_opens_experiment(tmp_path, monkeypatch):
    import morph.projects

    monkeypatch.setattr(morph.projects, "REGISTRY_DIR", tmp_path / "registry")

    proj_dir = tmp_path / "tuiproj"
    proj_dir.mkdir()
    (proj_dir / "main.py").write_text("print('ran')\n")

    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("p")
        await pilot.pause()
        screen = app.screen
        assert screen.__class__.__name__ == "ProjectsScreen"
        assert app.focused.id == "proj-src"  # empty list -> typing works

        screen.query_one("#proj-src").value = str(proj_dir)
        screen.query_one("#proj-install").value = False
        screen.action_connect()
        assert await _wait(pilot, lambda: not screen._busy and screen._rows)
        assert [r.name for r in screen._rows] == ["tuiproj"]
        assert screen._rows[0].command == "python3 main.py"
        assert app.focused.id == "proj-table"  # rows -> letter keys act on the table

        await pilot.press("e")
        await pilot.pause()
        exp = app.screen
        assert exp.__class__.__name__ == "ExperimentScreen"
        assert app.active_project.name == "tuiproj"
        assert exp.query_one("#in-command").value == "python3 main.py"
        assert exp._project_cwd == str(proj_dir)
