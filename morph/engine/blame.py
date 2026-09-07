"""Differential Runtime Blame engine.

Compares the output of a passing and a failing run to say *where* the failing
run diverged: the deepest project frame of a Python traceback, the final
exception, a structured ``{"signal": ...}`` JSON line, or an application log
of the form ``[tag] FAIL in 255ms (detail)``.

Every field is ``None`` when the output does not contain it. Nothing is
guessed: no default file, line, code snippet, diagnosis or fix. A UI should
render "no trace found" rather than a fabricated culprit.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from morph.schema.blame import BlameTrace, DifferentialBlameResult

_TRACEBACK_FRAME = re.compile(r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([\w<>]+))?')
_EXCEPTION_LINE = re.compile(
    r"^([a-zA-Z_][\w.]*(?:Error|Exception|Failure|Exit|Interrupt))\b:?\s*(.*)$", re.MULTILINE
)
_APP_LOG = re.compile(
    r"\[([\w_-]+)\]\s+(PASS|FAIL|ERROR)\s+in\s+(\d+(?:\.\d+)?)\s*ms(?:\s*\((.*?)\))?",
    re.IGNORECASE,
)
_LIBRARY_PARTS = {"lib", "site-packages", "dist-packages", "lib64"}


def _is_library_frame(path: str) -> bool:
    # Split on both separators: a Windows traceback may be parsed on POSIX.
    parts = {part.lower() for part in re.split(r"[\\/]+", path) if part}
    return bool(parts & _LIBRARY_PARTS)


def _parse_json_lines(raw: str, is_pass: bool) -> tuple[float | None, str | None]:
    duration_ms: float | None = None
    status: str | None = None
    for line in raw.splitlines():
        trimmed = line.strip()
        if not (trimmed.startswith("{") and trimmed.endswith("}")):
            continue
        try:
            data = json.loads(trimmed)
        except ValueError:
            continue
        if not isinstance(data, dict):
            continue
        dur = data.get("duration_ms", data.get("duration"))
        if dur is not None:
            try:
                duration_ms = float(dur)
            except (ValueError, TypeError):
                pass
        if not is_pass and data.get("signal"):
            status = str(data["signal"])
            if data.get("detail"):
                status += f" ({data['detail']})"
        elif is_pass and data.get("status"):
            status = str(data["status"])
    return duration_ms, status


def _extract_trace_info(
    output: str,
    is_pass: bool,
    param_val: str,
    project_dir: Path | None = None,
) -> BlameTrace:
    raw = (output or "").strip()
    file_path: str | None = None
    line_no: int | None = None
    function_name: str | None = None

    duration_ms, status_or_exception = _parse_json_lines(raw, is_pass)

    # Python traceback: prefer the deepest frame that is not library code.
    frames = _TRACEBACK_FRAME.findall(raw)
    if frames:
        chosen = next((f for f in reversed(frames) if not _is_library_frame(f[0])), frames[-1])
        file_path, line_no, function_name = chosen[0], int(chosen[1]), chosen[2] or None

    # The exception that actually terminated the run is the LAST one printed
    # (chained tracebacks print the cause first).
    if not is_pass:
        exc_matches = _EXCEPTION_LINE.findall(raw)
        if exc_matches:
            exc_type, exc_msg = exc_matches[-1]
            exc_msg = exc_msg.strip()
            status_or_exception = f"{exc_type}: {exc_msg}" if exc_msg else exc_type

    # Structured app log: [timeout] PASS in 210ms / FAIL in 260ms (detail)
    app_log = _APP_LOG.search(raw)
    if app_log:
        _tag, res_label, dur_str, details = app_log.groups()
        try:
            duration_ms = float(dur_str)
        except ValueError:
            pass
        if status_or_exception is None:
            status_or_exception = details or res_label.upper()

    where = f"{file_path}:{line_no}" if file_path and line_no is not None else "no trace"
    stat = status_or_exception or "no status found"
    summary = f"{'PASS' if is_pass else 'FAIL'} ({param_val}): {where} -> {stat}"

    return BlameTrace(
        run_type="PASS" if is_pass else "FAIL",
        parameter_val=param_val,
        file=file_path,
        line=line_no,
        function=function_name,
        operation=None,
        status_or_exception=status_or_exception,
        duration_ms=duration_ms,
        summary_line=summary,
    )


def _read_line(file_path: str, line_no: int, project_dir: Path | None) -> str | None:
    """The source line at ``file_path:line_no`` if the file can be found, else None."""
    candidates = [Path(file_path)]
    if project_dir is not None:
        candidates.append(project_dir / file_path)
        candidates.append(project_dir / Path(file_path).name)
    for candidate in candidates:
        try:
            if not candidate.is_file():
                continue
            lines = candidate.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        if 0 < line_no <= len(lines):
            return lines[line_no - 1].strip()
    return None


def analyze_differential_blame(
    pass_output: str,
    fail_output: str,
    pass_param_label: str = "pass",
    fail_param_label: str = "fail",
    project_dir: Path | None = None,
) -> DifferentialBlameResult:
    """Analyze the difference between passing and failing execution traces.

    The culprit location comes only from the *failing* run's trace; when it
    has none, ``culpable_file`` / ``culpable_line`` / ``culpable_code`` are
    ``None`` and the explanation says so. ``suggested_fix`` is always ``None``:
    this engine does not know the cause well enough to prescribe one.
    """
    pass_trace = _extract_trace_info(pass_output, True, pass_param_label, project_dir)
    fail_trace = _extract_trace_info(fail_output, False, fail_param_label, project_dir)

    culpable_file = fail_trace.file
    culpable_line = fail_trace.line
    culpable_code = (
        _read_line(culpable_file, culpable_line, project_dir)
        if culpable_file and culpable_line is not None
        else None
    )
    if culpable_file:
        culpable_file = re.split(r"[\\/]+", culpable_file)[-1]

    div_summary = f"{pass_trace.summary_line}\n{fail_trace.summary_line}"
    status = fail_trace.status_or_exception
    if culpable_file and culpable_line is not None:
        explanation = (
            f"Execution succeeded at {pass_param_label} but failed at {fail_param_label}; "
            f"the failing run's trace ends in {culpable_file}:{culpable_line}"
            f"{f' ({status})' if status else ''}."
        )
    elif status:
        explanation = (
            f"Execution succeeded at {pass_param_label} but failed at {fail_param_label} "
            f"with '{status}'. The failing output contains no stack trace, so no source "
            "line can be blamed."
        )
    else:
        explanation = (
            f"Execution succeeded at {pass_param_label} but failed at {fail_param_label}. "
            "The failing output contains no stack trace or recognisable status; nothing to blame."
        )

    return DifferentialBlameResult(
        culpable_file=culpable_file,
        culpable_line=culpable_line,
        culpable_code=culpable_code,
        pass_trace=pass_trace,
        fail_trace=fail_trace,
        divergence_summary=div_summary,
        explanation=explanation,
        suggested_fix=None,
    )
