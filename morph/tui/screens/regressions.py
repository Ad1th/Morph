"""Regressions screen -- browse ``.morph/regressions/`` bundles, replay one
live, export its CI test.

Phase 4 fills this in.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static


class RegressionsScreen(Screen):
    BINDINGS: ClassVar[list] = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static(" Regressions ", classes="screen-title")
        yield Static("browse & replay saved regression bundles -- Phase 4", classes="placeholder")
        yield Footer()
