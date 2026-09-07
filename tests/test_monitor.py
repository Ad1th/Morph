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
        error_type=None if passed else "DeadlineExceeded",
        stderr="" if passed else "DeadlineExceeded: batch missed its 2400ms deadline",
    )


async def _wait(pilot, pred, tries=200, dt=0.05) -> bool:
    for _ in range(tries):
        await pilot.pause(dt)
        if pred():
            return True
    return False


def test_perf_history_buffers_and_learns_boundary():
    hist = PerfHistory(capacity=5)
    for latency, passed in [(50, True), (120, True), (176, False), (150, True), (210, False)]:
        hist.add({"network.latency_ms": float(latency)}, _run(passed, latency * 1.5))

    assert len(hist) == 5
    assert hist.durations[-1] == 315.0
    assert hist.first_failure_value("network.latency_ms") == 176.0
    assert hist.last_pass_value("network.latency_ms") == 150.0
    assert hist.last_failure.error_type == "DeadlineExceeded"


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
    assert hist.implicates("cpu.cores", "down") is None


def test_implicates_is_direction_aware_for_ram_and_cores():
    """For RAM / cores *less* is worse: the boundary is the highest failing
    value, and it only counts when something passed strictly above it."""
    hist = PerfHistory()
    for ram, passed in [(8192, True), (4096, True), (512, False), (256, False), (1024, True)]:
        hist.add({"memory.total_mb": float(ram), "network.latency_ms": 60.0}, _run(passed, 40.0))
    assert hist.first_failure_value("memory.total_mb", "down") == 512.0
    assert hist.last_pass_value("memory.total_mb", "down") == 1024.0
    assert hist.implicates("memory.total_mb", "down") == 512.0
    assert hist.implicates("network.latency_ms", "up") is None  # constant -> not blamed
    # the "up" reading of the same data would wrongly pick the lowest failing value
    assert hist.implicates("memory.total_mb", "up") is None

    assert PerfHistory.near_boundary(512.0, 512.0, "down") == "past"
    assert PerfHistory.near_boundary(550.0, 512.0, "down") == "approaching"
    assert PerfHistory.near_boundary(4096.0, 512.0, "down") is None
    assert PerfHistory.near_boundary(370.0, 360.0, "up") == "past"
    assert PerfHistory.near_boundary(330.0, 360.0, "up") == "approaching"


@pytest.mark.asyncio
async def test_monitor_screen_runs_and_warns_in_demo_mode():
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert screen.__class__.__name__ == "MonitorScreen"

        assert await _wait(pilot, lambda: len(screen._hist) >= 1 and not screen._busy)

        sliders = list(screen.query(Slider))
        # honest badges: every slider carries a fidelity status for this host
        # (which one depends on the OS running the test)
        by_param = {s.param: s for s in sliders}
        reconciled = {"reproduced", "approximated", "unavailable"}
        assert by_param["memory.total_mb"].status in reconciled
        assert by_param["cpu.cores"].status in reconciled
        assert by_param["memory.total_mb"].direction == "down"

        latency = by_param["network.latency_ms"]
        latency.focus()
        for _ in range(30):
            await pilot.press("shift+right")
        await pilot.pause()
        settled = lambda: not screen._busy and screen._current_params() == screen._last_params  # noqa: E731
        assert await _wait(pilot, settled)

        assert screen._hist.implicates("network.latency_ms") is not None
        assert latency.warn is True
        assert by_param["cpu.cores"].warn is False
        warn_text = str(screen.query_one("#mon-warn").render())
        assert "latency" in warn_text and "DeadlineExceeded" in warn_text
        assert len(screen.query_one("#spark-dur").data) == len(screen._hist)

        # RAM is at the host maximum for every one of those failures: the
        # runs never split on it, so it must not be blamed (direction-aware).
        assert screen._hist.implicates("memory.total_mb", "down") is None
        assert by_param["memory.total_mb"].warn is False

        # the pass/fail strip is built from a list slice + rich.Text, so it
        # renders cleanly at any length
        for _ in range(200):
            screen._hist.add(screen._last_params, _run(_ % 3 != 0, 40.0))
        screen._repaint_graph()
        assert str(screen.query_one("#mon-strip").render())


@pytest.mark.asyncio
async def test_monitor_warns_when_ram_is_starved():
    """Less RAM is worse: dragging the ram slider to its minimum makes the
    synthetic app fail, and the slider (not latency) gets the warning."""
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert await _wait(pilot, lambda: len(screen._hist) >= 1 and not screen._busy)
        by_param = {s.param: s for s in screen.query(Slider)}
        ram = by_param["memory.total_mb"]
        ram.focus()
        await pilot.press("home")
        settled = lambda: not screen._busy and screen._current_params() == screen._last_params  # noqa: E731
        assert await _wait(pilot, settled)
        assert not screen._hist.latest.passed
        assert screen._hist.implicates("memory.total_mb", "down") is not None
        assert ram.warn is True
        assert by_param["network.latency_ms"].warn is False
        assert "ram" in str(screen.query_one("#mon-warn").render())


@pytest.mark.asyncio
async def test_monitor_command_box_runs_on_enter_not_on_keystrokes():
    app = MorphApp(demo=True)
    async with app.run_test(size=(120, 36)) as pilot:
        await pilot.press("m")
        await pilot.pause()
        screen = app.screen
        assert await _wait(pilot, lambda: len(screen._hist) >= 1 and not screen._busy)
        runs = len(screen._hist)
        box = screen.query_one("#mon-command")
        box.focus()
        for ch in "python":
            await pilot.press(ch)
        await pilot.pause(0.6)
        assert not screen._pending and len(screen._hist) == runs  # no run per keystroke
        await pilot.press("enter")
        assert await _wait(pilot, lambda: len(screen._hist) == runs + 1 and not screen._busy)


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

        await pilot.press("right")  # no-op at the ceiling, no new message
        await pilot.pause()
        assert slider.value == 400

        await pilot.press("home")
        await pilot.pause()
        assert slider.value == 0

    assert app.changes == [110, 120, 220, 400, 0]
