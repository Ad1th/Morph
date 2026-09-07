"""EvidencePane -- the latest failing trial, in full.

The log shows one line per failure; this pane keeps the *whole* tail of the
most recent one (condition, trial number, error type, stderr / stdout) so the
reason is readable without scrolling the log.
"""

from __future__ import annotations

from rich.text import Text
from textual.widgets import Static

from morph.schema.events import TrialEvent
from morph.tui.theme import palette

_MAX_LINES = 14


class EvidencePane(Static):
    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._event: TrialEvent | None = None
        self._empty = "no failing trial yet"

    def on_mount(self) -> None:
        self.border_title = "EVIDENCE"
        self._paint()

    def show_trial(self, ev: TrialEvent) -> None:
        self._event = ev
        self._paint()

    def clear(self, empty: str | None = None) -> None:
        self._event = None
        if empty:
            self._empty = empty
        self._paint()

    @property
    def has_evidence(self) -> bool:
        return self._event is not None

    def _paint(self) -> None:
        p = palette(self)
        ev = self._event
        if ev is None:
            self.update(Text(self._empty, style=p.muted))
            return
        out = Text()
        out.append(ev.condition or "?", style=f"bold {p.fail}")
        if ev.trial_index is not None:
            out.append(f"  trial {ev.trial_index + 1}", style=p.muted)
            if ev.total:
                out.append(f"/{ev.total}", style=p.muted)
        if ev.duration_ms:
            out.append(f"  {ev.duration_ms:,.0f} ms", style=p.muted)
        out.append("\n")
        out.append(ev.error_type or "failure", style=f"bold {p.text}")
        tail = (ev.stderr_tail or "").strip() or (ev.stdout_tail or "").strip()
        if tail:
            src = "stderr" if (ev.stderr_tail or "").strip() else "stdout"
            out.append(f"  ({src} tail)", style=p.muted)
            lines = tail.splitlines()
            if len(lines) > _MAX_LINES:
                out.append(f"\n… {len(lines) - _MAX_LINES} earlier lines", style=p.muted)
                lines = lines[-_MAX_LINES:]
            for line in lines:
                out.append("\n")
                out.append(line, style=p.text)
        self.update(out)
