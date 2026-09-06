"""ConditionLane -- one row of the live experiment console.

Shows a condition's trials landing one by one (green pass / red fail), a
failure-rate bar, the running count, and -- only once the batch is complete --
its Fisher's-exact p-value, effect, and a verdict stamp.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

_PASS_STYLE = "green"
_FAIL_STYLE = "red3"
_BAR_WIDTH = 24

_EFFECT_STAMP = {
    "significant_increase": ("  SIGNIFICANT ↑  ", "bold white on red3"),
    "significant_decrease": ("  SIGNIFICANT ↓  ", "bold white on green"),
    "no_effect": ("  no effect  ", "dim"),
}


class ConditionLane(Static):
    """A self-rendering lane. Drive it with add_trial / finish / set_comparison."""

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

    def on_mount(self) -> None:
        self._redraw()

    # --- state transitions --------------------------------------------------
    def add_trial(self, passed: bool) -> None:
        self._marks.append(passed)
        if not passed:
            self._failures += 1
        self._rate = self._failures / len(self._marks)
        self._redraw()

    def finish(self, failures: int, rate: float) -> None:
        self._failures = failures
        self._rate = rate
        self._done = True
        self._redraw()

    def set_comparison(self, p_value: float | None, effect_label: str | None) -> None:
        self._p_value = p_value
        self._effect = effect_label
        self._redraw()

    # --- rendering --------------------------------------------------------------
    def _headline(self) -> Text:
        line = Text()
        line.append(f"{self.label:<15} ", style="bold" if self.is_baseline else "bold cyan")
        denom = self.total if self._done else len(self._marks)
        line.append(f"{self._failures}/{denom} fail", style="dim")
        if self._p_value is not None:
            hot = self._p_value < 0.05
            line.append(f"   p={self._p_value:.4g}", style="bold yellow" if hot else "dim")
        if self._effect:
            text, style = _EFFECT_STAMP.get(self._effect, (f"  {self._effect}  ", "dim"))
            line.append("  ")
            line.append(text, style=style)
        return line

    def _ticks(self) -> Text:
        t = Text()
        for passed in self._marks:
            t.append("● " if passed else "✗ ", style=_PASS_STYLE if passed else _FAIL_STYLE)
        t.append("· " * max(self.total - len(self._marks), 0), style="grey27")
        return t

    def _bar(self) -> Text:
        filled = round(self._rate * _BAR_WIDTH)
        bar = Text("  ")
        bar.append("█" * filled, style=_FAIL_STYLE)
        bar.append("█" * (_BAR_WIDTH - filled), style="grey30")
        bar.append(f"  {self._rate:.0%} fail rate", style="bold" if self._rate else "dim")
        return bar

    def _redraw(self) -> None:
        self.update(Group(self._headline(), self._ticks(), self._bar()))
