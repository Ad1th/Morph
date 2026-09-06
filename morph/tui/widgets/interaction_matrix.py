"""InteractionMatrix -- the 2x2 that shows a failure needs *both* conditions.

Populated straight from the isolation run's four batches (baseline = neither,
latency_only = A, loss_only = B, full_target = both). Three cells stay green,
one goes red: the "aha".
"""

from __future__ import annotations

from rich.align import Align
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.widgets import Static


def _cell(rate: float, *, strong: bool = False) -> Text:
    if rate >= 0.6:
        style = "bold white on red3" if strong else "white on red3"
    elif rate >= 0.25:
        style = "black on yellow"
    else:
        style = "white on green"
    return Text(f"  {rate:>4.0%} fail  ", style=style)


class InteractionMatrix(Static):
    def show(
        self,
        label_a: str,
        label_b: str,
        neither: float,
        a_only: float,
        b_only: float,
        both: float,
    ) -> None:
        grid = Table(show_header=True, header_style="bold", box=None, padding=(0, 1))
        grid.add_column("", justify="right", style="dim")
        grid.add_column(f"{label_b}: off", justify="center")
        grid.add_column(f"{label_b}: on", justify="center")
        grid.add_row(f"{label_a}: off", _cell(neither), _cell(b_only))
        grid.add_row(f"{label_a}: on", _cell(a_only), _cell(both, strong=True))

        confirmed = a_only < 0.25 and b_only < 0.25 and both >= 0.6
        caption = (
            Text("→ failure requires the combination; neither condition does it alone",
                 style="bold red3")
            if confirmed
            else Text("→ no combination-only effect", style="dim")
        )
        self.update(
            Panel(
                Align.center(grid),
                title="interaction  2x2",
                subtitle=str(caption),
                border_style="red3" if confirmed else "grey50",
                padding=(1, 2),
            )
        )
