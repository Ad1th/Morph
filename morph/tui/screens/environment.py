"""Environment screen -- capture the host, build a target profile, and see it
reconciled field-by-field (REPRODUCED / APPROXIMATED / UNAVAILABLE).

Phase 3 fills this in with an editable ProfileDiff.
"""

from __future__ import annotations

from typing import ClassVar

from textual.app import ComposeResult
from textual.screen import Screen
from textual.widgets import Footer, Static


class EnvironmentScreen(Screen):
    BINDINGS: ClassVar[list] = [("escape", "app.pop_screen", "Back")]

    def compose(self) -> ComposeResult:
        yield Static(" Environment ", classes="screen-title")
        yield Static("capture / build / reconcile a target profile -- Phase 3", classes="placeholder")
        yield Footer()
