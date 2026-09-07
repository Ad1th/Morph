"""Exceptions the experiment engine raises for problems that are not verdicts."""

from __future__ import annotations


class InvalidTrialError(RuntimeError):
    """A trial could not be run at all (setup error: command not launchable,
    exit code 2 / 126 / 127, ...), even after retries.

    Callers (CLI / API / TUI) should report a setup problem rather than a
    verdict: an un-launchable command is neither a pass nor a failure.
    """

    def __init__(self, condition: str, reason: str | None, attempts: int = 3) -> None:
        self.condition = condition
        self.reason = reason
        self.attempts = attempts
        detail = f": {reason}" if reason else ""
        super().__init__(
            f"condition '{condition}': trial was invalid on {attempts} consecutive attempts{detail}"
        )
