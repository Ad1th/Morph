"""VerdictCard -- the plain-language diagnosis at the end of an experiment."""

from __future__ import annotations

from rich.panel import Panel
from rich.text import Text
from textual.widgets import Static

# classification -> (headline, one-line meaning, border style)
_VERDICTS = {
    "environment_caused": (
        "ENVIRONMENT-CAUSED",
        "Baseline is clean. This condition makes the failure appear.",
        "red3",
    ),
    "environment_exposed": (
        "ENVIRONMENT-EXPOSED",
        "The bug is in the app, but this condition makes it fire far more often.",
        "dark_orange",
    ),
    "application_internal": (
        "APPLICATION BUG",
        "Fails on its own, regardless of environment. Not an environment problem.",
        "yellow",
    ),
    "no_effect": (
        "NO EFFECT",
        "No condition produced a statistically significant increase in failures.",
        "grey50",
    ),
}


class VerdictCard(Static):
    def show(
        self,
        classification: str,
        strongest_condition: str = "",
        p_value: float | None = None,
        summary: str = "",
    ) -> None:
        headline, meaning, style = _VERDICTS.get(
            classification, (classification.upper(), "", "grey50")
        )
        body = Text()
        body.append(headline + "\n", style=f"bold {style}")
        body.append(meaning + "\n", style="italic")
        if strongest_condition and strongest_condition != "none":
            body.append(f"\nstrongest condition:  {strongest_condition}")
        if p_value is not None:
            body.append(f"\nFisher's exact p   :  {p_value:.4g}")
        if summary:
            body.append(f"\n\n{summary}", style="dim")
        self.update(Panel(body, title="verdict", border_style=style, padding=(1, 2)))
