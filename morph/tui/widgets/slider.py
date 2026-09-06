"""Slider -- a focusable horizontal value slider (Textual has no native one).

`←/→` nudge, `Shift+←/→` jump, `Home/End` to the ends. Emits `Slider.Changed`
so the screen can debounce and re-run.
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

_TRACK = 20


class Slider(Static, can_focus=True):
    BINDINGS: ClassVar[list] = [
        Binding("left", "adjust(-1)", "less", show=False),
        Binding("right", "adjust(1)", "more", show=False),
        Binding("shift+left", "adjust(-1, True)", "less x10", show=False),
        Binding("shift+right", "adjust(1, True)", "more x10", show=False),
        Binding("home", "to_end(False)", "min", show=False),
        Binding("end", "to_end(True)", "max", show=False),
    ]

    class Changed(Message):
        def __init__(self, slider: Slider, value: float) -> None:
            self.slider = slider
            self.value = value
            super().__init__()

    def __init__(
        self,
        param: str,
        label: str,
        *,
        minimum: float,
        maximum: float,
        value: float,
        step: float,
        big_step: float | None = None,
        unit: str = "",
        fmt: str = "g",
    ) -> None:
        super().__init__(classes="slider")
        self.param = param
        self.label = label
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.big_step = big_step or step * 10
        self.unit = unit
        self.fmt = fmt
        self.value = self._clamp(value)
        self.status: str = ""      # reconcile badge, set by the screen
        self.muted: bool = False   # host can't really apply this one

    # --- interaction ------------------------------------------------------
    def _clamp(self, v: float) -> float:
        return max(self.minimum, min(self.maximum, v))

    def action_adjust(self, direction: int, big: bool = False) -> None:
        delta = (self.big_step if big else self.step) * direction
        new = self._clamp(round((self.value + delta) / self.step) * self.step)
        if new != self.value:
            self.value = new
            self._redraw()
            self.post_message(self.Changed(self, self.value))

    def action_to_end(self, high: bool) -> None:
        new = self.maximum if high else self.minimum
        if new != self.value:
            self.value = new
            self._redraw()
            self.post_message(self.Changed(self, self.value))

    def set_value(self, value: float, *, notify: bool = False) -> None:
        self.value = self._clamp(value)
        self._redraw()
        if notify:
            self.post_message(self.Changed(self, self.value))

    def set_status(self, status: str, muted: bool) -> None:
        self.status = status
        self.muted = muted
        self._redraw()

    # --- rendering ----------------------------------------------------------
    def on_mount(self) -> None:
        self._redraw()

    def on_focus(self) -> None:
        self._redraw()

    def on_blur(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        span = (self.maximum - self.minimum) or 1.0
        filled = round((self.value - self.minimum) / span * _TRACK)
        knob = "green" if self.has_focus else ("grey50" if self.muted else "cyan")

        line = Text()
        line.append(f"{self.label:<11}", style="bold" if self.has_focus else ("dim" if self.muted else ""))
        line.append("▉" * filled, style=knob)
        line.append("░" * (_TRACK - filled), style="grey30")
        line.append(f"  {self.value:>7{self.fmt}}{self.unit}", style="bold" if self.has_focus else "")
        if self.status:
            badge = {"reproduced": "green", "approximated": "yellow", "unavailable": "red3"}
            line.append(f"  {self.status}", style=badge.get(self.status, "dim"))
        self.update(line)
