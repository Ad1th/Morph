"""ExperimentScreen -- the live causal-isolation console.

Pick a target profile + command, hit Run, and watch each condition's trials
land in real time. Baseline runs unconstrained; each candidate isolates one
network variable; the last lane is the full target. When every batch is in,
Fisher's exact runs once per condition and the verdict card resolves.
"""

from __future__ import annotations

import time
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Input, Label, RichLog, Static

from morph.config import load_config
from morph.regression import save_regression
from morph.schema.events import TrialEvent
from morph.schema.profile import EnvironmentProfile
from morph.schema.regression import RegressionArtifact
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import run_experiment_live
from morph.tui.profiles import default_profile_hint, resolve_profile
from morph.tui.widgets.condition_lane import ConditionLane
from morph.tui.widgets.interaction_matrix import InteractionMatrix
from morph.tui.widgets.verdict_card import VerdictCard

_INTERACTION_SET = {"baseline", "latency_only", "loss_only", "full_target"}


class ExperimentScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("ctrl+r", "run", "Run"),
        ("ctrl+s", "save", "Save regression"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._lanes: dict[str, ConditionLane] = {}
        self._rates: dict[str, float] = {}
        self._busy = False
        self._last_profile: EnvironmentProfile | None = None
        self._last_command = ""
        self._last_verdict = ""
        self._project_cwd: str | None = None

    def compose(self) -> ComposeResult:
        project = getattr(self.app, "active_project", None)
        self._project_cwd = project.cwd if project else None
        title = " Experiment · causal isolation "
        if project:
            title += f"·  {project.name} "
        yield Static(title, classes="screen-title")
        with Horizontal(id="setup"):
            yield Label("profile")
            yield Input(placeholder=default_profile_hint(), id="in-profile")
            yield Label("command")
            yield Input(
                value=(project.command if project and project.command else self._cfg.default_command)
                or "",
                placeholder="python -m apps.timeout",
                id="in-command",
            )
            yield Label("trials")
            yield Input(value=str(self._cfg.default_trials), id="in-trials")
            yield Button("Run ▶", id="btn-run", variant="primary")
            yield Input(placeholder="save id", id="in-regid")
            yield Button("Save regression", id="btn-save", variant="success", disabled=True)
        with Horizontal(id="exp-body"):
            yield VerticalScroll(id="lanes")
            yield RichLog(id="exp-log", wrap=True, markup=True, highlight=True)
        yield VerdictCard(id="verdict", classes="hidden")
        yield InteractionMatrix(id="matrix", classes="hidden")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#in-command", Input).focus()

    # --- run ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self.action_run()
        elif event.button.id == "btn-save":
            self.action_save()

    def action_run(self) -> None:
        if self._busy:
            return
        log = self.query_one("#exp-log", RichLog)
        demo = bool(getattr(self.app, "demo", False))

        command = self.query_one("#in-command", Input).value.strip()
        if not command and not demo:
            self.app.bell()
            log.write("[red]enter a command first[/red]")
            return
        try:
            trials = max(2, int(self.query_one("#in-trials", Input).value or "5"))
        except ValueError:
            trials = 5

        self._reset_views()
        self._busy = True
        self.query_one("#btn-run", Button).disabled = True

        if demo:
            log.write("[yellow]DEMO[/yellow] [dim]replaying a recorded checkout-timeout experiment[/dim]")
            self._last_profile = resolve_profile("")
            self._last_command = "python -m apps.pool_retry"
            self._demo_worker()
            return

        try:
            profile = resolve_profile(self.query_one("#in-profile", Input).value)
        except Exception as exc:
            log.write(f"[red]bad profile: {exc}[/red]")
            self._busy = False
            self.query_one("#btn-run", Button).disabled = False
            return

        self._last_profile = profile
        self._last_command = command
        log.write(f"[dim]running {trials} trials/condition · {command}[/dim]")
        self._worker(profile, command, trials)

    def _reset_views(self) -> None:
        lanes = self.query_one("#lanes", VerticalScroll)
        lanes.remove_children()
        self._lanes.clear()
        self._rates.clear()
        self._last_verdict = ""
        self.query_one("#btn-save", Button).disabled = True
        self.query_one("#verdict", VerdictCard).add_class("hidden")
        self.query_one("#matrix", InteractionMatrix).add_class("hidden")
        self.query_one("#exp-log", RichLog).clear()

    @work(thread=True, exclusive=True)
    def _worker(self, profile: EnvironmentProfile, command: str, trials: int) -> None:
        def emit(ev: TrialEvent) -> None:
            self.post_message(EngineEvent(ev))

        try:
            result = run_experiment_live(
                profile, command, trials, timeout=30.0, cwd=self._project_cwd, on_event=emit
            )
            self.post_message(RunFinished(result))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    @work(thread=True, exclusive=True)
    def _demo_worker(self) -> None:
        from morph.tui.demo import play

        try:
            play(lambda ev: self.post_message(EngineEvent(ev)))
            self.post_message(RunFinished(object()))
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
            self._rates[ev.condition] = ev.failure_rate or 0.0

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
            self._last_verdict = ev.classification
            self.query_one("#btn-save", Button).disabled = self._last_profile is None
            self._maybe_show_matrix()

    def action_save(self) -> None:
        log = self.query_one("#exp-log", RichLog)
        if self._last_profile is None or not self._last_verdict:
            log.write("[red]run an experiment first[/red]")
            return
        regression_id = self.query_one("#in-regid", Input).value.strip() or f"morph-{int(time.time())}"
        artifact = RegressionArtifact(
            regression_id=regression_id,
            environment=self._last_profile,
            command=self._last_command,
            expected_exit_code=0,
            expected_max_failure_rate=0.0,
            failure_signature=self._last_verdict,
        )
        try:
            out = save_regression(artifact)
        except Exception as exc:
            log.write(f"[red]save failed: {exc}[/red]")
            return
        self.query_one("#btn-save", Button).disabled = True
        log.write(
            f"[green]saved[/green] [dim]{out}[/dim]  ·  replay:  morph replay {regression_id}"
        )

    def _maybe_show_matrix(self) -> None:
        if not _INTERACTION_SET.issubset(self._rates):
            return
        matrix = self.query_one("#matrix", InteractionMatrix)
        matrix.show(
            "latency",
            "loss",
            neither=self._rates["baseline"],
            a_only=self._rates["latency_only"],
            b_only=self._rates["loss_only"],
            both=self._rates["full_target"],
        )
        matrix.remove_class("hidden")

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
