"""MorphApp -- the Textual application shell."""

from __future__ import annotations

from typing import ClassVar

from textual.app import App
from textual.binding import Binding

from morph.projects import Project
from morph.tui.screens.home import HomeScreen


class MorphApp(App):
    CSS_PATH = "app.tcss"
    TITLE = "Morph"
    SUB_TITLE = "test software in environments you don't physically have"

    BINDINGS: ClassVar[list] = [
        Binding("ctrl+q", "quit", "Quit", priority=True),
        Binding("f2", "toggle_dark", "Light/Dark"),
        Binding("escape", "home", "Home", show=True),
    ]

    def __init__(self, demo: bool = False) -> None:
        super().__init__()
        self.demo = demo
        # Set from the Projects screen; Experiment / Monitor / Threshold read
        # its command + cwd as their defaults.
        self.active_project: Project | None = None

    def on_mount(self) -> None:
        self.theme = "textual-dark"
        self.push_screen(HomeScreen())

    def action_toggle_dark(self) -> None:
        self.theme = "textual-light" if self.theme == "textual-dark" else "textual-dark"

    def action_home(self) -> None:
        """Pop every screen above Home."""
        while len(self.screen_stack) > 2:  # [default, Home, ...]
            self.pop_screen()
