"""Monitor screen building blocks: the Slider widget and PerfHistory."""

from __future__ import annotations

import pytest
from textual.app import App, ComposeResult

from morph.schema.telemetry import RunResult, TelemetryData
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
