"""HelpScreen -- ``?`` / ``F1``: every binding on the current screen, plus the
app-wide ones, in one modal."""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import ModalScreen, Screen
from textual.widgets import Static

from morph.tui.theme import palette

_KEY_DISPLAY = {
    "escape": "esc", "question_mark": "?", "ctrl+r": "^r", "ctrl+s": "^s", "ctrl+q": "^q",
    "ctrl+g": "^g", "ctrl+p": "^p", "ctrl+t": "^t", "ctrl+n": "^n", "ctrl+o": "^o",
    "ctrl+d": "^d", "space": "space", "delete": "del", "f1": "F1", "f2": "F2",
}

_EXTRA: dict[str, list[tuple[str, str]]] = {
    "MonitorScreen": [
        ("←/→", "nudge the focused slider"),
        ("shift+←/→", "jump x10"),
        ("home/end", "slider min / max"),
        ("tab", "next slider / control"),
        ("enter", "run the command (in the command box)"),
    ],
    "EnvironmentScreen": [
        ("↑/↓", "select a profile row"),
        ("enter", "apply the edit (in the edit box)"),
    ],
    "ProjectsScreen": [("↑/↓", "select a project"), ("enter", "connect (in the source box)")],
    "RegressionsScreen": [("↑/↓", "select a bundle")],
    "HomeScreen": [("tab / enter", "move between cards / open")],
}


def binding_rows(screen: Screen) -> list[tuple[str, str, str]]:
    """``(key, description, scope)`` for every binding the user can press now."""
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(bindings, scope: str) -> None:
        for b in bindings:
            binding = b if isinstance(b, Binding) else Binding(*b)
            if not binding.description:
                continue
            key = binding.key_display or _KEY_DISPLAY.get(binding.key, binding.key)
            if binding.key in seen:
                continue
            seen.add(binding.key)
            rows.append((key, binding.description, scope))

    add(getattr(screen, "BINDINGS", []), screen.__class__.__name__.removesuffix("Screen"))
    for key, desc in _EXTRA.get(screen.__class__.__name__, []):
        rows.append((key, desc, "widgets"))
    add(getattr(screen.app, "BINDINGS", []), "app")
    rows.append(("^p", "command palette", "app"))
    return rows


class HelpScreen(ModalScreen[None]):
    BINDINGS: ClassVar[list] = [
        Binding("escape", "dismiss", "Close", priority=True),
        Binding("question_mark", "dismiss", "Close", show=False),
        Binding("f1", "dismiss", "Close", show=False),
    ]

    def __init__(self, for_screen: Screen) -> None:
        super().__init__()
        self._for = for_screen

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="help-box"):
            yield Static("", id="help-body")

    def on_mount(self) -> None:
        p = palette(self)
        box = self.query_one("#help-box", VerticalScroll)
        name = self._for.__class__.__name__.removesuffix("Screen").upper()
        box.border_title = f"KEYS · {name}"
        box.border_subtitle = "esc closes"
        body = Text()
        current = ""
        for key, desc, scope in binding_rows(self._for):
            if scope != current:
                if current:
                    body.append("\n")
                body.append(f"{scope.upper()}\n", style=f"bold {p.muted}")
                current = scope
            body.append(f"  {key:<12}", style=f"bold {p.evidence}")
            body.append(f"{desc}\n", style=p.text)
        self.query_one("#help-body", Static).update(body)

    def action_dismiss(self) -> None:
        self.dismiss(None)
