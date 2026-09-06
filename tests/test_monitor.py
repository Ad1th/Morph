"""Monitor screen building blocks: the Slider widget and PerfHistory."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from morph.schema.telemetry import RunResult, TelemetryData
from morph.tui.app import MorphApp
from morph.tui.perf import PerfHistory
from morph.tui.widgets.slider import Slider


def _run(passed: bool, duration: float) -> RunResult:
    return RunResult(
        exit_code=0 if passed else 1,
        passed=passed,
        duration_ms=duration,
        peak_memory_mb=140.0,
        telemetry=TelemetryData(cpu_percent=22.0),
        error_type=None if passed else "LockLostException",
        stderr="" if passed else "LockLostException: lock expired mid-payment",
    )


def test_perf_history_buffers_and_learns_boundary():
    hist = PerfHistory(capacity=5)
    for latency, passed in [(50, True), (120, True), (176, False), (150, True), (210, False)]:
        hist.add({"network.latency_ms": float(latency)}, _run(passed, latency * 1.5))

    assert len(hist) == 5
    assert hist.durations[-1] == 315.0
    assert hist.first_failure_value("network.latency_ms") == 176.0
    assert hist.last_pass_value("network.latency_ms") == 150.0
    assert hist.last_failure.error_type == "LockLostException"


def test_perf_history_caps_at_capacity():
    hist = PerfHistory(capacity=3)
    for i in range(6):
        hist.add({"x": float(i)}, _run(True, float(i)))
    assert len(hist) == 3
    assert hist.durations == [3.0, 4.0, 5.0]


def test_implicates_only_blames_the_param_that_actually_split():
    hist = PerfHistory()
    # latency drives it: everything below 200 passes, at/above fails.
    # cpu.cores is 4 for every run -> it must NOT be implicated.
    for latency, passed in [(80, True), (150, True), (210, False), (260, False)]:
        hist.add(
            {"network.latency_ms": float(latency), "cpu.cores": 4.0},
            _run(passed, latency * 1.4),
        )
    assert hist.implicates("network.latency_ms") == 210.0
    assert hist.implicates("cpu.cores") is None


@pytest.mark.asyncio
async def test_monitor_screen_runs_and_warns_in_demo_mode():
    app = MorphApp(demo=True)
    async with app.run_test() as pilot:
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert screen.__class__.__name__ == "MonitorScreen"

        for _ in range(80):
            await pilot.pause(0.05)
            if len(screen._hist) and not screen._busy:
                break
        assert len(screen._hist) >= 1  # reconciled + auto-ran once

        sliders = list(screen.query(Slider))
        # honest badges: this host cannot cap RAM
        by_param = {s.param: s for s in sliders}
        assert by_param["memory.total_mb"].status == "unavailable"

        latency = by_param["network.latency_ms"]
        latency.focus()
        for _ in range(30):
            await pilot.press("shift+right")
        await pilot.pause()
        for _ in range(150):
            await pilot.pause(0.05)
            if not screen._busy and screen._current_params() == screen._last_params:
                break

        assert screen._hist.implicates("network.latency_ms") is not None
        assert latency.warn is True
        assert by_param["cpu.cores"].warn is False
        warn_text = str(screen.query_one("#mon-warn").render())
        assert "latency" in warn_text and "LockLostException" in warn_text
        assert len(screen.query_one("#spark-dur").data) == len(screen._hist)


class _SliderApp(App):
    def __init__(self) -> None:
        super().__init__()
        self.changes: list[float] = []

    def compose(self) -> ComposeResult:
        yield Slider(
            "network.latency_ms", "latency",
            minimum=0, maximum=400, value=100, step=10, big_step=100, unit="ms",
        )

    def on_slider_changed(self, event: Slider.Changed) -> None:
        self.changes.append(event.value)


@pytest.mark.asyncio
async def test_slider_keys_adjust_clamp_and_notify():
    app = _SliderApp()
    async with app.run_test() as pilot:
        slider = app.query_one(Slider)
        slider.focus()

        await pilot.press("right", "right")
        await pilot.pause()
        assert slider.value == 120

        await pilot.press("shift+right")
        await pilot.pause()
        assert slider.value == 220

        await pilot.press("end")
        await pilot.pause()
        assert slider.value == 400  # clamped to max

        await pilot.press("right")  # no-op at the ceiling — no new message
        await pilot.pause()
        assert slider.value == 400

        await pilot.press("home")
        await pilot.pause()
        assert slider.value == 0

    assert app.changes == [110, 120, 220, 400, 0]
