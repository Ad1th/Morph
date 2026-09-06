"""Regressions screen -- browse ``.morph/regressions/`` bundles, replay one
live against its recorded environment, and export its CI invariant test.
"""

from __future__ import annotations

from pathlib import Path
from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Input, RichLog, Static

from morph.regression import export_ci_test, list_regressions
from morph.schema.events import TrialEvent
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import run_replay_live
from morph.tui.widgets.condition_lane import ConditionLane
from morph.tui.widgets.verdict_card import VerdictCard


class RegressionsScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("r", "replay", "Replay"),
        ("x", "export", "Export CI test"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._bundles: list = []
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Static(" Regressions · flight recorder ", classes="screen-title")
        yield DataTable(id="reg-table")
        with Horizontal(id="reg-bar"):
            yield Input(placeholder="trials", value="3", id="reg-trials")
            yield Button("Replay ▶", id="reg-replay", variant="primary")
            yield Button("Export CI test", id="reg-export")
        yield ConditionLane("replay", 0)
        yield VerdictCard(id="reg-verdict", classes="hidden")
        yield RichLog(id="reg-log", markup=True, wrap=True)
        yield Static(" ", id="reg-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#reg-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("regression id", "command", "tolerance", "created")
        self._reload()

    def _reload(self) -> None:
        self._bundles = list_regressions()
        table = self.query_one("#reg-table", DataTable)
        table.clear()
        for art in self._bundles:
            table.add_row(
                art.regression_id,
                (art.command[:48] + "…") if len(art.command) > 49 else art.command,
                f"≤ {art.expected_max_failure_rate:.0%}",
                (art.created_at or "")[:19],
                key=art.regression_id,
            )
        if not self._bundles:
            self._status("no bundles in .morph/regressions/ yet")
        else:
            self._status(f"{len(self._bundles)} bundle(s)")

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

    def action_export(self) -> None:
        art = self._selected()
        if art is None:
            return
        out = Path(f"test_{art.regression_id.replace('-', '_')}_invariant.py")
        try:
            path = export_ci_test(art.regression_id, output_path=out)
        except Exception as exc:
            self._status(f"[red]export failed: {exc}[/red]")
            return
        self._status(f"[green]wrote {path}[/green]")

    def action_replay(self) -> None:
        if self._busy:
            return
        art = self._selected()
        if art is None:
            return
        try:
            trials = max(2, int(self.query_one("#reg-trials", Input).value or "3"))
        except ValueError:
            trials = 3

        old = self.query_one(ConditionLane)
        lane = ConditionLane(f"replay {art.regression_id}", trials)
        self.mount(lane, after=self.query_one("#reg-bar"))
        old.remove()
        self.query_one("#reg-verdict", VerdictCard).add_class("hidden")
        self.query_one("#reg-log", RichLog).clear()

        self._busy = True
        self.query_one("#reg-replay", Button).disabled = True
        self._status(f"replaying {art.regression_id} · {trials} trials")
        self._worker(art.regression_id, trials)

    @work(thread=True, exclusive=True)
    def _worker(self, regression_id: str, trials: int) -> None:
        def emit(ev: TrialEvent) -> None:
            self.post_message(EngineEvent(ev))

        try:
            result = run_replay_live(regression_id, trials, timeout=30.0, on_event=emit)
            self.post_message(RunFinished(result))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    # --- events -------------------------------------------------------------
    def on_engine_event(self, message: EngineEvent) -> None:
        ev = message.event
        lane = self.query_one(ConditionLane)
        if ev.kind == "trial":
            lane.add_trial(bool(ev.passed))
        elif ev.kind == "condition_done":
            lane.finish(ev.failures or 0, ev.failure_rate or 0.0)
        elif ev.kind == "verdict" and ev.classification:
            card = self.query_one("#reg-verdict", VerdictCard)
            card.show(ev.classification, "", None, str(ev.extra.get("summary", "")))
            card.remove_class("hidden")

    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self.query_one("#reg-replay", Button).disabled = False
        if message.error is not None:
            self._status(f"[red]replay failed: {message.error}[/red]")
        else:
            self._status("replay done")

    def _status(self, text: str) -> None:
        self.query_one("#reg-status", Static).update(text)
