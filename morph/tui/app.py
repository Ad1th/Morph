"""MorphApp -- the Textual application shell."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding

from morph.projects import Project
from morph.tui.commands import MorphCommands
from morph.tui.screens.home import HomeScreen
from morph.tui.theme import MORPH_DARK, MORPH_LIGHT, SEMANTIC_DEFAULTS

COMPACT_WIDTH = 120  # below this: single column, lanes stacked
TALL_HEIGHT = 36     # at or above this: the big wordmark on Home


class MorphApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Morph"
    SUB_TITLE = "test software in environments you don't physically have"
    COMMANDS = App.COMMANDS | {MorphCommands}
    HORIZONTAL_BREAKPOINTS: ClassVar[list] = [(0, "-compact"), (COMPACT_WIDTH, "-wide")]
    VERTICAL_BREAKPOINTS: ClassVar[list] = [(0, "-short"), (TALL_HEIGHT, "-tall")]

    BINDINGS: ClassVar[list] = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f1", "help", "Help", key_display="F1"),
        Binding("question_mark", "help", "Help", key_display="?", show=False),
        Binding("f2", "toggle_theme", "Theme", key_display="F2", show=False),
        Binding("ctrl+g", "home", "Home", priority=True, show=False),
    ]

    def __init__(self, demo: bool = False) -> None:
        super().__init__()
        self.demo = demo
        # Set from the Projects screen; Experiment / Monitor / Threshold read
        # its command + cwd as their defaults.
        self.active_project: Project | None = None
        self.worker_target: str = ""  # set only when a run is explicitly dispatched
        self.register_theme(MORPH_DARK)
        self.register_theme(MORPH_LIGHT)
        self.theme = MORPH_DARK.name

    def get_theme_variable_defaults(self) -> dict[str, str]:
        # Morph's semantic tokens must resolve even before a Morph theme is
        # active (the stylesheet is parsed at startup).
        return {**super().get_theme_variable_defaults(), **SEMANTIC_DEFAULTS}

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())

    # --- actions ------------------------------------------------------------
    def action_toggle_theme(self) -> None:
        self.theme = MORPH_LIGHT.name if self.theme == MORPH_DARK.name else MORPH_DARK.name

    def action_toggle_dark(self) -> None:  # backwards-compatible alias
        self.action_toggle_theme()

    def watch_theme(self, theme: str) -> None:
        for screen in self.screen_stack:
            redraw = getattr(screen, "redraw_theme", None)
            if callable(redraw):
                redraw()

    def action_help(self) -> None:
        from morph.tui.screens.help import HelpScreen

        if isinstance(self.screen, HelpScreen):
            self.pop_screen()
            return
        self.push_screen(HelpScreen(self.screen))

    def action_home(self) -> None:
        """Pop every screen above Home."""
        while len(self.screen_stack) > 2:  # [default, Home, ...]
            self.pop_screen()

    def screen_class(self, name: str):
        from morph.tui.screens.environment import EnvironmentScreen
        from morph.tui.screens.experiment import ExperimentScreen
        from morph.tui.screens.monitor import MonitorScreen
        from morph.tui.screens.projects import ProjectsScreen
        from morph.tui.screens.regressions import RegressionsScreen
        from morph.tui.screens.threshold import ThresholdScreen

        return {
            "experiment": ExperimentScreen,
            "monitor": MonitorScreen,
            "threshold": ThresholdScreen,
            "environment": EnvironmentScreen,
            "projects": ProjectsScreen,
            "regressions": RegressionsScreen,
        }[name]

    def action_goto(self, name: str, then: str = "") -> None:
        """Push a screen by name; ``then`` = ``"run"`` starts it, ``"profile"``
        focuses its profile box."""
        cls = self.screen_class(name)
        if isinstance(self.screen, cls):
            screen = self.screen
        else:
            screen = cls()
            self.push_screen(screen)
        if then == "run" and hasattr(screen, "action_run"):
            self.call_after_refresh(screen.action_run)
        elif then == "profile" and hasattr(screen, "focus_profile"):
            self.call_after_refresh(screen.focus_profile)

    def open_project(self, project: Project, which: str = "experiment") -> None:
        self.active_project = project
        self.push_screen(self.screen_class(which)())
