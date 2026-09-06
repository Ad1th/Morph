"""Morph TUI -- a full-screen terminal console for capturing environments,
running causal experiments, and watching them resolve live.

Entry point: ``morph tui`` (see ``morph.cli.main``) or ``python -m morph.tui``.
"""

from __future__ import annotations


def run(demo: bool = False) -> None:
    """Launch the Morph TUI. ``demo=True`` replays a recorded experiment so the
    live views work with no root, no network, and no target app."""
    from morph.tui.app import MorphApp

    MorphApp(demo=demo).run()
