"""ExperimentScreen -- the live causal-isolation console.

Pick a target profile + command, hit Run, and watch each condition's trials
land in real time. Baseline runs unconstrained; each candidate isolates one
network variable; the last lane is the full target.

Sequential mode (default) interleaves baseline and candidates round-robin and
streams each candidate's anytime-valid e-value live; a lane stops as soon as
it is DECISIVE. Batch mode runs fixed-size batches and shows one Fisher
p-value per condition only when its batch completes.
"""

from __future__ import annotations

import time
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import Button, Checkbox, Footer, Input, Label, RichLog, Static

from morph.config import load_config
from morph.regression import save_regression
from morph.schema.events import TrialEvent
from morph.schema.experiment import ExperimentResult, TrialBatch
from morph.schema.profile import EnvironmentProfile
from morph.schema.regression import RegressionArtifact
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import run_experiment_live
from morph.tui.profiles import default_profile_hint, resolve_profile
from morph.tui.screens.base import RunnerScreen, safe
from morph.tui.theme import palette
from morph.tui.widgets.condition_lane import ConditionLane
from morph.tui.widgets.evidence import EvidencePane
from morph.tui.widgets.interaction_matrix import InteractionMatrix
from morph.tui.widgets.status_bar import StatusBar
from morph.tui.widgets.verdict_card import VerdictCard

_INTERACTION_SET = {"baseline", "latency_only", "loss_only", "full_target"}
_EMPTY = "no lanes yet · set a command and press ^r to run causal isolation"


class ExperimentScreen(RunnerScreen):
    SECTION = "experiment"
    SUBTITLE = "causal isolation"

    BINDINGS: ClassVar[list] = [
        *RunnerScreen.BINDINGS,
        Binding("ctrl+r", "run", "Run", priority=True),
        Binding("ctrl+t", "toggle_mode", "Seq/Batch", priority=True),
        Binding("ctrl+s", "save", "Save", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._cfg = load_config()
        self._lanes: dict[str, ConditionLane] = {}
        self._rates: dict[str, float] = {}
        self._counts: dict[str, tuple[int, int]] = {}
        self._last_profile: EnvironmentProfile | None = None
        self._last_command = ""
        self._last_verdict = ""
        self._last_result: ExperimentResult | None = None
        self._mode = "sequential"
        self._verdict_event: TrialEvent | None = None
        self._project_cwd: str | None = None

    def compose(self) -> ComposeResult:
        self._project_cwd = self.project_cwd
        yield self.title_widget()
        with Vertical(id="setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Label("profile")
                yield Input(placeholder=default_profile_hint(), id="in-profile", compact=True)
                yield Label("command")
                yield Input(
                    value=(self.project_command or self._cfg.default_command) or "",
                    placeholder="python -m apps.pool_retry",
                    id="in-command",
                    compact=True,
                )
            with Horizontal(classes="row"):
                yield Label("trials")
                yield Input(
                    value=str(self._cfg.default_trials), id="in-trials", classes="narrow", compact=True
                )
                yield Checkbox("sequential", value=True, id="in-seq", compact=True)
                yield Button("Run ▶", id="btn-run", variant="primary", compact=True)
                yield Button("Stop", id="btn-stop", compact=True, disabled=True)
                yield Input(placeholder="save id", id="in-regid", classes="mid", compact=True)
                yield Button("Save", id="btn-save", variant="success", compact=True, disabled=True)
        with Horizontal(id="exp-body"):
            with VerticalScroll(id="exp-left"):
                yield Static(_EMPTY, id="lanes-empty")
                yield Vertical(id="lanes")
                yield VerdictCard(id="verdict", classes="panel hidden")
                yield InteractionMatrix(id="matrix", classes="panel hidden")
            with Vertical(id="exp-right"):
                yield EvidencePane(id="evidence", classes="panel")
                yield RichLog(id="exp-log", classes="panel", wrap=True, markup=True, highlight=False)
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#exp-log", RichLog).border_title = "LOG"
        self.query_one("#in-command", Input).focus()
        if self.demo:
            self.status("DEMO · press ^r to replay pool_retry at 120 ms + 18 % loss")
        else:
            self.status("set a command, then ^r")

    def focus_profile(self) -> None:
        self.query_one("#in-profile", Input).focus()

    @property
    def mode(self) -> str:
        return self._mode

    # --- run ------------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-run":
            self.action_run()
        elif event.button.id == "btn-save":
            self.action_save()
        elif event.button.id == "btn-stop":
            self.action_cancel()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id == "in-seq":
            self._mode = "sequential" if event.value else "batch"
            self.status(f"mode → {self._mode}")

    def action_toggle_mode(self) -> None:
        box = self.query_one("#in-seq", Checkbox)
        box.value = not box.value

    def _log(self, text: str | Text) -> None:
        self.query_one("#exp-log", RichLog).write(text)

    def _trials(self) -> int | None:
        raw = self.query_one("#in-trials", Input).value.strip()
        try:
            n = int(raw or str(self._cfg.default_trials))
        except ValueError:
            self.status(f"trials must be a whole number, got {raw!r}", error=True)
            return None
        if n < 2:
            self.status("trials must be at least 2", error=True)
            return None
        return n

    def action_run(self) -> None:
        if self.busy:
            self.status("already running · esc / c stops it")
            return
        command = self.query_one("#in-command", Input).value.strip()
        if not command and not self.demo:
            self.app.bell()
            self.status("enter a command first", error=True)
            self.query_one("#in-command", Input).focus()
            return
        trials = self._trials()
        if trials is None:
            return

        if self.demo:
            from morph.tui.demo import DEMO_COMMAND, experiment_recording, play

            events, result = experiment_recording()
            self._reset_views()
            self._mode = "sequential"
            self.query_one("#in-seq", Checkbox).value = True
            self._last_profile = None  # built lazily on save (host capture stays off the UI thread)
            self._last_command = DEMO_COMMAND
            self._last_result = result
            self._log(Text("DEMO  replaying the engine's recorded run of apps/pool_retry "
                           "(120 ms + 18 % loss); every e-value below is one it produced",
                           style=palette(self).muted))
            self._set_running(True)
            self.start(lambda on_event: play(on_event, events),
                       phase="isolation", total=4 * 12)
            return

        try:
            profile = resolve_profile(self.query_one("#in-profile", Input).value)
        except Exception as exc:
            self.status(Text(f"bad profile: {exc}"), error=True)
            self.query_one("#in-profile", Input).focus()
            return

        self._reset_views()
        self._last_profile = profile
        self._last_command = command
        self._last_result = None
        self._log(Text(f"{self._mode}: {trials} trials/condition · {command}", style=palette(self).muted))
        self._set_running(True)
        self.start(
            run_experiment_live, profile, command, trials, 30.0,
            cwd=self._project_cwd, mode=self._mode,
            phase="isolation", total=4 * trials,
        )

    def _set_running(self, running: bool) -> None:
        self.query_one("#btn-run", Button).disabled = running
        self.query_one("#btn-stop", Button).disabled = not running
        self.query_one("#in-seq", Checkbox).disabled = running

    def _reset_views(self) -> None:
        lanes = self.query_one("#lanes", Vertical)
        lanes.remove_children()
        self._lanes.clear()
        self._rates.clear()
        self._counts.clear()
        self._last_verdict = ""
        self._verdict_event = None
        self.query_one("#lanes-empty", Static).add_class("hidden")
        self.query_one("#btn-save", Button).disabled = True
        verdict = self.query_one("#verdict", VerdictCard)
        verdict.clear()
        verdict.add_class("hidden")
        self.query_one("#matrix", InteractionMatrix).add_class("hidden")
        self.query_one("#exp-log", RichLog).clear()
        self.query_one("#evidence", EvidencePane).clear()

    # --- event handling -----------------------------------------------------
    def handle_event(self, ev: TrialEvent) -> None:
        p = palette(self)
        if ev.kind == "phase_start":
            mode = ev.extra.get("mode")
            if mode in ("sequential", "batch"):
                self._mode = mode

        elif ev.kind == "condition_start":
            lane = ConditionLane(ev.condition, ev.total or 0, is_baseline=ev.condition == "baseline")
            self._lanes[ev.condition] = lane
            self.query_one("#lanes", Vertical).mount(lane)

        elif ev.kind == "trial":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.add_trial(bool(ev.passed))
            if ev.passed is False:
                self.query_one("#evidence", EvidencePane).show_trial(ev)
                head = (ev.stderr_tail or ev.stdout_tail or "").strip()
                snippet = head.splitlines()[-1] if head else (ev.error_type or "failed")
                line = Text()
                line.append(ev.condition, style=p.fail)
                line.append(f" trial {(ev.trial_index or 0) + 1}: ", style=p.muted)
                line.append(snippet)
                self._log(line)

        elif ev.kind == "evidence":
            lane = self._lanes.get(ev.condition)
            if lane is not None and ev.e_value is not None:
                was = lane._decisive
                lane.evidence(ev.e_value, ev.evidence_threshold or 20.0, ev.pairs or 0, bool(ev.decisive))
                if ev.decisive and not was:
                    self._flash()
                    line = Text()
                    line.append(ev.condition, style=f"bold {p.evidence}")
                    line.append(f" decisive: E = {ev.e_value:.3g} ≥ {ev.evidence_threshold:g} "
                                f"after {ev.pairs} pairs", style=p.evidence)
                    self._log(line)

        elif ev.kind == "condition_done":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.finish(ev.failures or 0, ev.failure_rate or 0.0)
            self._rates[ev.condition] = ev.failure_rate or 0.0
            self._counts[ev.condition] = (ev.failures or 0, ev.total or 0)

        elif ev.kind == "comparison":
            lane = self._lanes.get(ev.condition)
            if lane is not None:
                lane.set_comparison(
                    ev.p_value, ev.effect_label, e_value=ev.e_value, pairs=ev.pairs,
                    stopped_early=bool(ev.extra.get("stopped_early")),
                )
                if ev.is_significant and ev.effect_label == "significant_increase" and self._mode == "batch":
                    self._flash()

        elif ev.kind == "verdict" and ev.classification:
            self._verdict_event = ev
            self._show_verdict(ev)

    def _show_verdict(self, ev: TrialEvent) -> None:
        card = self.query_one("#verdict", VerdictCard)
        result = self._last_result
        warnings = list(getattr(result, "warnings", None) or []) if result else []
        minimal = self._minimal_set()
        card.show(
            ev.classification or "",
            ev.strongest_condition or "",
            ev.p_value,
            str(ev.extra.get("summary", "")),
            e_value=ev.e_value,
            pairs=self._pairs_for(ev.strongest_condition),
            mode=self._mode,
            warnings=warnings,
            minimal_set=list(minimal) if minimal else None,
        )
        card.remove_class("hidden")
        self._last_verdict = ev.classification or ""
        self.query_one("#btn-save", Button).disabled = self._last_profile is None and not self.demo
        self._maybe_show_matrix()
        self.query_one("#exp-left", VerticalScroll).scroll_end(animate=False)

    def _batches(self) -> dict[str, TrialBatch] | None:
        if not _INTERACTION_SET.issubset(self._counts):
            return None
        return {
            name: TrialBatch(condition_label=name, total_runs=total, failures=failures)
            for name, (failures, total) in self._counts.items()
            if name in _INTERACTION_SET
        }

    def _interaction_probability(self) -> float | None:
        """Posterior P(super-additive) for the 2x2, from the four batches already run."""
        batches = self._batches()
        if batches is None:
            return None
        try:
            from morph.engine.experiment import interaction_probability

            return interaction_probability(
                batches["baseline"], batches["latency_only"], batches["loss_only"], batches["full_target"]
            )
        except Exception:
            return None

    def _minimal_set(self) -> list[str] | None:
        """1-minimal failing condition set (ddmin) over the isolation batches.
        No extra trials: the oracle answers from the batches already run."""
        batches = self._batches()
        if batches is None:
            return None
        try:
            from morph.engine.minimize import ddmin
        except ImportError:
            return None
        by_subset = {
            frozenset(): batches["baseline"],
            frozenset({"latency"}): batches["latency_only"],
            frozenset({"loss"}): batches["loss_only"],
            frozenset({"latency", "loss"}): batches["full_target"],
        }

        def fails(subset: frozenset[str]) -> bool:
            batch = by_subset.get(subset)
            return bool(batch and (batch.failure_rate or 0.0) > 0.5)

        try:
            outcome = ddmin(["latency", "loss"], fails)
        except Exception:
            return None
        if not outcome.reproduced or not outcome.minimal:
            return None
        return sorted(outcome.minimal)

    def _pairs_for(self, condition: str | None) -> int | None:
        lane = self._lanes.get(condition or "")
        return lane._pairs if lane is not None else None

    def _demo_profile(self) -> EnvironmentProfile:
        """The recorded run's target: this host + 120 ms / 18 % loss."""
        from morph.tui.profiles import implicit_high_latency

        profile = implicit_high_latency()
        profile.network.latency_ms.value = 120.0
        profile.network.packet_loss_percent.value = 18.0
        return profile

    def action_save(self) -> None:
        if not self._last_verdict:
            self.status("run an experiment first", error=True)
            return
        if self._last_profile is None:
            if not self.demo:
                self.status("run an experiment first", error=True)
                return
            self._last_profile = self._demo_profile()
        regression_id = self.query_one("#in-regid", Input).value.strip() or f"morph-{int(time.time())}"
        strongest = self._verdict_event.strongest_condition if self._verdict_event else None
        artifact = RegressionArtifact(
            regression_id=regression_id,
            environment=self._last_profile,
            command=self._last_command,
            expected_exit_code=0,
            expected_max_failure_rate=0.0,
            failure_signature=strongest if strongest and strongest != "none" else None,
            metadata={
                "cwd": self._project_cwd,
                "classification": self._last_verdict,
                "mode": self._mode,
            },
        )
        try:
            out = save_regression(artifact)
        except Exception as exc:
            self.status(Text(f"save failed: {exc}"), error=True)
            return
        self.query_one("#btn-save", Button).disabled = True
        self.status(Text(f"saved {out}  ·  replay: morph replay {regression_id}"), ok=True)
        self._log(f"[{palette(self).pass_}]saved[/] {safe(out)}")

    def _maybe_show_matrix(self) -> None:
        if not _INTERACTION_SET.issubset(self._rates):
            return
        matrix = self.query_one("#matrix", InteractionMatrix)
        prob = self._interaction_probability()
        matrix.show(
            "latency",
            "loss",
            neither=self._rates["baseline"],
            a_only=self._rates["latency_only"],
            b_only=self._rates["loss_only"],
            both=self._rates["full_target"],
            interaction_probability=float(prob) if prob is not None else None,
        )
        matrix.remove_class("hidden")

    def run_finished(self, message: RunFinished) -> None:
        self._set_running(False)
        if message.cancelled:
            for lane in self._lanes.values():
                lane.mark_cancelled()
            self._log(Text("cancelled", style=palette(self).warn))
            return
        if message.error is not None:
            self._log(Text(f"run failed: {message.error}", style=palette(self).fail))
            return
        if isinstance(message.result, ExperimentResult):
            self._last_result = message.result
            for warning in getattr(message.result, "warnings", None) or []:
                self._log(Text(f"⚠ {warning}", style=palette(self).warn))
            if self._verdict_event is not None:
                self._show_verdict(self._verdict_event)
        self._log(Text("done", style=palette(self).pass_))
        if not self._lanes:
            self.query_one("#lanes-empty", Static).remove_class("hidden")

    def _flash(self) -> None:
        self.query_one("#screen-title").flash()
