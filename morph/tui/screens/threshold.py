"""Threshold search screen -- a gauge that converges on the failure boundary.

Runs ``search_threshold`` in a thread worker; each ``search_probe`` event
narrows the gauge's uncertainty bracket, and ``phase_done`` locks the boundary.
"""

from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, RichLog, Select, Static

from morph.config import load_config
from morph.schema.events import TrialEvent
from morph.schema.profile import EnvironmentProfile
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import THRESHOLD_PARAMETERS, run_threshold_live
from morph.tui.profiles import resolve_profile
from morph.tui.widgets.threshold_gauge import ThresholdGauge

_UNITS = {"network.latency_ms": "ms", "network.packet_loss_percent": "%"}
_DEFAULT_RANGE = {"network.latency_ms": (0.0, 400.0), "network.packet_loss_percent": (0.0, 20.0)}


class ThresholdScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+r", "run", "Run"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._busy = False
        project = getattr(self.app, "active_project", None)
        self._project_cwd = project.cwd if project else None
        self._project_command = project.command if project else None

    def compose(self) -> ComposeResult:
        title = " Threshold · failure boundary "
        project = getattr(self.app, "active_project", None)
        if project:
            title += f"·  {project.name} "
        yield Static(title, classes="screen-title")
        with Horizontal(id="th-bar"):
            yield Select.from_values(
                THRESHOLD_PARAMETERS, prompt="parameter", id="th-param", allow_blank=False
            )
            yield Input(placeholder="low", value="0", id="th-low")
            yield Input(placeholder="high", value="400", id="th-high")
            yield Input(placeholder="trials", value="3", id="th-trials")
            yield Button("Search ▶", id="th-run", variant="primary")
        with Horizontal(id="th-setup2"):
            yield Input(placeholder="profile.json (blank -> host + latency/loss)", id="th-profile")
            yield Input(
                value=self._project_command or self._cfg.default_command or "",
                placeholder="python -m apps.timeout",
                id="th-command",
            )
        yield Static("", id="th-gauge-wrap")
        yield RichLog(id="th-log", markup=True, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#th-command", Input).focus()

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "th-param":
            lo, hi = _DEFAULT_RANGE.get(str(event.value), (0.0, 400.0))
            self.query_one("#th-low", Input).value = f"{lo:g}"
            self.query_one("#th-high", Input).value = f"{hi:g}"

    # --- run ----------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "th-run":
            self.action_run()

    def _num(self, widget_id: str, fallback: float) -> float:
        try:
            return float(self.query_one(widget_id, Input).value)
        except (ValueError, TypeError):
            return fallback

    def _resolve_profile(self) -> EnvironmentProfile:
        return resolve_profile(self.query_one("#th-profile", Input).value)

    def action_run(self) -> None:
        if self._busy:
            return
        command = self.query_one("#th-command", Input).value.strip()
        log = self.query_one("#th-log", RichLog)
        if not command:
            log.write("[red]enter a command first[/red]")
            return

        parameter = str(self.query_one("#th-param", Select).value)
        low = self._num("#th-low", 0.0)
        high = self._num("#th-high", 400.0)
        trials = max(2, int(self._num("#th-trials", 3)))
        if high <= low:
            log.write("[red]high must exceed low[/red]")
            return

        try:
            profile = self._resolve_profile()
        except Exception as exc:
            log.write(f"[red]bad profile: {exc}[/red]")
            return

        wrap = self.query_one("#th-gauge-wrap", Static)
        wrap.remove_children()
        gauge = ThresholdGauge(parameter, low, high, unit=_UNITS.get(parameter, ""))
        wrap.mount(gauge)
        self._gauge = gauge
        log.clear()
        log.write(f"[dim]searching {parameter} in [{low:g}, {high:g}] · {trials} trials/probe[/dim]")

        self._busy = True
        self.query_one("#th-run", Button).disabled = True
        self._worker(profile, command, parameter, low, high, trials)

    @work(thread=True, exclusive=True)
    def _worker(
        self,
        profile: EnvironmentProfile,
        command: str,
        parameter: str,
        low: float,
        high: float,
        trials: int,
    ) -> None:
        def emit(ev: TrialEvent) -> None:
            self.post_message(EngineEvent(ev))

        try:
            result = run_threshold_live(
                profile, command, parameter, low, high, trials,
                timeout=30.0, cwd=self._project_cwd, on_event=emit,
            )
            self.post_message(RunFinished(result))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    # --- events -----------------------------------------------------------
    def on_engine_event(self, message: EngineEvent) -> None:
        ev = message.event
        gauge = getattr(self, "_gauge", None)
        if gauge is None:
            return
        if ev.kind == "search_probe":
            gauge.probe(
                ev.param_value or 0.0,
                bool(ev.extra.get("passed")),
                ev.safe_value if ev.safe_value is not None else gauge.low,
                ev.failure_value if ev.failure_value is not None else gauge.high,
            )
            self.query_one("#th-log", RichLog).write(
                f"  probe {ev.param_value:g}: {ev.failures}/{ev.total} fail"
            )
        elif ev.kind == "phase_done":
            gauge.finish(
                ev.boundary_estimate or 0.0,
                ev.safe_value or gauge.low,
                ev.failure_value or gauge.high,
            )

    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self.query_one("#th-run", Button).disabled = False
        log = self.query_one("#th-log", RichLog)
        if message.error is not None:
            log.write(f"[red]search failed: {message.error}[/red]")
        else:
            log.write("[green]done[/green]")
