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
from morph.tui.app import MorphApp
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import build_isolation_runners, set_profile_parameter
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
# app navigation
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
        ]:
            await pilot.press(key)
            await pilot.pause()
            assert app.screen.__class__.__name__ == name
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen.__class__.__name__ == "HomeScreen"


@pytest.mark.asyncio
async def test_environment_screen_capture_template_reconcile():
    app = MorphApp()
    async with app.run_test() as pilot:
        await pilot.press("n")
        await pilot.pause()
        screen = app.screen

        for _ in range(60):
            await pilot.pause(0.05)
            if screen._profile is not None:
                break
        assert screen._profile is not None  # host capture landed

        screen.query_one("#env-template").value = "high-latency"
        await pilot.pause()
        await pilot.pause()
        assert screen._profile.network.latency_ms.value == 180.0

        screen.action_reconcile()
        await pilot.pause()
        # every field carries a reconciled status (not the raw REQUESTED/CAPTURED)
        assert screen.query_one("#env-diff").row_count == 9


# --------------------------------------------------------------------------- #
# live experiment console wiring (engine faked)
# --------------------------------------------------------------------------- #

def _event_script(trials: int = 5):
    """A full experiment's worth of TrialEvents: baseline clean, full_target 5/5."""
    events: list[TrialEvent] = []
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
                    stderr_tail="ValueError: boom" if not passed else None,
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
async def test_experiment_screen_renders_lanes_and_verdict():
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

        assert set(screen._lanes) == {"baseline", "latency_only", "loss_only", "full_target"}
        assert not screen.query_one("#verdict").has_class("hidden")

        full = screen._lanes["full_target"]
        assert full._effect == "significant_increase"
        assert full._failures == 5
        assert full._p_value == 0.001

        baseline = screen._lanes["baseline"]
        assert baseline._failures == 0
