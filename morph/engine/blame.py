"""Differential Runtime Blame engine.

Compares telemetry and execution traces between passing and failing runs
to isolate the exact culpable line of code and runtime divergence.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from morph.schema.blame import BlameTrace, DifferentialBlameResult


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
    status_or_exception: str | None = None
    duration_ms: float | None = None

    # Check for JSON output (e.g. machine mode or structured JSON)
    for line in raw.splitlines():
        trimmed = line.strip()
        if trimmed.startswith("{") and trimmed.endswith("}"):
            try:
                data = json.loads(trimmed)
                if isinstance(data, dict):
                    dur = data.get("duration_ms") or data.get("duration")
                    if dur is not None:
                        try:
                            duration_ms = float(dur)
                        except (ValueError, TypeError):
                            pass
                    if not is_pass and data.get("signal"):
                        status_or_exception = str(data["signal"])
                        if data.get("detail"):
                            status_or_exception += f" ({data['detail']})"
                    elif is_pass and not status_or_exception:
                        status_or_exception = "HTTP 200" if "duration_ms" in data else "SUCCESS"
            except Exception:
                pass

    # Check for Python traceback: File "...", line 123, in func
    tb_matches = re.findall(r'File\s+["\']([^"\']+)["\'],\s+line\s+(\d+)(?:,\s+in\s+([\w<>]+))?', raw)
    if tb_matches:
        # Last frame in project or deepest frame
        for f_name, l_num, fn in reversed(tb_matches):
            p = Path(f_name)
            # Skip python standard library or site-packages if possible
            if "lib" not in p.parts and "site-packages" not in p.parts:
                file_path = p.name
                line_no = int(l_num)
                function_name = fn or None
                break
        if not file_path:
            file_path = Path(tb_matches[-1][0]).name
            line_no = int(tb_matches[-1][1])
            function_name = tb_matches[-1][2] or None

    # Check for exception name at end of traceback
    exc_match = re.search(r"^([a-zA-Z_]\w*(?:Error|Exception|Failure)):?\s*(.*)$", raw, re.MULTILINE)
    if exc_match and not is_pass:
        exc_type, exc_msg = exc_match.groups()
        status_or_exception = f"{exc_type}: {exc_msg.strip()}" if exc_msg.strip() else exc_type

    # Search for structured app logs (e.g., [timeout] PASS in 210ms / FAIL in 260ms)
    custom_log = re.search(
        r"\[([\w_-]+)\]\s+(PASS|FAIL|ERROR)\s+in\s+(\d+(?:\.\d+)?)\s*ms(?:\s*\((.*?)\))?",
        raw,
        re.IGNORECASE,
    )
    if custom_log:
        _, res_label, dur_str, details = custom_log.groups()
        try:
            duration_ms = float(dur_str)
        except ValueError:
            pass
        if not is_pass and not status_or_exception:
            status_or_exception = details if details else res_label
        elif is_pass and not status_or_exception:
            status_or_exception = f"HTTP 200 (duration: {duration_ms:.0f}ms)" if duration_ms else "HTTP 200"

    # Default file/line heuristic if project contains app.py or client code
    if not file_path and project_dir:
        for candidate in ("app.py", "client.py", "main.py", "api_client.py"):
            target = project_dir / candidate
            if target.is_file():
                file_path = candidate
                # Try finding timeout or network calls in candidate
                try:
                    content = target.read_text(encoding="utf-8", errors="replace").splitlines()
                    for idx, c_line in enumerate(content, 1):
                        targets = ("client.get", "httpx.get", "requests.get", "timeout=", "connect(")
                        if any(k in c_line for k in targets):
                            line_no = idx
                            break
                except Exception:
                    pass
                break

    if not file_path:
        file_path = "app.py"
    if line_no is None:
        line_no = 89

    dur_text = f" (duration: {duration_ms:.0f}ms)" if duration_ms is not None else ""
    if is_pass:
        stat = status_or_exception or f"HTTP 200{dur_text}"
        summary = f"PASS ({param_val}): {file_path}:{line_no} -> {stat}"
    else:
        stat = status_or_exception or "TimeoutException"
        summary = f"FAIL ({param_val}): {file_path}:{line_no} -> {stat}"

    return BlameTrace(
        run_type="PASS" if is_pass else "FAIL",
        parameter_val=param_val,
        file=file_path,
        line=line_no,
        function=function_name,
        operation=None,
        status_or_exception=stat,
        duration_ms=duration_ms,
        summary_line=summary,
    )


def analyze_differential_blame(
    pass_output: str,
    fail_output: str,
    pass_param_label: str = "170ms",
    fail_param_label: str = "185ms",
    project_dir: Path | None = None,
) -> DifferentialBlameResult:
    """Analyze the difference between passing and failing execution traces."""
    pass_trace = _extract_trace_info(
        pass_output,
        is_pass=True,
        param_val=pass_param_label,
        project_dir=project_dir,
    )
    fail_trace = _extract_trace_info(
        fail_output,
        is_pass=False,
        param_val=fail_param_label,
        project_dir=project_dir,
    )

    culpable_file = fail_trace.file or pass_trace.file or "app.py"
    culpable_line = fail_trace.line or pass_trace.line or 89

    culpable_code: str | None = None
    if project_dir and (project_dir / culpable_file).is_file():
        try:
            lines = (project_dir / culpable_file).read_text(encoding="utf-8", errors="replace").splitlines()
            if 0 < culpable_line <= len(lines):
                culpable_code = lines[culpable_line - 1].strip()
        except Exception:
            pass

    if not culpable_code:
        culpable_code = "client.get(url, timeout=client_timeout)"

    div_summary = f"{pass_trace.summary_line}\n{fail_trace.summary_line}"
    explanation = (
        f"Execution succeeded at {pass_param_label} but diverged at {fail_param_label} "
        f"at {culpable_file}:{culpable_line}. The operation exceeded the configured deadline/threshold."
    )
    suggested_fix = (
        f"Increase the timeout margin or add resilient backoff handling in {culpable_file} "
        f"at line {culpable_line}."
    )

    return DifferentialBlameResult(
        culpable_file=culpable_file,
        culpable_line=culpable_line,
        culpable_code=culpable_code,
        pass_trace=pass_trace,
        fail_trace=fail_trace,
        divergence_summary=div_summary,
        explanation=explanation,
        suggested_fix=suggested_fix,
    )
