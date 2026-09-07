"""Shared screen chrome: the one-row title bar."""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from morph.tui.theme import palette


class ScreenTitle(Static):
    """``MORPH · EXPERIMENT · causal isolation`` in one row. ``flash()`` tints
    it for 0.6 s without touching layout (used when significance lands)."""

    def __init__(self, section: str, subtitle: str = "", *, id: str | None = "screen-title") -> None:
        super().__init__(id=id, classes="screen-title")
        self.section = section
        self.subtitle = subtitle
        self.extra = ""

    def on_mount(self) -> None:
        self._paint()

    def set_extra(self, extra: str) -> None:
        self.extra = extra
        self._paint()

    def flash(self, seconds: float = 0.6) -> None:
        self.add_class("flash")
        self.set_timer(seconds, lambda: self.remove_class("flash"))

    def _paint(self) -> None:
        p = palette(self)
        t = Text()
        t.append(" MORPH", style="bold")
        t.append("  ·  ", style=p.muted)
        t.append(self.section.upper(), style="bold")
        if self.subtitle:
            t.append("  ·  ", style=p.muted)
            t.append(self.subtitle)
        if self.extra:
            t.append("  ·  ", style=p.muted)
            t.append(self.extra, style="bold")
        self.update(t)
