"""Regressions screen -- browse ``.morph/regressions/`` bundles, replay one
live against its recorded environment, and export its CI invariant test.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, DataTable, Footer, Input, Label, RichLog

from morph.regression import export_ci_test, list_regressions
from morph.schema.events import TrialEvent
from morph.tui.messages import RunFinished
from morph.tui.orchestrator import run_replay_live
from morph.tui.screens.base import RunnerScreen
from morph.tui.theme import palette
from morph.tui.widgets.condition_lane import ConditionLane
from morph.tui.widgets.evidence import EvidencePane
from morph.tui.widgets.status_bar import StatusBar
from morph.tui.widgets.verdict_card import VerdictCard

_EMPTY_ROW = ("no bundles yet", "run an experiment and press ^s to save one", "", "")


class RegressionsScreen(RunnerScreen):
    SECTION = "regressions"
    SUBTITLE = "flight recorder"

    BINDINGS: ClassVar[list] = [
        *RunnerScreen.BINDINGS,
        Binding("ctrl+r", "replay", "Replay", priority=True),
        Binding("ctrl+o", "export", "Export test", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._bundles: list = []

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Vertical(id="reg-setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Label("trials")
                yield Input(placeholder="trials", value="3", id="reg-trials", classes="narrow", compact=True)
                yield Button("Replay ▶", id="reg-replay", variant="primary", compact=True)
                yield Button("Stop", id="reg-stop", compact=True, disabled=True)
                yield Button("Export CI test", id="reg-export", compact=True)
        yield DataTable(id="reg-table")
        with Container(id="reg-lane-wrap"):
            yield ConditionLane("replay", 0)
        yield VerdictCard(id="reg-verdict", classes="panel hidden")
        yield EvidencePane(id="reg-evidence", classes="panel hidden")
        yield RichLog(id="reg-log", classes="panel", markup=True, wrap=True, highlight=False)
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#reg-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("regression id", "command", "tolerance", "created")
        table.border_title = "BUNDLES · .morph/regressions"
        self.query_one("#reg-log", RichLog).border_title = "LOG"
        self._reload()
        table.focus()

    def _reload(self) -> None:
        p = palette(self)
        self._bundles = list_regressions()
        table = self.query_one("#reg-table", DataTable)
        table.clear()
        if not self._bundles:
            table.add_row(*[Text(c, style=p.muted) for c in _EMPTY_ROW], key="__empty__")
            self.status("no bundles in .morph/regressions/ yet")
            return
        for art in self._bundles:
            table.add_row(
                art.regression_id,
                (art.command[:48] + "…") if len(art.command) > 49 else art.command,
                f"≤ {art.expected_max_failure_rate:.0%}",
                (art.created_at or "")[:19],
                key=art.regression_id,
            )
        self.status(f"{len(self._bundles)} bundle(s) · ^r replays the selection")

    def _selected(self):
        table = self.query_one("#reg-table", DataTable)
        if not self._bundles:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return self._bundles[0]
        return next((b for b in self._bundles if b.regression_id == row_key.value), self._bundles[0])

    # --- actions ---------------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "reg-replay":
            self.action_replay()
        elif event.button.id == "reg-export":
            self.action_export()
        elif event.button.id == "reg-stop":
            self.action_cancel()

    def action_export(self) -> None:
        art = self._selected()
        if art is None:
            self.status("nothing to export yet", error=True)
            return
        out = Path(f"test_{art.regression_id.replace('-', '_')}_invariant.py")
        try:
            path = export_ci_test(art.regression_id, output_path=out)
        except Exception as exc:
            self.status(Text(f"export failed: {exc}"), error=True)
            return
        self.status(Text(f"wrote {path}"), ok=True)

    def _log(self, text: str | Text) -> None:
        self.query_one("#reg-log", RichLog).write(text)

    def _set_running(self, running: bool) -> None:
        self.query_one("#reg-replay", Button).disabled = running
        self.query_one("#reg-stop", Button).disabled = not running

    def _fresh_lane(self, label: str, trials: int) -> None:
        wrap = self.query_one("#reg-lane-wrap", Container)
        wrap.remove_children()
        wrap.mount(ConditionLane(label, trials))
        self.query_one("#reg-verdict", VerdictCard).add_class("hidden")
        self.query_one("#reg-evidence", EvidencePane).add_class("hidden")
        self.query_one("#reg-log", RichLog).clear()

    def action_replay(self) -> None:
        if self.busy:
            self.status("already replaying · esc / c stops it")
            return
        raw = self.query_one("#reg-trials", Input).value.strip()
        try:
            trials = int(raw or "3")
        except ValueError:
            self.status(f"trials must be a whole number, got {raw!r}", error=True)
            return
        if trials < 1:
            self.status("trials must be at least 1", error=True)
            return

        if self.demo:
            from morph.tui.demo import play, replay_recording

            events = replay_recording()
            self._fresh_lane("replay demo", 3)
            self._log(Text("DEMO  replaying a recorded bundle (synthetic trials, nothing executes)",
                           style=palette(self).muted))
            self._set_running(True)
            self.start(lambda on_event: play(on_event, events), phase="replay", total=3)
            return

        art = self._selected()
        if art is None:
            self.status("no bundle selected · save one from Experiment with ^s", error=True)
            return
        self._fresh_lane(f"replay {art.regression_id}", trials)
        cwd = art.metadata.get("cwd") if isinstance(art.metadata, dict) else None
        self._log(Text(f"replaying {art.regression_id} · {trials} trials"
                       + (f" · cwd {cwd}" if cwd else ""), style=palette(self).muted))
        self._set_running(True)
        self.start(run_replay_live, art.regression_id, trials, 30.0, phase="replay", total=trials)

    # --- events -------------------------------------------------------------
    def handle_event(self, ev: TrialEvent) -> None:
        lane = self.query_one(ConditionLane)
        if ev.kind == "trial":
            lane.add_trial(bool(ev.passed))
            if ev.passed is False:
                pane = self.query_one("#reg-evidence", EvidencePane)
                pane.show_trial(ev)
                pane.remove_class("hidden")
        elif ev.kind == "condition_done":
            lane.finish(ev.failures or 0, ev.failure_rate or 0.0)
        elif ev.kind == "verdict" and ev.classification:
            card = self.query_one("#reg-verdict", VerdictCard)
            card.show(ev.classification, "", None, str(ev.extra.get("summary", "")))
            card.remove_class("hidden")

    def run_finished(self, message: RunFinished) -> None:
        self._set_running(False)
        p = palette(self)
        if message.cancelled:
            self.query_one(ConditionLane).mark_cancelled()
            self._log(Text("cancelled", style=p.warn))
        elif message.error is not None:
            self._log(Text(f"replay failed: {message.error}", style=p.fail))
        else:
            self._log(Text("replay done", style=p.pass_))
