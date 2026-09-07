"""Projects screen -- add a GitHub repo or local dir, then open it straight
into Experiment / Monitor / Threshold with its command pre-filled.

Focus model: the table has focus when there are projects (so ``e`` / ``m`` /
``t`` / ``del`` act on the selection); the source box has focus when the list
is empty (so typing works). ``^r`` opens the selection in Experiment from
anywhere, including inside the source box.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual import work
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Checkbox, DataTable, Footer, Input, RichLog

from morph import github, project_setup, projects
from morph.projects import Project
from morph.tui.messages import RunFinished, StatusUpdate
from morph.tui.screens.base import MorphScreen, safe
from morph.tui.theme import palette
from morph.tui.widgets.status_bar import StatusBar

_EMPTY_ROW = ("—", "no projects yet", "type owner/repo or a path above → Connect", "")


class ProjectsScreen(MorphScreen):
    SECTION = "projects"
    SUBTITLE = "add a repo, then run it"

    BINDINGS: ClassVar[list] = [
        Binding("escape", "app.pop_screen", "Back"),
        Binding("ctrl+r", "open('experiment')", "Open", priority=True),
        Binding("e", "open('experiment')", "Experiment", show=False),
        Binding("m", "open('monitor')", "Monitor"),
        Binding("t", "open('threshold')", "Threshold"),
        Binding("delete", "remove", "Remove"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._rows: list[Project] = []
        self._busy = False

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Vertical(id="proj-setup", classes="setup"):
            with Horizontal(classes="row"):
                yield Input(
                    placeholder="owner/repo, a GitHub URL, or a local directory path",
                    id="proj-src", compact=True,
                )
                yield Checkbox("install deps", value=True, id="proj-install", compact=True)
                yield Button("Connect", id="proj-connect", variant="primary", compact=True)
            with Horizontal(classes="row"):
                yield Button("Experiment", id="proj-experiment", compact=True)
                yield Button("Monitor", id="proj-monitor", compact=True)
                yield Button("Threshold", id="proj-threshold", compact=True)
                yield Button("Reinstall", id="proj-reinstall", compact=True)
                yield Button("Remove", id="proj-remove", variant="error", compact=True)
        yield DataTable(id="proj-table")
        yield RichLog(id="proj-log", classes="panel", markup=True, wrap=True, highlight=False)
        yield StatusBar()
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#proj-table", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("id", "name", "source", "command")
        table.border_title = "PROJECTS"
        self.query_one("#proj-log", RichLog).border_title = "LOG"
        self._reload()
        self._focus_default()
        self.status("auth: checking…")
        self._auth_worker()

    def _focus_default(self) -> None:
        if self._rows:
            self.query_one("#proj-table", DataTable).focus()
        else:
            self.query_one("#proj-src", Input).focus()

    @work(thread=True, exclusive=True, group="proj-auth")
    def _auth_worker(self) -> None:
        try:
            source = github.token_source()
        except Exception as exc:
            source = f"unknown ({exc})"
        self.post_message(StatusUpdate(f"auth: {source}"))

    def on_status_update(self, message: StatusUpdate) -> None:
        self.status(Text(str(message.text)), error=message.error)

    # --- data ----------------------------------------------------------------
    def _reload(self) -> None:
        p = palette(self)
        self._rows = projects.list_projects()
        table = self.query_one("#proj-table", DataTable)
        table.clear()
        if not self._rows:
            table.add_row(*[Text(c, style=p.muted) for c in _EMPTY_ROW], key="__empty__")
            return
        for proj in self._rows:
            src = proj.source + (f" {proj.repo}@{proj.commit}" if proj.repo else "")
            cmd = Text(proj.command or "—")
            if proj.deps_failed:
                cmd = Text(f"! {len(proj.deps_failed)} deps  ", style=p.warn)
                cmd.append(proj.command or "—")
            table.add_row(proj.id, proj.name, src, cmd, key=proj.id)

    def _selected(self) -> Project | None:
        table = self.query_one("#proj-table", DataTable)
        if not self._rows:
            return None
        try:
            row_key, _ = table.coordinate_to_cell_key(table.cursor_coordinate)
        except Exception:
            return self._rows[0]
        return next((proj for proj in self._rows if proj.id == row_key.value), self._rows[0])

    # --- connect -----------------------------------------------------------
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid == "proj-connect":
            self.action_connect()
        elif bid == "proj-remove":
            self.action_remove()
        elif bid == "proj-reinstall":
            self.action_reinstall()
        elif bid.startswith("proj-") and bid.split("-", 1)[1] in {"experiment", "monitor", "threshold"}:
            self.action_open(bid.split("-", 1)[1])

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "proj-src":
            self.action_connect()

    def _log(self, text: str | Text) -> None:
        self.query_one("#proj-log", RichLog).write(text)

    def action_reinstall(self) -> None:
        if self._busy:
            return
        proj = self._selected()
        if proj is None:
            self.status("connect a project first", error=True)
            return
        self._busy = True
        self.query_one("#proj-reinstall", Button).disabled = True
        self.query_one("#proj-log", RichLog).clear()
        self._log(Text(f"reinstalling {proj.name}…", style=palette(self).muted))
        self.status(f"reinstalling {proj.name}…")
        self._reinstall_worker(proj.id)

    def _emit_line(self, line: str) -> None:
        self._log(f"[dim]{safe(line)}[/dim]")

    @work(thread=True, exclusive=True, group="proj-work")
    def _reinstall_worker(self, project_id: str) -> None:
        def emit(line: str) -> None:
            self.app.call_from_thread(self._emit_line, line)

        try:
            proj = projects.load(project_id)
            updated = project_setup.reinstall(proj, logger=emit)
            self.post_message(RunFinished(updated))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    def action_connect(self) -> None:
        if self._busy:
            return
        source = self.query_one("#proj-src", Input).value.strip()
        if not source:
            self.status("type owner/repo, a GitHub URL, or a directory path", error=True)
            self.query_one("#proj-src", Input).focus()
            return
        install = self.query_one("#proj-install", Checkbox).value
        self._busy = True
        self.query_one("#proj-connect", Button).disabled = True
        self.query_one("#proj-table", DataTable).loading = True
        self.query_one("#proj-log", RichLog).clear()
        self._log(Text(f"connecting {source}…", style=palette(self).muted))
        self.status(f"connecting {source}…")
        self._connect_worker(source, install)

    @work(thread=True, exclusive=True, group="proj-work")
    def _connect_worker(self, source: str, install: bool) -> None:
        def emit(line: str) -> None:
            self.app.call_from_thread(self._emit_line, line)

        try:
            emit(f"auth: {github.token_source()}")
            proj = project_setup.connect(source, install=install, logger=emit)
            self.post_message(RunFinished(proj))
        except Exception as exc:
            self.post_message(RunFinished(None, exc))

    def on_run_finished(self, message: RunFinished) -> None:
        p = palette(self)
        self._busy = False
        self.query_one("#proj-connect", Button).disabled = False
        self.query_one("#proj-reinstall", Button).disabled = False
        self.query_one("#proj-table", DataTable).loading = False
        if message.error is not None:
            self._log(Text(f"failed: {message.error}", style=p.fail))
            self.status(Text(f"failed: {message.error}"), error=True)
            return
        proj = message.result
        self._reload()
        line = Text(proj.name, style=f"bold {p.pass_}")
        line.append("  ·  ", style=p.muted)
        line.append(proj.command or "no command detected", style=p.text if proj.command else p.warn)
        self._log(line)
        if proj.deps_failed:
            self._log(Text(f"! deps still failing: {', '.join(proj.deps_failed)}", style=p.warn))
        self.query_one("#proj-src", Input).value = ""
        self.status(Text(f"connected {proj.name} · e / m / t opens it"), ok=True)
        self._focus_default()

    # --- actions -----------------------------------------------------------
    def action_remove(self) -> None:
        proj = self._selected()
        if proj is None:
            return
        projects.delete(proj.id)
        self._reload()
        self.status(Text(f"removed {proj.name}"))
        self._focus_default()

    def action_open(self, which: str) -> None:
        proj = self._selected()
        if proj is None:
            self.status("connect a project first", error=True)
            self.query_one("#proj-src", Input).focus()
            return
        if not proj.command:
            self.status(Text(f"{proj.name} has no command; edit it in Experiment"))
        self.app.open_project(proj, which)
