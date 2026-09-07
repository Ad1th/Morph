"""Screen base classes: shared chrome, status bar, and the cooperative-cancel
runner used by Experiment / Threshold / Regressions / Monitor.

``RunnerScreen.start(fn, ...)`` runs ``fn(on_event=...)`` in a thread worker.
The ``on_event`` it hands the engine raises :class:`RunCancelled` as soon as
the worker is cancelled (Esc / ``c`` / leaving the screen), which unwinds the
engine between trials -- after ``RuntimeController.run`` has already restored
the host in its ``finally`` -- and lands here as ``RunFinished(cancelled=True)``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, ClassVar

from rich.markup import escape
from rich.text import Text
from textual.binding import Binding
from textual.screen import Screen
from textual.worker import Worker, get_current_worker

from morph.schema.events import TrialEvent
from morph.tui.messages import EngineEvent, RunFinished
from morph.tui.orchestrator import RunCancelled, cancellable
from morph.tui.widgets.chrome import ScreenTitle
from morph.tui.widgets.status_bar import StatusBar

WORKER_GROUP = "engine"


def safe(text: object) -> str:
    """Escape user / exception text for a markup-enabled log."""
    return escape(str(text))


class MorphScreen(Screen):
    """Chrome shared by every screen: title, status bar, redraw on theme change."""

    SECTION: ClassVar[str] = ""
    SUBTITLE: ClassVar[str] = ""

    def title_widget(self) -> ScreenTitle:
        project = getattr(self.app, "active_project", None)
        title = ScreenTitle(self.SECTION, self.SUBTITLE)
        if project is not None:
            title.extra = project.name
        return title

    @property
    def status_bar(self) -> StatusBar:
        return self.query_one(StatusBar)

    def status(self, text: str | Text, *, error: bool = False, ok: bool = False) -> None:
        try:
            self.status_bar.message(text, error=error, ok=ok)
        except Exception:
            pass

    def redraw_theme(self) -> None:
        """Repaint every widget that bakes theme colours into Rich output."""
        for widget in self.walk_children(with_self=False):
            for name in ("_redraw", "_repaint", "_paint"):
                fn = getattr(widget, name, None)
                if callable(fn):
                    try:
                        fn()
                    except Exception:
                        pass
                    break

    @property
    def demo(self) -> bool:
        return bool(getattr(self.app, "demo", False))

    @property
    def project_cwd(self) -> str | None:
        project = getattr(self.app, "active_project", None)
        return project.cwd if project else None

    @property
    def project_command(self) -> str | None:
        project = getattr(self.app, "active_project", None)
        return project.command if project else None


class RunnerScreen(MorphScreen):
    """A screen that runs the engine in a cancellable thread worker."""

    BINDINGS: ClassVar[list] = [
        Binding("escape", "back_or_cancel", "Back", priority=True),
        Binding("c", "cancel", "Stop"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._busy = False
        self._trials_seen = 0
        self._worker: Worker | None = None

    @property
    def busy(self) -> bool:
        return self._busy

    # --- worker plumbing -------------------------------------------------------
    def start(
        self,
        fn: Callable[..., Any],
        *args: Any,
        phase: str = "running",
        total: int = 0,
        **kwargs: Any,
    ) -> None:
        """Run ``fn(*args, on_event=emit, **kwargs)`` in a worker; ``fn`` must
        accept ``on_event``. Posts ``EngineEvent`` per event, ``RunFinished`` at
        the end (with ``cancelled=True`` if the user stopped it)."""
        self._busy = True
        self._trials_seen = 0
        self.status_bar.start_run(phase, total)
        self.refresh_bindings()

        def _job() -> None:
            worker = get_current_worker()

            def is_cancelled() -> bool:
                return worker is not None and worker.is_cancelled

            emit = cancellable(lambda ev: self.post_message(EngineEvent(ev)), is_cancelled)
            try:
                if is_cancelled():
                    raise RunCancelled()
                result = fn(*args, on_event=emit, **kwargs)
            except RunCancelled:
                self.post_message(RunFinished(None, cancelled=True))
            except Exception as exc:
                self.post_message(RunFinished(None, exc))
            else:
                self.post_message(RunFinished(result))

        self._worker = self.run_worker(
            _job, name="engine", group=WORKER_GROUP, exclusive=True, thread=True, exit_on_error=False
        )

    def action_cancel(self) -> None:
        if not self._busy:
            return
        self.status("stopping after the current trial…")
        self.workers.cancel_group(self, WORKER_GROUP)

    def action_back_or_cancel(self) -> None:
        if self._busy:
            self.action_cancel()
        else:
            self.app.pop_screen()

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        if action == "cancel":
            return bool(self._busy)
        return True

    def on_unmount(self) -> None:
        self.workers.cancel_group(self, WORKER_GROUP)

    # --- events -----------------------------------------------------------------
    def on_engine_event(self, message: EngineEvent) -> None:
        ev = message.event
        bar = self.status_bar
        if ev.kind == "trial":
            self._trials_seen += 1
            bar.advance()
        elif ev.kind == "phase_start" and ev.phase:
            bar.set_phase(ev.phase)
        elif ev.kind == "evidence" and ev.e_value is not None:
            bar.evidence(ev.condition, ev.e_value)
        elif ev.kind == "search_probe":
            bar.advance()
        self.handle_event(ev)

    def handle_event(self, ev: TrialEvent) -> None:  # pragma: no cover - overridden
        pass

    def on_run_finished(self, message: RunFinished) -> None:
        self._busy = False
        self._worker = None
        self.refresh_bindings()
        if message.cancelled:
            self.status_bar.finish_run("cancelled")
            self.status("run cancelled · host restored", error=True)
        elif message.error is not None:
            self.status_bar.finish_run("failed")
            self.status(Text(f"failed: {message.error}"), error=True)
        else:
            self.status_bar.finish_run("done")
        self.run_finished(message)

    def run_finished(self, message: RunFinished) -> None:  # pragma: no cover - overridden
        pass
