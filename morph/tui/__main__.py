"""``python -m morph.tui`` -> launch the TUI."""

from __future__ import annotations

import sys

from morph.tui import run

if __name__ == "__main__":
    run(demo="--demo" in sys.argv[1:])
