"""ExperimentScreen -- the live causal-isolation console.

Phase C wires this to the engine's ``on_event`` hook: condition lanes with
trials landing live, per-condition Fisher's-exact, and a verdict card.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static


class ExperimentScreen(Screen):
    BINDINGS: ClassVar[list] = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static(" Experiment · causal isolation ", classes="screen-title")
        yield Static("baseline vs treatments -> live verdict -- next commit", classes="placeholder")
        yield Footer()
