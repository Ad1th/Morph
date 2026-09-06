"""ExperimentScreen -- the live causal-isolation console.

Pick a target profile + command, hit Run, and watch each condition's trials
land in real time. Baseline runs unconstrained; each candidate isolates one
network variable; the last lane is the full target. When every batch is in,
Fisher's exact runs once per condition and the verdict card resolves.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Static

from morph.config import load_config
from morph.profiler.capture import capture_environment
from morph.schema.events import TrialEvent
from morph.schema.profile import EnvironmentProfile, FieldStatus, ProfileField
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import run_experiment_live
from morph.tui.widgets.condition_lane import ConditionLane
from morph.tui.widgets.verdict_card import VerdictCard

_PROFILE_CANDIDATES = ("target_profile.json", "target.json", "profile.json")


def _implicit_high_latency() -> EnvironmentProfile:
    """A sane target when the user hasn't supplied one: the host, plus a
    latency+loss network condition to isolate."""
    profile = capture_environment()
    profile.network = profile.network or _blank_network()
    profile.network.latency_ms = ProfileField(value=150.0, status=FieldStatus.REQUESTED)
    profile.network.packet_loss_percent = ProfileField(value=1.5, status=FieldStatus.REQUESTED)
    return profile


def _blank_network():
    from morph.schema.profile import NetworkInfo

    return NetworkInfo(
        latency_ms=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
        packet_loss_percent=ProfileField(value=0.0, status=FieldStatus.REQUESTED),
    )


class ExperimentScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+r", "run", "Run"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._lanes: dict[str, ConditionLane] = {}
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Static(" Experiment · causal isolation ", classes="screen-title")
        with Horizontal(id="setup"):
            yield Label("profile")
            yield Input(placeholder=self._default_profile(), id="in-profile")
            yield Label("command")
            yield Input(
                value=self._cfg.default_command or "",
                placeholder="python -m apps.timeout",
                id="in-command",
            )
            yield Label("trials")
            yield Input(value=str(self._cfg.default_trials), id="in-trials")
            yield Button("Run ▶", id="btn-run", variant="primary")
        with Horizontal(id="exp-body"):
            yield VerticalScroll(id="lanes")
            yield RichLog(id="exp-log", wrap=True, markup=True, highlight=True)
        yield VerdictCard(id="verdict", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#in-command", Input).focus()

    # --- setup helpers ----------------------------------------------------
    def _default_profile(self) -> str:
        for name in _PROFILE_CANDIDATES:
            if Path(name).is_file():
                return name
        return "(blank -> host + latency/loss)"

    def _resolve_profile(self, raw: str) -> EnvironmentProfile:
        raw = raw.strip()
        if not raw or raw.startswith("("):
            for name in _PROFILE_CANDIDATES:
                if Path(name).is_file():
                    raw = name
                    break
        if raw and Path(raw).is_file():
            return EnvironmentProfile.model_validate_json(Path(raw).read_text(encoding="utf-8"))
        return _implicit_high_latency()

    # --- run ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self.action_run()

    def action_run(self) -> None:
        if self._busy:
            return
        command = self.query_one("#in-command", Input).value.strip()
        if not command:
            self.app.bell()
            self.query_one("#exp-log", RichLog).write("[red]enter a command first[/red]")
            return
        try:
            trials = max(2, int(self.query_one("#in-trials", Input).value or "5"))
        except ValueError:
            trials = 5

        try:
            profile = self._resolve_profile(self.query_one("#in-profile", Input).value)
        except Exception as exc:
            self.query_one("#exp-log", RichLog).write(f"[red]bad profile: {exc}[/red]")
            return

        self._reset_views()
        self._busy = True
        self.query_one("#btn-run", Button).disabled = True
        self.query_one("#exp-log", RichLog).write(
            f"[dim]running {trials} trials/condition · {command}[/dim]"
        )
        self._worker(profile, command, trials)

    def _reset_views(self) -> None:
        lanes = self.query_one("#lanes", VerticalScroll)
        lanes.remove_children()
        self._lanes.clear()
        self.query_one("#verdict", VerdictCard).add_class("hidden")
        self.query_one("#exp-log", RichLog).clear()

    @work(thread=True, exclusive=True)
    def _worker(self, profile: EnvironmentProfile, command: str, trials: int) -> None:
        def emit(ev: TrialEvent) -> None:
            self.post_message(EngineEvent(ev))

        try:
            result = run_experiment_live(profile, command, trials, timeout=30.0, on_event=emit)
            self.post_message(RunFinished(result))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    # --- event handling -----------------------------------------------------
    def on_engine_event(self, message: EngineEvent) -> None:
        ev = message.event
        log = self.query_one("#exp-log", RichLog)

        if ev.kind == "condition_start":
            lane = ConditionLane(ev.condition, ev.total or 0, is_baseline=ev.condition == "baseline")
            self._lanes[ev.condition] = lane
            self.query_one("#lanes", VerticalScroll).mount(lane)

        elif ev.kind == "trial":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.add_trial(bool(ev.passed))
            if ev.passed is False and (ev.stderr_tail or ev.error_type):
                head = ev.stderr_tail or ""
                snippet = head.strip().splitlines()[-1] if head.strip() else (ev.error_type or "")
                log.write(f"[red3]{ev.condition}[/red3] trial {ev.trial_index}: {snippet}")

        elif ev.kind == "condition_done":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.finish(ev.failures or 0, ev.failure_rate or 0.0)

        elif ev.kind == "comparison":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.set_comparison(ev.p_value, ev.effect_label)
                if ev.is_significant and ev.effect_label == "significant_increase":
                    self._flash()

        elif ev.kind == "verdict" and ev.classification:
            card = self.query_one("#verdict", VerdictCard)
            card.show(
                ev.classification,
                ev.strongest_condition or "",
                ev.p_value,
                str(ev.extra.get("summary", "")),
            )
            card.remove_class("hidden")

    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self.query_one("#btn-run", Button).disabled = False
        if message.error is not None:
            self.query_one("#exp-log", RichLog).write(f"[red]run failed: {message.error}[/red]")
        else:
            self.query_one("#exp-log", RichLog).write("[green]done[/green]")

    def _flash(self) -> None:
        self.add_class("significant")
        self.set_timer(0.6, lambda: self.remove_class("significant"))
