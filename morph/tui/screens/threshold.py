"""Threshold search screen -- a gauge that converges on the failure boundary.

Phase 3 fills this in with a live ThresholdGauge fed by ``search_probe`` events.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static


class ThresholdScreen(Screen):
    BINDINGS: ClassVar[list] = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static(" Threshold ", classes="screen-title")
        yield Static("binary-search a parameter's tipping point -- Phase 3", classes="placeholder")
        yield Footer()
