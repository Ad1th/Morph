"""Best-effort extraction of error type / message / stack trace from process output.

The runner executes arbitrary demo apps (Python, Node, Java, plain binaries). This
module recognises the common shapes their failures take on stderr/stdout so the
experiment engine can classify a failure without the app cooperating.
"""

from __future__ import annotations

import re
from typing import Optional

# Final line of a Python traceback, or a bare "Type: message" string.
# A leading module path (pkg.mod.MyError) is consumed and dropped.
_FINAL_LINE = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*\.)*"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_]*"
    r"(?:Error|Exception|Exit|Interrupt|Warning|Expired|Timeout|Failure|Fault|"
    r"Abort|Aborted|Lost|Refused|Denied|Unavailable|NotFound|Overflow|Underflow)"
    r"|SystemExit|KeyboardInterrupt|StopIteration|StopAsyncIteration|GeneratorExit)"
    r"(?::[ \t]*(?P<msg>.*?))?[ \t]*$"
)

# JVM: `Exception in thread "main" pkg.FooException: msg`  /  `Caused by: pkg.Bar: msg`
_JAVA_EXC = re.compile(
    r'(?:Exception in thread "[^"]*"|Caused by:)\s+'
    r"(?:[\w$]+\.)*(?P<type>[\w$]+(?:Error|Exception))"
    r"(?::[ \t]*(?P<msg>.*?))?[ \t]*$",
    re.MULTILINE,
)

_PY_TRACEBACK_HEADER = "Traceback (most recent call last):"


def _iter_sources(stderr: str, stdout: str):
    for text in (stderr or "", stdout or ""):
        if text.strip():
            yield text


def _match(text: str) -> Optional[re.Match]:
    """Return the match that best identifies the failure in `text`.

    Java header first; otherwise scan lines bottom-up so a chained traceback
    resolves to the most recent exception (the one that actually killed the process).
    """
    jm = _JAVA_EXC.search(text)
    if jm:
        return jm
    for line in reversed([ln.strip() for ln in text.splitlines()]):
        if not line:
            continue
        m = _FINAL_LINE.match(line)
        if m:
            return m
    return None


def extract_error_type(stderr: str, stdout: str = "") -> Optional[str]:
    for text in _iter_sources(stderr, stdout):
        m = _match(text)
        if m:
            return m.group("type")
    return None


def extract_error_message(stderr: str, stdout: str = "") -> Optional[str]:
    for text in _iter_sources(stderr, stdout):
        m = _match(text)
        if m:
            return (m.group("msg") or "").strip() or None
    return None


def extract_stack_trace(stderr: str) -> Optional[str]:
    stderr = stderr or ""
    if _PY_TRACEBACK_HEADER in stderr:
        idx = stderr.index(_PY_TRACEBACK_HEADER)
        return stderr[idx:].rstrip() or None

    java_lines = [
        ln
        for ln in stderr.splitlines()
        if ln.strip().startswith("at ")
        or ln.startswith("Exception in thread")
        or ln.strip().startswith("Caused by:")
        or ln.strip().startswith("... ")
    ]
    return "\n".join(java_lines) if java_lines else None
