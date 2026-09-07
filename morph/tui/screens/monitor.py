"""MonitorScreen -- slide the conditions, watch the app's performance respond.

Not a statistical test: a live tuner. Each slider move re-runs the command under
the new conditions (debounced), and a task-manager-style set of sparklines
tracks duration / CPU / memory over the last ~60 runs. When a slider crosses a
boundary the runs have revealed, the warning panel says which one, at what
value, and why -- pulled from the last failing run.
"""

from __future__ import annotations

import os
import random
from typing import ClassVar

import psutil
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, Sparkline, Static, Switch

from morph.config import load_config
from morph.profiler.capture import capture_environment
from morph.runtime.controller import RuntimeController, reconcile_profile_statuses
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult, TelemetryData
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import set_profile_parameter
from morph.tui.perf import PerfHistory
from morph.tui.profiles import implicit_high_latency
from morph.tui.widgets.slider import Slider

_DEBOUNCE_S = 0.35
_RUN_TIMEOUT_S = 15.0
_STATUS_FIELD = {
    "network.latency_ms": ("network", "latency_ms"),
    "network.packet_loss_percent": ("network", "packet_loss_percent"),
    "cpu.cores": ("cpu", "cores"),
    "memory.total_mb": ("memory", "total_mb"),
}


class MonitorScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("space", "toggle_auto", "Auto-run"),
        ("ctrl+r", "run_once", "Run once"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._hist = PerfHistory(capacity=60)
        self._busy = False
        self._pending = False
        self._base: EnvironmentProfile | None = None
        self._last_params: dict[str, float] = {}
        cores = os.cpu_count() or 4
        total_mb = int(psutil.virtual_memory().total / (1024 * 1024))
        self._specs = [
            ("network.latency_ms", "latency", 0.0, 400.0, 60.0, 5.0, 50.0, "ms", ".0f"),
            ("network.packet_loss_percent", "loss", 0.0, 20.0, 0.0, 0.5, 5.0, "%", ".1f"),
            ("cpu.cores", "cpu cores", 1.0, float(cores), float(cores), 1.0, 2.0, "", ".0f"),
            ("memory.total_mb", "ram", 256.0, float(total_mb), float(total_mb),
             256.0, 2048.0, " MB", ".0f"),
        ]

    def compose(self) -> ComposeResult:
        yield Static(" Monitor · live tuning ", classes="screen-title")
        with Horizontal(id="mon-bar"):
            yield Input(
                value=self._cfg.default_command or "",
                placeholder="python -m apps.timeout",
                id="mon-command",
            )
            yield Label("auto-run")
            yield Switch(value=True, id="mon-auto")
            yield Button("Run once", id="mon-run")
        with Horizontal(id="mon-body"):
            with VerticalScroll(id="mon-sliders"):
                for param, label, lo, hi, val, step, big, unit, fmt in self._specs:
                    yield Slider(
                        param, label, minimum=lo, maximum=hi, value=val,
                        step=step, big_step=big, unit=unit, fmt=fmt,
                    )
            with Vertical(id="mon-graph"):
                yield Static("PERFORMANCE  ·  last 60 runs", classes="mon-h")
                yield Static("duration", classes="mon-metric")
                yield Sparkline([0.0], summary_function=max, id="spark-dur")
                yield Static("-", id="val-dur", classes="mon-val")
                yield Static("cpu", classes="mon-metric")
                yield Sparkline([0.0], summary_function=max, id="spark-cpu")
                yield Static("-", id="val-cpu", classes="mon-val")
                yield Static("peak memory", classes="mon-metric")
                yield Sparkline([0.0], summary_function=max, id="spark-mem")
                yield Static("-", id="val-mem", classes="mon-val")
                yield Static("runs", classes="mon-metric")
                yield Static("", id="mon-strip")
        yield Static("adjusting the host to match…", id="mon-warn")
        yield Footer()

    def on_mount(self) -> None:
        try:
            self.query(Slider).first().focus()
        except Exception:
            pass
        self._reconcile()

    # --- host reconcile (slider badges) ----------------------------------
    @work(thread=True, exclusive=True, group="mon-reconcile")
    def _reconcile(self) -> None:
        try:
            base = implicit_high_latency()
            reconciled = reconcile_profile_statuses(base)
            self.app.call_from_thread(self._apply_reconcile, base, reconciled)
        except Exception:
            self.app.call_from_thread(self._apply_reconcile, capture_environment(), None)

    def _apply_reconcile(
        self, base: EnvironmentProfile, reconciled: EnvironmentProfile | None
    ) -> None:
        self._base = base
        for slider in self.query(Slider):
            section, name = _STATUS_FIELD[slider.param]
            status = ""
            if reconciled is not None:
                obj = getattr(reconciled, section, None)
                fld = getattr(obj, name, None) if obj else None
                status = str(getattr(fld, "status", "")) if fld else ""
            slider.set_status(status, muted=status == "unavailable")
        self._warn("ready · slide a condition and watch it re-run")
        if self._auto():
            self._schedule_run()

    # --- run scheduling --------------------------------------------------
    def _auto(self) -> bool:
        try:
            return self.query_one("#mon-auto", Switch).value
        except Exception:
            return False

    def _current_params(self) -> dict[str, float]:
        return {s.param: s.value for s in self.query(Slider)}

    def on_slider_changed(self, event: Slider.Changed) -> None:
        if self._auto():
            self._schedule_run()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "mon-command" and self._auto():
            self._schedule_run()

    def on_switch_changed(self, event: Switch.Changed) -> None:
        if event.switch.id == "mon-auto" and event.value:
            self._schedule_run()

    def action_toggle_auto(self) -> None:
        sw = self.query_one("#mon-auto", Switch)
        sw.value = not sw.value

    def action_run_once(self) -> None:
        self._pending = True
        self._start_run()

    def _schedule_run(self) -> None:
        self._pending = True
        self.set_timer(_DEBOUNCE_S, self._start_run)

    def _start_run(self) -> None:
        if self._busy or not self._pending:
            return
        command = self.query_one("#mon-command", Input).value.strip()
        demo = bool(getattr(self.app, "demo", False))
        if not command and not demo:
            self._warn("[dim]enter a command to start[/dim]")
            return
        self._pending = False
        self._busy = True
        self._last_params = self._current_params()
        self._run_worker(self._last_params, command, demo)

    @work(thread=True, exclusive=True, group="mon-run")
    def _run_worker(self, params: dict[str, float], command: str, demo: bool) -> None:
        try:
            run = self._synthetic_run(params) if demo else self._real_run(params, command)
            self.post_message(RunFinished(run))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    def _real_run(self, params: dict[str, float], command: str) -> RunResult:
        profile = self._base or capture_environment()
        for param, value in params.items():
            try:
                profile = set_profile_parameter(profile, param, value)
            except ValueError:
                pass
        return RuntimeController().run(profile=profile, command=command, timeout=_RUN_TIMEOUT_S)

    def _synthetic_run(self, params: dict[str, float]) -> RunResult:
        lat = params.get("network.latency_ms", 0.0)
        loss = params.get("network.packet_loss_percent", 0.0)
        cores = max(params.get("cpu.cores", 4.0), 1.0)
        ram = max(params.get("memory.total_mb", 8192.0), 128.0)
        duration = 38 + lat * 1.15 + loss * 16 + random.gauss(0, 4)
        cpu = min(99.0, 20 + 130 / cores + random.gauss(0, 3))
        mem = 85 + (4096 / ram) * 55 + random.gauss(0, 5)
        failed = (lat >= 180 and loss >= 1.0) or lat >= 330 or ram < 700
        return RunResult(
            exit_code=1 if failed else 0,
            passed=not failed,
            duration_ms=max(1.0, duration if not failed else duration + 4000),
            peak_memory_mb=round(mem, 1),
            telemetry=TelemetryData(cpu_percent=round(cpu, 1), memory_rss_mb=round(mem, 1)),
            error_type=None if not failed else "LockLostException",
            error_message=None if not failed else "lock for order 8123 expired mid-payment",
            stderr="" if not failed else "LockLostException: lock for order 8123 expired mid-payment",
        )

    # --- results -------------------------------------------------------------
    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        if message.error is not None:
            self._warn(Text(f"run failed: {message.error}", style="red"))
        elif isinstance(message.result, RunResult):
            self._hist.add(self._last_params, message.result)
            self._repaint_graph()
            self._update_warnings()

        if self._auto() and self._current_params() != self._last_params:
            self._pending = True
            self._start_run()

    def _repaint_graph(self) -> None:
        self.query_one("#spark-dur", Sparkline).data = self._hist.durations or [0.0]
        self.query_one("#spark-cpu", Sparkline).data = self._hist.cpu or [0.0]
        self.query_one("#spark-mem", Sparkline).data = self._hist.memory or [0.0]
        s = self._hist.latest
        if s is not None:
            self.query_one("#val-dur", Static).update(f"{s.duration_ms:,.0f} ms")
            self.query_one("#val-cpu", Static).update(f"{s.cpu_percent:.0f} %")
            self.query_one("#val-mem", Static).update(f"{s.peak_mem_mb:,.0f} MB")

        strip = Text()
        for ok in self._hist.outcomes[-100:]:
            strip.append("● " if ok else "✗ ", style="green" if ok else "red3")
        self.query_one("#mon-strip", Static).update(strip)

    def _update_warnings(self) -> None:
        current = self._current_params()
        hot: list[str] = []
        for slider in self.query(Slider):
            boundary = self._hist.implicates(slider.param)
            near = boundary is not None and current[slider.param] >= boundary * 0.9
            slider.set_warn(bool(near))
            if near:
                over = "past" if current[slider.param] >= boundary else "approaching"
                hot.append(f"{slider.label} {current[slider.param]:g} {over} the boundary (~{boundary:g})")

        if not hot:
            passing = bool(self._hist.latest and self._hist.latest.passed)
            self._warn(Text("healthy at these settings" if passing else "watching…",
                            style="green" if passing else "dim"))
            return

        line = Text()
        line.append("⚠  ", style="bold red3")
        line.append("  ;  ".join(hot), style="red3")
        fail = self._hist.last_failure
        if fail is not None:
            why = fail.error_message or (fail.stderr.strip().splitlines()[-1] if fail.stderr else "")
            if fail.error_type or why:
                line.append(f"    {fail.error_type or 'failure'}: {why}", style="dim")
        self._warn(line)

    def _warn(self, text: str | Text) -> None:
        self.query_one("#mon-warn", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mon-run":
            self.action_run_once()
