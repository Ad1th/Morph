"""VerdictCard -- the plain-language diagnosis at the end of an experiment.

Lines reveal progressively (~600 ms total) so the verdict *lands* rather than
pops; the reveal is a timer on the widget, so it works for the demo replay too.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from morph.tui.theme import palette

# classification -> (headline, one-line meaning, colour role)
_VERDICTS = {
    "environment_caused": (
        "ENVIRONMENT-CAUSED",
        "Baseline is clean. This condition makes the failure appear.",
        "fail",
    ),
    "environment_exposed": (
        "ENVIRONMENT-EXPOSED",
        "The bug is in the app, but this condition makes it fire far more often.",
        "warn",
    ),
    "application_internal": (
        "APPLICATION BUG",
        "Fails on its own, regardless of environment. Not an environment problem.",
        "warn",
    ),
    "no_effect": (
        "NO EFFECT",
        "No condition produced a significant increase in failures.",
        "muted",
    ),
    "compliant": (
        "REGRESSION LOCKED",
        "Replayed within tolerance. The fix holds under the recorded environment.",
        "pass",
    ),
    "violation": (
        "REGRESSION OPEN",
        "Replay exceeded the allowed failure rate. The invariant is not satisfied.",
        "fail",
    ),
}

REVEAL_SECONDS = 0.6


class VerdictCard(Static):
    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._lines: list[Text] = []
        self._shown = 0
        self._timer = None
        self.classification = ""

    def on_mount(self) -> None:
        self.border_title = "VERDICT"

    def show(
        self,
        classification: str,
        strongest_condition: str = "",
        p_value: float | None = None,
        summary: str = "",
        *,
        e_value: float | None = None,
        pairs: int | None = None,
        mode: str = "",
        warnings: list[str] | None = None,
        minimal_set: list[str] | None = None,
        reveal: bool = True,
    ) -> None:
        p = palette(self)
        headline, meaning, role = _VERDICTS.get(classification, (classification.upper(), "", "muted"))
        colour = {"fail": p.fail, "warn": p.warn, "pass": p.pass_, "muted": p.muted}[role]
        self.classification = classification
        self.styles.border = ("round", colour)
        self.border_subtitle = ""

        lines: list[Text] = [Text(headline, style=f"bold {colour}"), Text(meaning, style="italic")]
        if strongest_condition and strongest_condition != "none":
            lines.append(Text(f"strongest condition  →  {strongest_condition}", style=p.text))
        if mode == "sequential" and e_value is not None:
            stat = Text("evidence  →  ", style=p.text)
            stat.append(f"E = {e_value:.3g}", style=f"bold {p.evidence}")
            if pairs:
                stat.append(f"  after {pairs} pairs", style=p.muted)
            if p_value is not None:
                stat.append(f"  anytime p ≤ {p_value:.3g}", style=p.muted)
            lines.append(stat)
        elif p_value is not None:
            stat = Text("Fisher's exact  →  ", style=p.text)
            stat.append(f"p = {p_value:.3g}", style=f"bold {p.evidence}")
            lines.append(stat)
        lines.append(Text(f"classification  →  {classification}", style=p.muted))
        if minimal_set:
            lines.append(Text(f"minimal failing set  →  {', '.join(minimal_set)}", style=p.text))
        for warning in warnings or []:
            lines.append(Text(f"⚠ {warning}", style=p.warn))
        if summary:
            lines.append(Text(summary, style=p.muted))

        self._lines = lines
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        if reveal and len(lines) > 1:
            self._shown = 1
            self._paint()
            self._timer = self.set_interval(REVEAL_SECONDS / len(lines), self._reveal_step)
        else:
            self._shown = len(lines)
            self._paint()

    @property
    def revealed(self) -> bool:
        return self._shown >= len(self._lines)

    def _reveal_step(self) -> None:
        self._shown += 1
        self._paint()
        if self.revealed and self._timer is not None:
            self._timer.stop()
            self._timer = None

    def _paint(self) -> None:
        out = Text()
        for i, line in enumerate(self._lines[: self._shown]):
            if i:
                out.append("\n")
            out.append_text(line)
        self.update(out)

    def clear(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self._lines = []
        self._shown = 0
        self.classification = ""
        self.update("")
