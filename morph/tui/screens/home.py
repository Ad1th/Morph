"""Home -- mission control. Six ways in, plus a live host summary."""

from __future__ import annotations

import platform
from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Grid
from textual.widgets import Button, Footer, Static

from morph.tui.screens.base import MorphScreen
from morph.tui.theme import palette
from morph.tui.widgets.status_bar import StatusBar

_LOGO = r"""
 __  __  ___  ___ ___ _  _
|  \/  |/ _ \| _ \ _ \ || |
| |\/| | (_) |   /  _/ __ |
|_|  |_|\___/|_|_\_| |_||_|
""".strip("\n")

_CARDS = [
    ("experiment", "e", "Experiment", "baseline vs conditions → causal verdict"),
    ("monitor", "m", "Monitor", "slide conditions, watch performance live"),
    ("threshold", "t", "Threshold", "locate a parameter's failure boundary"),
    ("environment", "n", "Environment", "capture / shape a target profile"),
    ("projects", "p", "Projects", "add a GitHub repo or dir, then run it"),
    ("regressions", "r", "Regressions", "browse & replay saved bundles"),
]


class HomeScreen(MorphScreen):
    SECTION = "home"
    SUBTITLE = "test software in environments you don't physically have"

    # The cards carry their own key hints, so the footer stays short at 80 cols.
    BINDINGS: ClassVar[list] = [
        Binding("e", "open('experiment')", "Experiment", show=False),
        Binding("m", "open('monitor')", "Monitor", show=False),
        Binding("t", "open('threshold')", "Threshold", show=False),
        Binding("n", "open('environment')", "Environment", show=False),
        Binding("p", "open('projects')", "Projects", show=False),
        Binding("r", "open('regressions')", "Regressions", show=False),
    ]

    def compose(self) -> ComposeResult:
        yield self.title_widget()
        with Container(id="home-wrap"):
            yield Static(_LOGO, id="logo")
            yield Static("M O R P H", id="wordmark")
            yield Static("test software in environments you don't physically have", id="tagline")
            with Grid(id="menu"):
                for card_id, key, title, desc in _CARDS:
                    yield Button(self._card_label(key, title, desc), id=f"card-{card_id}", classes="card")
            yield Static(self._host_line(), id="home-status")
        yield StatusBar()
        yield Footer()

    def _card_label(self, key: str, title: str, desc: str) -> Text:
        p = palette(self)
        label = Text()
        label.append(f"{key} ", style=f"bold {p.evidence}")
        label.append(title, style="bold")
        label.append("\n")
        label.append(desc, style=p.muted)
        return label

    def on_mount(self) -> None:
        self.query_one("#card-experiment", Button).focus()
        mode = "DEMO · recorded run, nothing executes" if self.demo else "LIVE"
        self.status(mode)

    def redraw_theme(self) -> None:
        super().redraw_theme()
        for card_id, key, title, desc in _CARDS:
            self.query_one(f"#card-{card_id}", Button).label = self._card_label(key, title, desc)

    def _host_line(self) -> str:
        return (
            f"host {platform.system().lower()} / {platform.machine()}  ·  "
            f"python {platform.python_version()}"
        )

    def action_open(self, which: str) -> None:
        self.app.action_goto(which)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        assert event.button.id is not None
        self.action_open(event.button.id.removeprefix("card-"))

