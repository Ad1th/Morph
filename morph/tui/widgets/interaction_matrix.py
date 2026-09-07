"""InteractionMatrix -- the 2x2 that shows a failure needs *both* conditions.

Populated straight from the isolation run's four batches (baseline = neither,
latency_only = A, loss_only = B, full_target = both). Three cells stay green,
one goes rose: the "aha".
"""

from __future__ import annotations

from rich.console import Group
from rich.table import Table
from rich.text import Text
from textual.widgets import Static

from morph.tui.theme import palette


class InteractionMatrix(Static):
    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self.confirmed: bool | None = None

    def on_mount(self) -> None:
        self.border_title = "INTERACTION 2x2"

    def _cell(self, rate: float, *, strong: bool = False) -> Text:
        p = palette(self)
        if rate >= 0.6:
            style = f"bold {p.ink_on_fail} on {p.fail}" if strong else f"{p.ink_on_fail} on {p.fail}"
        elif rate >= 0.25:
            style = f"{p.ink_on_evidence} on {p.warn}"
        else:
            style = f"{p.ink_on_pass} on {p.pass_}"
        return Text(f" {rate:>4.0%} fail ", style=style)

    def show(
        self,
        label_a: str,
        label_b: str,
        neither: float,
        a_only: float,
        b_only: float,
        both: float,
        *,
        interaction_probability: float | None = None,
    ) -> None:
        p = palette(self)
        grid = Table(show_header=True, header_style=f"bold {p.muted}", box=None, padding=(0, 1))
        grid.add_column("", justify="right", style=p.muted)
        grid.add_column(f"{label_b} off", justify="center")
        grid.add_column(f"{label_b} on", justify="center")
        grid.add_row(f"{label_a} off", self._cell(neither), self._cell(b_only))
        grid.add_row(f"{label_a} on", self._cell(a_only), self._cell(both, strong=True))

        confirmed = a_only < 0.25 and b_only < 0.25 and both >= 0.6
        self.confirmed = confirmed
        if confirmed:
            caption = Text("→ failure requires the combination; neither alone does it",
                           style=f"bold {p.fail}")
        else:
            caption = Text("→ no combination-only effect", style=p.muted)
        if interaction_probability is not None:
            caption.append(f"   P(interaction) = {interaction_probability:.2f}", style=p.evidence)
        self.styles.border = ("round", p.fail if confirmed else p.muted)
        self.update(Group(grid, caption))
