"""ConditionLane -- one row of the live experiment console.

Line 1: the condition, its running count, and the trial ticks (● pass / ✗ fail).
Line 2: in *sequential* mode a live evidence readout -- an e-value sparkline
plus a bar growing toward the ``│`` threshold line (E >= K/alpha); a DECISIVE stamp
and "stopped early after N pairs" once crossed. In *batch* mode the failure-rate
bar, and the Fisher p-value only once the batch is complete (no peeking).
"""

from __future__ import annotations

import math

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from morph.tui.theme import palette

_SPARK = "▁▂▃▄▅▆▇█"
_EFFECT_STAMP = {
    "significant_increase": " SIGNIFICANT ↑ ",
    "significant_decrease": " SIGNIFICANT ↓ ",
    "no_effect": " no effect ",
}


class ConditionLane(Static):
    """A self-rendering lane. Drive it with add_trial / evidence / finish / set_comparison."""

    def __init__(self, label: str, total: int, *, is_baseline: bool = False) -> None:
        super().__init__(classes="lane")
        self.label = label
        self.total = total
        self.is_baseline = is_baseline
        self._marks: list[bool] = []
        self._failures = 0
        self._done = False
        self._rate: float = 0.0
        self._p_value: float | None = None
        self._effect: str | None = None
        self._e_history: list[float] = []
        self._e_value: float | None = None
        self._threshold: float | None = None
        self._pairs: int | None = None
        self._decisive = False
        self._stopped_early = False
        self._cancelled = False

    def on_mount(self) -> None:
        self.border_title = self.label.upper()
        self._redraw()

    def on_resize(self) -> None:
        self._redraw()

    # --- state transitions --------------------------------------------------
    def add_trial(self, passed: bool) -> None:
        self._marks.append(passed)
        if not passed:
            self._failures += 1
        self._rate = self._failures / len(self._marks)
        self._redraw()

    def evidence(self, e_value: float, threshold: float, pairs: int, decisive: bool) -> None:
        self._e_value = e_value
        self._threshold = threshold
        self._pairs = pairs
        self._e_history.append(e_value)
        if decisive and not self._decisive:
            self._decisive = True
            self.add_class("decisive")
        self._redraw()

    def finish(self, failures: int, rate: float) -> None:
        self._failures = failures
        self._rate = rate
        self._done = True
        if self._decisive and self.total and len(self._marks) < self.total:
            self._stopped_early = True
        self._redraw()

    def set_comparison(
        self,
        p_value: float | None,
        effect_label: str | None,
        *,
        e_value: float | None = None,
        pairs: int | None = None,
        stopped_early: bool | None = None,
    ) -> None:
        self._p_value = p_value
        self._effect = effect_label
        if e_value is not None:
            self._e_value = e_value
        if pairs is not None:
            self._pairs = pairs
        if stopped_early:
            self._stopped_early = True
        self._redraw()

    def mark_cancelled(self) -> None:
        self._cancelled = True
        self._redraw()

    # --- rendering --------------------------------------------------------------
    @property
    def _bar_width(self) -> int:
        width = self.content_size.width or 60
        return max(8, min(30, width - 34))

    def _headline(self) -> Text:
        p = palette(self)
        line = Text()
        denom = self.total or len(self._marks)
        line.append(f"{self._failures}/{denom} fail", style=p.muted)
        if self._stopped_early:
            line.append(f"  · stopped early after {len(self._marks)} pairs", style=p.evidence)
        elif self._cancelled:
            line.append("  · cancelled", style=p.warn)
        line.append("  ")
        shown = self._marks[-self._bar_width - 10:]
        for passed in shown:
            line.append("●" if passed else "✗", style=p.pass_ if passed else p.fail)
        remaining = max((self.total or 0) - len(self._marks), 0)
        if not self._done and not self._cancelled:
            line.append("·" * min(remaining, max(0, self._bar_width + 10 - len(shown))), style=p.track)
        return line

    def _rate_bar(self) -> Text:
        p = palette(self)
        width = self._bar_width
        filled = round(self._rate * width)
        bar = Text()
        bar.append("rate ", style=p.muted)
        bar.append("█" * filled, style=p.fail)
        bar.append("█" * (width - filled), style=p.track)
        bar.append(f" {self._rate:>4.0%}", style=f"bold {p.text}" if self._rate else p.muted)
        if self._p_value is not None and self._done:
            hot = self._p_value < 0.05
            bar.append(f"   p={self._p_value:.3g}", style=f"bold {p.evidence}" if hot else p.muted)
        if self._effect:
            stamp = _EFFECT_STAMP.get(self._effect, f" {self._effect} ")
            if self._effect == "significant_increase":
                style = f"bold {p.ink_on_fail} on {p.fail}"
            elif self._effect == "significant_decrease":
                style = f"bold {p.ink_on_pass} on {p.pass_}"
            else:
                style = p.muted
            bar.append("  ")
            bar.append(stamp, style=style)
        return bar

    def _evidence_line(self) -> Text:
        p = palette(self)
        width = self._bar_width
        line = Text()
        e = self._e_value if self._e_value is not None else 1.0
        k = self._threshold or 20.0
        line.append(f"E {e:>6.3g} ", style=f"bold {p.evidence}" if e > 1 else p.muted)

        # sparkline of the e-value history on a log scale (8 cells max)
        hist = self._e_history[-8:]
        if hist:
            top = max(math.log10(max(k, 1.0001)), 0.1)
            for v in hist:
                lv = max(0.0, math.log10(max(v, 1e-9)))
                idx = min(len(_SPARK) - 1, int(lv / top * (len(_SPARK) - 1)))
                line.append(_SPARK[idx], style=p.evidence if v >= k else p.evidence_dim)
            line.append(" " * (8 - len(hist)))
        line.append(" ")

        # progress bar toward the threshold line (log scale; the line sits at ~85%)
        mark = max(4, int(width * 0.85))
        frac = max(0.0, math.log10(max(e, 1e-9))) / max(math.log10(max(k, 1.0001)), 0.1)
        filled = min(width, int(frac * mark))
        for i in range(width):
            if i == mark:
                line.append("│", style=f"bold {p.text}")
            elif i < filled:
                line.append("▮", style=p.evidence if i < mark else p.fail)
            else:
                line.append("░", style=p.track)
        line.append(f" {k:g}", style=p.muted)
        if self._decisive:
            line.append("  ")
            line.append(" DECISIVE ", style=f"bold {p.ink_on_evidence} on {p.evidence}")
        elif self._pairs:
            line.append(f"  {self._pairs} pairs", style=p.muted)
        if self._p_value is not None and self._done:
            line.append(f"  p≤{self._p_value:.2g}", style=p.muted)
        return line

    def _redraw(self) -> None:
        if not self.is_mounted:
            return
        second = self._rate_bar() if (self.is_baseline or self._e_value is None) else self._evidence_line()
        self.update(Group(self._headline(), second))
