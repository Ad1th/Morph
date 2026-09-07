"""MonitorScreen -- slide the conditions, watch the app's performance respond.

Not a statistical test: a live tuner. Each slider move re-runs the command under
the new conditions (debounced), and a task-manager-style set of sparklines
tracks duration / CPU / memory over the last ~60 runs. When a slider crosses a
boundary the runs have revealed, the warning panel says which one, at what
value, and why -- pulled from the last failing run.
"""

from __future__ import annotations

import hashlib
import os
import random
from typing import ClassVar

import psutil
from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Input, Sparkline, Static

from morph.config import load_config
from morph.runtime.controller import RuntimeController
from morph.schema.profile import EnvironmentProfile
from morph.schema.telemetry import RunResult, TelemetryData
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import set_profile_parameter
from morph.tui.perf import PerfHistory
from morph.tui.profiles import PARAMS, fidelity_badges, implicit_high_latency
from morph.tui.screens.base import MorphScreen
from morph.tui.theme import palette
from morph.tui.widgets.slider import Slider
from morph.tui.widgets.status_bar import StatusBar

_DEBOUNCE_S = 0.35
_RUN_TIMEOUT_S = 15.0

# pool_retry's failure narrative for the synthetic (demo) performance model.
_DEMO_ERROR_TYPE = "DeadlineExceeded"
_DEMO_ERROR = "9/12 requests completed in 2607ms (deadline 2400ms, pool 2)"


class ProjectModel:
    """A deterministic performance model for a project Morph cannot run here.

    Seeded from the project's identity (repo and commit, or its path), so the
    same repository always draws the same graphs and crosses the same
    boundaries, and a different repository gets different ones. It stands in
    only when the real command is missing or cannot launch, and every result
    it produces is marked ``simulated`` so nobody mistakes it for a run.
    """

    ERRORS = (
        ("DeadlineExceeded", "request batch missed its deadline under the shaped network"),
        ("LockLostException", "lease expired mid-transaction after retries stalled"),
        ("ConnectionPoolTimeout", "pool exhausted while retries queued behind lost packets"),
        ("MemoryError", "worker pool could not allocate under the memory limit"),
    )

    def __init__(self, key: str) -> None:
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        rng = random.Random(digest[:8])
        self.noise = random.Random(digest[8:16])

        def between(a: float, b: float) -> float:
            return a + (b - a) * rng.random()

        self.key = key
        self.lat_threshold = round(between(110.0, 320.0))
        self.loss_threshold = round(between(0.5, 4.0), 1)
        self.ram_floor = round(between(400.0, 1400.0))
        self.core_floor = 1 if rng.random() < 0.6 else 2
        self.base_ms = between(220.0, 900.0)
        self.lat_gain = between(0.8, 1.7)
        self.loss_gain = between(8.0, 26.0)
        self.base_cpu = between(8.0, 40.0)
        self.base_mem = between(60.0, 240.0)
        self.error_type, self.error = rng.choice(self.ERRORS)

    def failed(self, params: dict[str, float]) -> bool:
        lat = params.get("network.latency_ms", 0.0)
        loss = params.get("network.packet_loss_percent", 0.0)
        cores = params.get("cpu.cores", 4.0)
        ram = params.get("memory.total_mb", 8192.0)
        return (
            (lat >= self.lat_threshold and loss >= self.loss_threshold)
            or lat >= self.lat_threshold * 1.6
            or ram < self.ram_floor
            or cores < self.core_floor
        )

    def run(self, params: dict[str, float]) -> RunResult:
        lat = params.get("network.latency_ms", 0.0)
        loss = params.get("network.packet_loss_percent", 0.0)
        cores = max(params.get("cpu.cores", 4.0), 1.0)
        ram = max(params.get("memory.total_mb", 8192.0), 128.0)
        g = self.noise.gauss
        failed = self.failed(params)
        duration = self.base_ms + lat * self.lat_gain + loss * self.loss_gain + g(0, 12)
        if failed:
            duration = max(duration, self.base_ms * 3.2 + lat * 2.0) + g(0, 40)
        cpu = min(99.0, self.base_cpu + 110 / cores + g(0, 3))
        mem = self.base_mem + (4096 / ram) * 55 + g(0, 4)
        detail = f"{self.error} (latency {lat:.0f} ms, loss {loss:.1f} %, {cores:.0f} cores, {ram:.0f} MB)"
        return RunResult(
            exit_code=1 if failed else 0,
            passed=not failed,
            duration_ms=max(1.0, duration),
            peak_memory_mb=round(mem, 1),
            telemetry=TelemetryData(cpu_percent=round(cpu, 1), memory_rss_mb=round(mem, 1)),
            error_type=self.error_type if failed else None,
            error_message=detail if failed else None,
            stdout=f"[simulated] {'FAIL' if failed else 'PASS'}\n  {detail}",
        )


class MonitorScreen(MorphScreen):
    SECTION = "monitor"
    SUBTITLE = "live tuning"

    BINDINGS: ClassVar[list] = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("space", "toggle_auto", "Auto-run"),
        Binding("ctrl+r", "run_once", "Run once", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._hist = PerfHistory(capacity=60)
        self._busy = False
        self._pending = False
        self._model: ProjectModel | None = None
        self._simulated_reason: str | None = None
        self._base: EnvironmentProfile | None = None
        self._last_params: dict[str, float] = {}
        self._controller: RuntimeController | None = None
        cores = os.cpu_count() or 4
        total_mb = int(psutil.virtual_memory().total / (1024 * 1024))
        self._limits = {"cpu.cores": float(cores), "memory.total_mb": float(total_mb)}

    @property
    def busy(self) -> bool:
        return self._busy

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Vertical(id="mon-setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Input(
                    value=self.project_command or self._cfg.default_command or "",
                    placeholder="command · enter runs it",
                    id="mon-command",
                    compact=True,
                )
                yield Checkbox("auto-run", value=True, id="mon-auto", compact=True)
                yield Button("Run once", id="mon-run", compact=True)
        with Horizontal(id="mon-body"):
            with VerticalScroll(id="mon-sliders"):
                for param, spec in PARAMS.items():
                    hi = self._limits.get(param, spec["high"])
                    if spec["direction"] == "down":
                        val = hi
                    else:
                        val = 60.0 if param.endswith("latency_ms") else 0.0
                    yield Slider(
                        param, spec["label"], minimum=spec["low"], maximum=hi, value=val,
                        step=spec["step"], big_step=spec["big_step"], unit=spec["unit"],
                        fmt=spec["fmt"], direction=spec["direction"],
                    )
                yield Static("", id="mon-warn")
            with VerticalScroll(id="mon-graph"):
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
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#mon-sliders", VerticalScroll).border_title = "CONDITIONS"
        self.query_one("#mon-graph", VerticalScroll).border_title = "PERFORMANCE · last 60 runs"
        try:
            self.query(Slider).first().focus()
        except Exception:
            pass
        self.status("reconciling the host…")
        self.query_one("#mon-sliders", VerticalScroll).loading = True
        self._reconcile()

    # --- host reconcile (slider badges) ----------------------------------
    @work(thread=True, exclusive=True, group="mon-reconcile")
    def _reconcile(self) -> None:
        try:
            base = implicit_high_latency()
            badges = fidelity_badges(base)
            self.app.call_from_thread(self._apply_reconcile, base, badges)
        except Exception as exc:
            self.app.call_from_thread(self._apply_reconcile, None, {}, exc)

    def _apply_reconcile(
        self,
        base: EnvironmentProfile | None,
        badges: dict[str, tuple[str, str]],
        error: Exception | None = None,
    ) -> None:
        self._base = base
        self.query_one("#mon-sliders", VerticalScroll).loading = False
        for slider in self.query(Slider):
            status, note = badges.get(slider.param, ("", ""))
            slider.set_status(status, muted=status == "unavailable", note=note)
        if error is not None:
            self.status(Text(f"reconcile failed: {error}"), error=True)
        else:
            self.status("ready · slide a condition and watch it re-run")
        self._warn(Text("adjust a slider; the last failing run explains itself here",
                        style=palette(self).muted))
        if self._auto():
            self._schedule_run()

    # --- run scheduling --------------------------------------------------
    def _auto(self) -> bool:
        try:
            return self.query_one("#mon-auto", Checkbox).value
        except Exception:
            return False

    def _current_params(self) -> dict[str, float]:
        return {s.param: s.value for s in self.query(Slider)}

    def on_slider_changed(self, event: Slider.Changed) -> None:
        if self._auto():
            self._schedule_run()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "mon-command":
            self.action_run_once()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "mon-auto" and event.value:
            self._schedule_run()

    def action_toggle_auto(self) -> None:
        box = self.query_one("#mon-auto", Checkbox)
        box.value = not box.value

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
        if not command and not self.demo and self._project_model() is None:
            self.status("enter a command to start", error=True)
            return
        self._pending = False
        self._busy = True
        self._last_params = self._current_params()
        self.status_bar.start_run("run", 1)
        self._run_worker(self._last_params, command, self.demo)

    def _project_model(self) -> ProjectModel | None:
        """The per-project simulation, built once from the project's identity."""
        if self._model is not None:
            return self._model
        project = getattr(self.app, "active_project", None)
        if project is None:
            return None
        key = f"{project.repo or project.path}@{project.commit or ''}"
        self._model = ProjectModel(key)
        return self._model

    @work(thread=True, exclusive=True, group="mon-run")
    def _run_worker(self, params: dict[str, float], command: str, demo: bool) -> None:
        if demo:
            self.post_message(RunFinished(self._synthetic_run(params)))
            return
        model = self._project_model()
        reason: str | None = None
        if command:
            try:
                run = self._real_run(params, command)
            except Exception as exc:
                if model is None:
                    self.post_message(RunFinished(None, exc))
                    return
                reason = f"could not launch: {exc}"
            else:
                if not getattr(run, "invalid", False) or model is None:
                    self._simulated_reason = None
                    self.post_message(RunFinished(run))
                    return
                reason = f"invalid trial: {getattr(run, 'invalid_reason', None) or 'command could not run'}"
        elif model is not None:
            reason = "no runnable command detected in this project"
        if model is None:
            self.post_message(RunFinished(None, RuntimeError("enter a command to start")))
            return
        self._simulated_reason = reason
        self.post_message(RunFinished(model.run(params)))

    def _real_run(self, params: dict[str, float], command: str) -> RunResult:
        profile = self._base or implicit_high_latency()
        for param, value in params.items():
            try:
                profile = set_profile_parameter(profile, param, value)
            except ValueError:
                pass
        if self._controller is None:
            self._controller = RuntimeController()
        return self._controller.run(
            profile=profile, command=command, timeout=_RUN_TIMEOUT_S, cwd=self.project_cwd
        )

    def _synthetic_run(self, params: dict[str, float]) -> RunResult:
        """pool_retry-shaped synthetic performance model for --demo: the batch
        misses its deadline once latency and loss stack, or when latency alone
        is extreme, or when RAM is too tight for the worker pool."""
        lat = params.get("network.latency_ms", 0.0)
        loss = params.get("network.packet_loss_percent", 0.0)
        cores = max(params.get("cpu.cores", 4.0), 1.0)
        ram = max(params.get("memory.total_mb", 8192.0), 128.0)
        duration = 558 + lat * 1.15 + loss * 16 + random.gauss(0, 12)
        cpu = min(99.0, 18 + 130 / cores + random.gauss(0, 3))
        mem = 96 + (4096 / ram) * 55 + random.gauss(0, 4)
        failed = (lat >= 180 and loss >= 1.0) or lat >= 330 or ram < 700
        return RunResult(
            exit_code=1 if failed else 0,
            passed=not failed,
            duration_ms=max(1.0, duration if not failed else 2607 + random.gauss(0, 40)),
            peak_memory_mb=round(mem, 1),
            telemetry=TelemetryData(cpu_percent=round(cpu, 1), memory_rss_mb=round(mem, 1)),
            error_type=None if not failed else _DEMO_ERROR_TYPE,
            error_message=None if not failed else _DEMO_ERROR,
            stdout="" if not failed else f"[pool_retry] FAIL\n  {_DEMO_ERROR}",
        )

    # --- results -------------------------------------------------------------
    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self.status_bar.finish_run("")
        if message.error is not None:
            self._warn(Text(f"run failed: {message.error}", style=palette(self).fail))
        elif isinstance(message.result, RunResult):
            self._hist.add(self._last_params, message.result)
            self._repaint_graph()
            self._update_warnings()
            graph = self.query_one("#mon-graph", VerticalScroll)
            if self._simulated_reason:
                model = self._project_model()
                graph.border_title = "PERFORMANCE · SIMULATED · last 60 runs"
                self.status(
                    Text.assemble(
                        ("simulated  ", palette(self).evidence),
                        (self._simulated_reason, ""),
                        (
                            f"  ·  model seeded from {model.key if model else 'project'}",
                            palette(self).muted,
                        ),
                    )
                )
            else:
                graph.border_title = "PERFORMANCE · last 60 runs"

        if self._auto() and self._current_params() != self._last_params:
            self._pending = True
            self._start_run()

    def _repaint_graph(self) -> None:
        p = palette(self)
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
            strip.append("●" if ok else "✗", style=p.pass_ if ok else p.fail)
        self.query_one("#mon-strip", Static).update(strip)

    def _update_warnings(self) -> None:
        p = palette(self)
        current = self._current_params()
        hot: list[str] = []
        for slider in self.query(Slider):
            boundary = self._hist.implicates(slider.param, slider.direction)
            near = None
            if boundary is not None:
                near = PerfHistory.near_boundary(current[slider.param], boundary, slider.direction)
            slider.set_warn(near is not None)
            if near is not None:
                unit = slider.unit.strip()
                value = current[slider.param]
                hot.append(f"{slider.label} {value:g}{unit} {near} the boundary (~{boundary:g}{unit})")

        if not hot:
            passing = bool(self._hist.latest and self._hist.latest.passed)
            self._warn(Text("healthy at these settings" if passing else "watching…",
                            style=p.pass_ if passing else p.muted))
            return

        line = Text()
        line.append("⚠ ", style=f"bold {p.fail}")
        line.append(";  ".join(hot), style=p.fail)
        fail = self._hist.last_failure
        if fail is not None:
            why = fail.error_message or (fail.stderr.strip().splitlines()[-1] if fail.stderr else "")
            if not why and fail.stdout:
                why = fail.stdout.strip().splitlines()[-1]
            if fail.error_type or why:
                line.append(f"\n{fail.error_type or 'failure'}: {why}", style=p.muted)
        self._warn(line)

    def _warn(self, text: str | Text) -> None:
        if isinstance(text, str):
            text = Text(text)
        self.query_one("#mon-warn", Static).update(text)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "mon-run":
            self.action_run_once()
