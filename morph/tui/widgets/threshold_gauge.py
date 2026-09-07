"""ThresholdGauge -- a track from ``low`` to ``high`` on which the failure
boundary is located.

Bayesian mode (default): the gold bracket is the credible interval, which
shrinks with every probe; ``▲`` is the posterior median; a density strip under
the track shows where the posterior mass sits. When the search concludes there
is no boundary in range (never fails / always fails) the gauge says so instead
of pretending the boundary is at zero.

Classic mode: the green known-safe / rose known-failing halves and the
uncertainty band between ``[safe`` and ``fail]`` as bisection narrows it.
"""

from __future__ import annotations

from rich.console import Group
from rich.text import Text
from textual.widgets import Static

from morph.tui.theme import palette

_SPARK = "▁▂▃▄▅▆▇█"


class ThresholdGauge(Static):
    def __init__(
        self,
        parameter: str,
        low: float,
        high: float,
        unit: str = "",
        *,
        bayesian: bool = True,
    ) -> None:
        super().__init__(classes="gauge")
        self.parameter = parameter
        self.low = low
        self.high = high
        self.unit = unit
        self.bayesian = bayesian
        self._safe = low
        self._fail = high
        self._probes: list[tuple[float, bool]] = []  # (value, passed)
        self._boundary: float | None = None
        self._estimate: float | None = None  # running posterior median
        self._probs: dict[str, float] = {}
        self._density: list[float] = []
        self._done = False
        self._outcome: str = ""  # "" | "boundary" | "never_fails" | "always_fails"

    def on_mount(self) -> None:
        self.border_title = f"BOUNDARY · {self.parameter}"
        self._repaint()

    def on_resize(self) -> None:
        self._repaint()

    # --- state ------------------------------------------------------------
    def probe(
        self,
        value: float,
        passed: bool,
        safe: float | None,
        fail: float | None,
        *,
        estimate: float | None = None,
        probs: dict[str, float] | None = None,
    ) -> None:
        self._probes.append((value, passed))
        if self.bayesian:
            if safe is not None:
                self._safe = safe
            if fail is not None:
                self._fail = fail
            self._estimate = estimate
            if probs:
                self._probs = dict(probs)
        else:
            if passed:
                self._safe = max(self._safe, value)
            else:
                self._fail = min(self._fail, value)
        self._repaint()

    def finish(
        self,
        boundary: float | None,
        safe: float | None,
        fail: float | None,
        *,
        outcome: str | None = None,
        posterior: list[dict] | None = None,
        probs: dict[str, float] | None = None,
    ) -> None:
        self._done = True
        if probs:
            self._probs = dict(probs)
        if posterior:
            self._density = [float(pt.get("density", 0.0)) for pt in posterior]
        if boundary is None:
            if outcome in ("never_fails", "always_fails"):
                self._outcome = outcome
            elif safe is not None and fail is None:
                self._outcome = "never_fails"
            elif fail is not None and safe is None:
                self._outcome = "always_fails"
            else:
                self._outcome = "never_fails"
            self._boundary = None
        else:
            self._outcome = "boundary"
            self._boundary = boundary
            self._safe = safe if safe is not None else self._safe
            self._fail = fail if fail is not None else self._fail
        self._repaint()

    @property
    def outcome(self) -> str:
        return self._outcome

    # --- rendering ------------------------------------------------------------
    @property
    def _track(self) -> int:
        width = self.content_size.width or 60
        return max(20, min(100, width - 4))

    def _pos(self, value: float) -> int:
        span = self.high - self.low or 1.0
        return max(0, min(self._track, round((value - self.low) / span * self._track)))

    def _track_line(self) -> Text:
        p = palette(self)
        n = self._track
        line = Text()
        if self._outcome in ("never_fails", "always_fails"):
            colour = p.pass_ if self._outcome == "never_fails" else p.fail
            line.append("━" * (n + 1), style=colour)
            return line
        lo_i = self._pos(self._safe)
        hi_i = self._pos(self._fail)
        marker = self._boundary if self._boundary is not None else self._estimate
        mark_i = self._pos(marker) if marker is not None else None
        for i in range(n + 1):
            if mark_i is not None and i == mark_i:
                line.append("▲", style=f"bold {p.evidence}")
            elif i == lo_i:
                line.append("[", style=f"bold {p.evidence if self.bayesian else p.pass_}")
            elif i == hi_i:
                line.append("]", style=f"bold {p.evidence if self.bayesian else p.fail}")
            elif lo_i < i < hi_i:
                line.append("░", style=p.evidence)
            elif i < lo_i:
                line.append("━", style=p.pass_)
            else:
                line.append("━", style=p.fail)
        return line

    def _density_line(self) -> Text | None:
        p = palette(self)
        if not self.bayesian:
            return None
        n = self._track + 1
        dens = self._density
        if not dens:
            # Before the posterior arrives, sketch it from the credible band.
            lo_i, hi_i = self._pos(self._safe), self._pos(self._fail)
            dens = [1.0 if lo_i <= i <= hi_i else 0.0 for i in range(n)]
        # Resample to the track width.
        out = Text()
        m = len(dens)
        top = max(dens) or 1.0
        for i in range(n):
            j0 = int(i * m / n)
            j1 = max(j0 + 1, int((i + 1) * m / n))
            v = max(dens[j0:j1]) if j0 < m else 0.0
            idx = min(len(_SPARK) - 1, int(v / top * (len(_SPARK) - 1) + 0.5))
            out.append(_SPARK[idx] if v > 0 else " ", style=p.evidence_dim)
        return out

    def _probe_line(self) -> Text:
        p = palette(self)
        t = Text("probes  ", style=p.muted)
        for value, passed in self._probes[-12:]:
            t.append(f"{value:.4g}", style=p.pass_ if passed else p.fail)
            t.append("●" if passed else "✗", style=p.pass_ if passed else p.fail)
            t.append(" ")
        return t

    def _summary(self) -> Text:
        p = palette(self)
        u = f" {self.unit}" if self.unit else ""
        pin = self._probs.get("boundary_in_range")
        if self._outcome == "never_fails":
            t = Text(f"no boundary in [{self.low:g}, {self.high:g}]{u}: never fails here",
                     style=f"bold {p.pass_}")
            if (never := self._probs.get("never_fails")) is not None:
                t.append(f"   P = {never:.2f}", style=p.muted)
            return t
        if self._outcome == "always_fails":
            t = Text(f"no boundary in [{self.low:g}, {self.high:g}]{u}: already failing at {self.low:g}{u}",
                     style=f"bold {p.fail}")
            if (always := self._probs.get("always_fails")) is not None:
                t.append(f"   P = {always:.2f}", style=p.muted)
            return t
        if self._outcome == "boundary" and self._boundary is not None:
            t = Text(f"boundary ≈ {self._boundary:.4g}{u}", style=f"bold {p.evidence}")
            if self.bayesian:
                t.append(f"   90% credible [{self._safe:.4g}, {self._fail:.4g}]", style=p.text)
                if pin is not None:
                    t.append(f"   P(in range) {pin:.2f}", style=p.muted)
            else:
                t.append(f"   safe ≤ {self._safe:g} · fail ≥ {self._fail:g}", style=p.text)
            return t
        if self.bayesian:
            t = Text("narrowing…  ", style=p.muted)
            if self._estimate is not None:
                t.append(f"median {self._estimate:.4g}{u}  ", style=p.evidence)
            t.append(f"90% credible [{self._safe:.4g}, {self._fail:.4g}]", style=p.text)
            if pin is not None:
                t.append(f"   P(in range) {pin:.2f}", style=p.muted)
            return t
        return Text(f"narrowing…   safe ≤ {self._safe:g}{u}   fail ≥ {self._fail:g}{u}", style=p.muted)

    def _repaint(self) -> None:
        if not self.is_mounted:
            return
        p = palette(self)
        n = self._track
        lo, hi = f"{self.low:g}", f"{self.high:g}"
        scale = Text(lo, style=p.muted)
        scale.append(" " * max(1, n + 1 - len(lo) - len(hi)))
        scale.append(hi, style=p.muted)
        parts = [self._track_line()]
        density = self._density_line()
        if density is not None:
            parts.append(density)
        parts += [scale, self._probe_line(), self._summary()]
        self.update(Group(*parts))
