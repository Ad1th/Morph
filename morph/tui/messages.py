"""Textual messages that carry engine progress onto the UI thread."""

from __future__ import annotations

from textual.message import Message

from morph.schema.events import TrialEvent


class EngineEvent(Message):
    """One :class:`~morph.schema.events.TrialEvent` from a running experiment."""

    def __init__(self, event: TrialEvent) -> None:
        self.event = event
        super().__init__()


class RunFinished(Message):
    """A worker finished. ``result`` is the engine's return value or an Exception."""

    def __init__(self, result: object, error: BaseException | None = None) -> None:
        self.result = result
        self.error = error
        super().__init__()
