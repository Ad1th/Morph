"""StatusBar -- one docked line above the Footer on every screen.

Left: mode (LIVE / DEMO), project, worker target and a free-form status
message. Right, while a run is in flight: phase, trials done/total, elapsed,
the leading e-value, and a progress bar. Status text is always a ``Text`` so
user-supplied strings (paths, exceptions) can never be parsed as markup.
"""

from __future__ import annotations

import time

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import ProgressBar, Static

from morph.tui.theme import palette


class StatusBar(Horizontal):
    def __init__(self, *, id: str | None = "status-bar") -> None:
        super().__init__(id=id, classes="status-bar")
        self._message: Text = Text("")
        self._phase = ""
        self._done = 0
        self._total = 0
        self._e_value: float | None = None
        self._e_label = ""
        self._started: float | None = None
        self._timer = None

    def compose(self) -> ComposeResult:
        yield Static("", id="status-left", classes="status-left")
        yield Static("", id="status-right", classes="status-right")
        yield ProgressBar(total=1, show_percentage=False, show_eta=False, id="status-progress")

    def on_mount(self) -> None:
        self.query_one("#status-progress", ProgressBar).display = False
        self._paint()

    # --- API ----------------------------------------------------------------
    def message(self, text: str | Text, *, error: bool = False, ok: bool = False) -> None:
        p = palette(self)
        if isinstance(text, Text):
            self._message = text
        else:
            style = p.fail if error else (p.pass_ if ok else p.muted)
            self._message = Text(str(text), style=style)
        self._paint()

    def start_run(self, phase: str, total: int) -> None:
        self._phase = phase
        self._done = 0
        self._total = max(total, 0)
        self._e_value = None
        self._e_label = ""
        self._started = time.monotonic()
        bar = self.query_one("#status-progress", ProgressBar)
        bar.total = max(total, 1)
        bar.progress = 0
        bar.display = True
        if self._timer is None:
            self._timer = self.set_interval(1.0, self._paint)
        self._paint()

    def set_phase(self, phase: str) -> None:
        self._phase = phase
        self._paint()

    def progress(self, done: int, total: int | None = None) -> None:
        self._done = done
        if total is not None:
            self._total = total
            self.query_one("#status-progress", ProgressBar).total = max(total, 1)
        self.query_one("#status-progress", ProgressBar).progress = done
        self._paint()

    def advance(self) -> None:
        self.progress(self._done + 1)

    def evidence(self, label: str, e_value: float) -> None:
        if self._e_value is None or e_value > self._e_value:
            self._e_value = e_value
            self._e_label = label
            self._paint()

    def finish_run(self, phase: str = "done") -> None:
        self._phase = phase
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.query_one("#status-progress", ProgressBar).display = False
        self._paint()

    @property
    def elapsed(self) -> float:
        return 0.0 if self._started is None else time.monotonic() - self._started

    # --- rendering ----------------------------------------------------------
    def _paint(self) -> None:
        if not self.is_mounted:
            return
        p = palette(self)
        app = self.app
        left = Text()
        demo = bool(getattr(app, "demo", False))
        if demo:
            left.append(" DEMO ", style=f"bold {p.ink_on_evidence} on {p.evidence}")
        else:
            left.append(" LIVE ", style=f"bold {p.ink_on_pass} on {p.pass_}")
        project = getattr(app, "active_project", None)
        if project is not None:
            left.append(f" {project.name}", style=p.text)
        worker = getattr(app, "worker_target", None)
        if worker:
            left.append(f" → {worker}", style=p.muted)
        if self._message.plain:
            left.append("  ")
            left.append_text(self._message)
        self.query_one("#status-left", Static).update(left)

        right = Text()
        if self._phase:
            right.append(self._phase, style=f"bold {p.text}" if self._started else p.muted)
        if self._total:
            right.append(f"  {self._done}/{self._total}", style=p.text)
        if self._started is not None:
            mins, secs = divmod(int(self.elapsed), 60)
            right.append(f"  {mins:02d}:{secs:02d}", style=p.muted)
        if self._e_value is not None:
            right.append(f"  E {self._e_value:.3g}", style=f"bold {p.evidence}")
            if self._e_label:
                right.append(f" {self._e_label}", style=p.muted)
        right.append(" ")
        self.query_one("#status-right", Static).update(right)
