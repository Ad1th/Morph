"""Projects screen -- add a GitHub repo or local dir, then open it straight
into Experiment / Monitor / Threshold with its command pre-filled.
"""

from __future__ import annotations

from typing import ClassVar

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import Button, Checkbox, DataTable, Footer, Input, RichLog, Static

from morph import github, project_setup, projects
from morph.projects import Project
from morph.tui.messages import RunFinished


class ProjectsScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("escape", "app.pop_screen", "Back"),
        ("e", "open('experiment')", "Experiment"),
        ("m", "open('monitor')", "Monitor"),
        ("t", "open('threshold')", "Threshold"),
        ("delete", "remove", "Remove"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[Project] = []
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Static(" Projects · add a repo, then run it ", classes="screen-title")
        with Horizontal(id="proj-bar"):
            yield Input(placeholder="owner/repo, a GitHub URL, or a local directory path", id="proj-src")
            yield Checkbox("install deps", value=True, id="proj-install")
            yield Button("Connect", id="proj-connect", variant="primary")
        yield DataTable(id="proj-table")
        with Horizontal(id="proj-actions"):
            yield Button("Experiment", id="proj-experiment")
            yield Button("Monitor", id="proj-monitor")
            yield Button("Threshold", id="proj-threshold")
            yield Button("Remove", id="proj-remove", variant="error")
        yield RichLog(id="proj-log", markup=True, wrap=True)
        yield Static("", id="proj-status")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#proj-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("id", "name", "source", "command")
        self._reload()
        self.query_one("#proj-src", Input).focus()
        self._status(f"auth: {github.token_source()}")

    # --- data ----------------------------------------------------------------
    def _reload(self) -> None:
        self._rows = projects.list_projects()
        table = self.query_one("#proj-table", DataTable)
        table.clear()
        for p in self._rows:
            src = p.source + (f" {p.repo}@{p.commit}" if p.repo else "")
            table.add_row(p.id, p.name, src, p.command or "—", key=p.id)

    def _selected(self) -> Project | None:
        table = self.query_one("#proj-table", DataTable)
        if not self._rows:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return self._rows[0]
        return next((p for p in self._rows if p.id == row_key.value), self._rows[0])

    # --- connect -----------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "proj-connect":
            self.action_connect()
        elif bid == "proj-remove":
            self.action_remove()
        elif bid.startswith("proj-") and bid.split("-", 1)[1] in {
            "experiment", "monitor", "threshold"
        }:
            self.action_open(bid.split("-", 1)[1])

    def action_connect(self) -> None:
        if self._busy:
            return
        source = self.query_one("#proj-src", Input).value.strip()
        if not source:
            return
        install = self.query_one("#proj-install", Checkbox).value
        self._busy = True
        self.query_one("#proj-connect", Button).disabled = True
        log = self.query_one("#proj-log", RichLog)
        log.clear()
        log.write(f"[dim]connecting {source}  (auth: {github.token_source()})[/dim]")
        self._connect_worker(source, install)

    @work(thread=True, exclusive=True)
    def _connect_worker(self, source: str, install: bool) -> None:
        def emit(line: str) -> None:
            self.app.call_from_thread(self.query_one("#proj-log", RichLog).write, f"[dim]{line}[/dim]")

        try:
            proj = project_setup.connect(source, install=install, logger=emit)
            self.post_message(RunFinished(proj))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self.query_one("#proj-connect", Button).disabled = False
        log = self.query_one("#proj-log", RichLog)
        if message.error is not None:
            log.write(f"[red]connect failed: {message.error}[/red]")
            return
        proj = message.result
        self._reload()
        cmd = proj.command or "[yellow]no command detected[/yellow]"
        log.write(f"[green]connected[/green] {proj.name}  ·  {cmd}")
        self.query_one("#proj-src", Input).value = ""

    # --- actions -----------------------------------------------------------
    def action_remove(self) -> None:
        proj = self._selected()
        if proj is None:
            return
        projects.delete(proj.id)
        self._reload()
        self._status(f"removed {proj.name}")

    def action_open(self, which: str) -> None:
        proj = self._selected()
        if proj is None:
            self._status("connect a project first")
            return
        if not proj.command:
            self._status(f"{proj.name} has no command; edit it in Experiment")
        self.app.active_project = proj  # type: ignore[attr-defined]

        from morph.tui.screens.experiment import ExperimentScreen
        from morph.tui.screens.monitor import MonitorScreen
        from morph.tui.screens.threshold import ThresholdScreen

        screen = {"experiment": ExperimentScreen, "monitor": MonitorScreen,
                  "threshold": ThresholdScreen}[which]
        self.app.push_screen(screen())

    def _status(self, text: str) -> None:
        self.query_one("#proj-status", Static).update(text)
