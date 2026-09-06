"""ThresholdGauge -- a track from `low` to `high` whose uncertainty bracket
visibly collapses onto the failure boundary as the binary search probes.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

_TRACK = 48  # cells between the low and high labels


class ThresholdGauge(Static):
    def __init__(self, parameter: str, low: float, high: float, unit: str = "") -> None:
        super().__init__(classes="gauge")
        self.parameter = parameter
        self.low = low
        self.high = high
        self.unit = unit
        self._safe = low
        self._fail = high
        self._probes: list[tuple[float, bool]] = []  # (value, passed)
        self._boundary: float | None = None

    def on_mount(self) -> None:
        self._repaint()

    # --- state ------------------------------------------------------------
    def probe(self, value: float, passed: bool, safe: float, fail: float) -> None:
        self._probes.append((value, passed))
        self._safe = max(self._safe, safe) if passed else self._safe
        self._fail = min(self._fail, fail)
        if passed:
            self._safe = max(self._safe, value)
        else:
            self._fail = min(self._fail, value)
        self._repaint()

    def finish(self, boundary: float, safe: float, fail: float) -> None:
        self._boundary = boundary
        self._safe, self._fail = safe, fail
        self._repaint()

    # --- rendering ------------------------------------------------------------
    def _pos(self, value: float) -> int:
        span = self.high - self.low or 1.0
        return max(0, min(_TRACK, round((value - self.low) / span * _TRACK)))

    def _track_line(self) -> Text:
        safe_i = self._pos(self._safe)
        fail_i = self._pos(self._fail)
        line = Text()
        for i in range(_TRACK + 1):
            if self._boundary is not None and i == self._pos(self._boundary):
                line.append("▲", style="bold yellow")
            elif i == safe_i:
                line.append("[", style="bold green")
            elif i == fail_i:
                line.append("]", style="bold red3")
            elif safe_i < i < fail_i:
                line.append("░", style="yellow")   # still-uncertain zone
            elif i < safe_i:
                line.append("━", style="green")     # known safe
            else:
                line.append("━", style="red3")      # known failing
        return line

    def _probe_line(self) -> Text:
        t = Text("probes  ", style="dim")
        for value, passed in self._probes[-14:]:
            t.append(f"{value:g}", style="green" if passed else "red3")
            t.append("●" if passed else "✗", style="green" if passed else "red3")
            t.append(" ")
        return t

    def _summary(self) -> Text:
        u = f" {self.unit}" if self.unit else ""
        if self._boundary is not None:
            return Text(
                f"boundary ≈ {self._boundary:g}{u}   (safe {self._safe:g} / fail {self._fail:g})",
                style="bold yellow",
            )
        return Text(
            f"narrowing…   safe ≤ {self._safe:g}{u}   fail ≥ {self._fail:g}{u}", style="dim"
        )

    def _repaint(self) -> None:
        header = Text(self.parameter, style="bold cyan")
        scale = Text(f"{self.low:g}", style="dim")
        scale.append(" " * (_TRACK - len(f"{self.low:g}") - len(f"{self.high:g}") + 1))
        scale.append(f"{self.high:g}", style="dim")
        self.update(Group(header, self._track_line(), scale, self._probe_line(), self._summary()))
