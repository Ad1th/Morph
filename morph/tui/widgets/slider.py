"""Slider -- a focusable horizontal value slider (Textual has no native one).

`←/→` nudge, `Shift+←/→` jump, `Home/End` to the ends. Emits `Slider.Changed`
so the screen can debounce and re-run. Carries a fidelity badge (REPRODUCED /
APPROXIMATED / UNAVAILABLE) and a ⚠ when the runs have revealed a boundary
near the current value. ``direction`` says which way is "worse".
"""

from __future__ import annotations

from typing import ClassVar

from rich.text import Text
from textual.binding import Binding
from textual.message import Message
from textual.widgets import Static

from morph.tui.theme import palette, status_style


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
        direction: str = "up",
        choices: list[str] | None = None,
    ) -> None:
        super().__init__(classes="slider")
        self.param = param
        self.label = label
        # A choice slider cycles through labels; its numeric value is the index.
        self.choices = list(choices) if choices else None
        if self.choices:
            minimum, maximum, step, big_step, fmt = 0.0, float(len(self.choices) - 1), 1.0, 1.0, ".0f"
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.big_step = big_step or step * 10
        self.unit = unit
        self.fmt = fmt
        self.direction = direction
        self.value = self._clamp(value)
        self.status: str = ""  # fidelity badge, set by the screen
        self.note: str = ""  # fidelity note (mechanism / reason)
        self.muted: bool = False  # host can't really apply this one
        self.warn: bool = False  # near a boundary the runs have revealed

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

    def display_value(self) -> str:
        """The value as a person reads it: a number with its unit, or a label."""
        if self.choices:
            return self.choices[round(self.value)]
        return f"{self.value:{self.fmt}}{self.unit}"

    def set_status(self, status: str, muted: bool, note: str = "") -> None:
        self.status = status
        self.note = note
        self.muted = muted
        self.tooltip = note or None
        self._redraw()

    def set_warn(self, warn: bool) -> None:
        if warn != self.warn:
            self.warn = warn
            self.set_class(warn, "warn")
            self._redraw()

    # --- rendering ----------------------------------------------------------
    def on_mount(self) -> None:
        self._redraw()

    def on_resize(self) -> None:
        self._redraw()

    def on_focus(self) -> None:
        self._redraw()

    def on_blur(self) -> None:
        self._redraw()

    def _redraw(self) -> None:
        if not self.is_mounted:
            return
        p = palette(self)
        width = self.content_size.width or 60
        badge = self.status.upper() if self.status else ""
        # ⚠ + label + value + unit + badge, the track takes what is left
        fixed = 2 + 11 + 10 + len(self.unit) + (len(badge) + 2 if badge else 0)
        track = max(6, min(30, width - fixed))
        span = (self.maximum - self.minimum) or 1.0
        filled = round((self.value - self.minimum) / span * track)
        knob = p.evidence if self.has_focus else (p.muted if self.muted else p.text)

        line = Text()
        line.append("⚠ " if self.warn else "  ", style=f"bold {p.fail}")
        label_style = f"bold {p.text}" if self.has_focus else (p.muted if self.muted else p.text)
        line.append(f"{self.label:<11}", style=label_style)
        value_style = f"bold {p.text}" if self.has_focus else p.text
        if self.choices:
            # segmented track: one cell per option, the chosen one lit
            idx = round(self.value)
            n = len(self.choices)
            seg = max(1, track // n)
            for i in range(n):
                line.append("▉" * seg if i == idx else "░" * seg, style=knob if i == idx else p.track)
            line.append(f" {self.choices[idx]:>{max(7, len(max(self.choices, key=len)))}}", style=value_style)
        else:
            line.append("▉" * filled, style=knob)
            line.append("░" * (track - filled), style=p.track)
            line.append(f" {self.value:>7{self.fmt}}{self.unit}", style=value_style)
        if badge:
            line.append(f"  {badge}", style=status_style(p, self.status))
        self.update(line)
