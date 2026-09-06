"""Home -- mission control. Four ways in, plus a live host summary."""

from __future__ import annotations

import platform
from typing import ClassVar

from textual.app import ComposeResult
from textual.containers import Container, Grid
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Static

_LOGO = r"""
 __  __  ___  ___ ___ _  _
|  \/  |/ _ \| _ \ _ \ || |
| |\/| | (_) |   /  _/ __ |
|_|  |_|\___/|_|_\_| |_||_|
""".strip("\n")

_CARDS = [
    ("experiment", "Experiment", "baseline vs treatments -> causal verdict"),
    ("threshold", "Threshold", "binary-search a parameter's tipping point"),
    ("environment", "Environment", "capture / build a target profile"),
    ("regressions", "Regressions", "browse & replay saved bundles"),
]


class HomeScreen(Screen):
    BINDINGS: ClassVar[list] = [
        ("e", "open('experiment')", "Experiment"),
        ("t", "open('threshold')", "Threshold"),
        ("n", "open('environment')", "Environment"),
        ("r", "open('regressions')", "Regressions"),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Container(id="home-wrap"):
            yield Static(_LOGO, id="logo")
            yield Static("test software in environments you don't physically have", id="tagline")
            with Grid(id="menu"):
                for card_id, title, desc in _CARDS:
                    yield Button(f"{title}\n[dim]{desc}[/dim]", id=f"card-{card_id}", classes="card")
        yield Static(self._host_line(), id="home-status")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#card-experiment", Button).focus()

    def _host_line(self) -> str:
        mode = "DEMO (recorded)" if getattr(self.app, "demo", False) else "live"
        return (
            f" host: {platform.system().lower()} / {platform.machine()}   "
            f"python {platform.python_version()}   mode: {mode} "
        )

    def action_open(self, which: str) -> None:
        from morph.tui.screens.environment import EnvironmentScreen
        from morph.tui.screens.experiment import ExperimentScreen
        from morph.tui.screens.regressions import RegressionsScreen
        from morph.tui.screens.threshold import ThresholdScreen

        screens = {
            "experiment": ExperimentScreen,
            "threshold": ThresholdScreen,
            "environment": EnvironmentScreen,
            "regressions": RegressionsScreen,
        }
        self.app.push_screen(screens[which]())

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.action_open(event.button.id.removeprefix("card-"))
