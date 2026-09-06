import os
import shlex
import subprocess
import sys
import time

import pytest

from morph.schema.telemetry import RunResult
from morph.telemetry.collector import run_with_telemetry


def _py(code: str) -> str:
    # OS-native quoting: run_with_telemetry passes Windows commands straight
    # to CreateProcess (its own quoting rules) and shlex-splits POSIX ones,
    # so the join style must match whichever the current OS will use.
    if os.name == "nt":
        return subprocess.list2cmdline([sys.executable, "-c", code])
    return shlex.join([sys.executable, "-c", code])


def test_successful_run_populates_result():
    r = run_with_telemetry(_py("import time; print('hello'); time.sleep(0.15)"))
    assert isinstance(r, RunResult)
    assert r.passed is True
    assert r.exit_code == 0
    assert "hello" in r.stdout
    assert r.stderr == ""
    assert r.duration_ms > 0
    assert r.error_type is None
    assert r.peak_memory_mb is not None and r.peak_memory_mb > 0
    assert r.run_id.startswith("run-")
    assert r.telemetry is not None


def test_nonzero_exit_parses_error():
    r = run_with_telemetry(_py("raise ValueError('boom')"))
    assert r.passed is False
    assert r.exit_code == 1
    assert r.error_type == "ValueError"
    assert r.error_message == "boom"
    assert r.telemetry.extra.get("stack_trace", "").startswith("Traceback")


def test_stdout_and_stderr_are_separate():
    r = run_with_telemetry(
        _py("import sys; sys.stdout.write('OUT'); sys.stderr.write('ERR')")
    )
    assert r.stdout == "OUT"
    assert r.stderr == "ERR"


def test_timeout_terminates_and_flags():
    r = run_with_telemetry(_py("import time; time.sleep(10)"), timeout=0.5)
    assert r.passed is False
    assert r.error_type == "TimeoutExpired"
    assert r.exit_code != 0
    assert r.telemetry.extra.get("timed_out") is True
    assert 400 <= r.duration_ms < 8000


def test_timeout_kills_child_process_tree(tmp_path):
    marker = tmp_path / "leaked.txt"
    # repr() escapes backslashes/quotes so the path is a valid Python literal
    # even nested inside this outer (non-raw) string, safe on Windows too.
    child = (
        "import subprocess, sys, time; "
        "subprocess.Popen([sys.executable, '-c', "
        f"\"import time; time.sleep(3); open({str(marker)!r}, 'w').write('leaked')\"]); "
        "time.sleep(30)"
    )
    r = run_with_telemetry(_py(child), timeout=0.8)
    assert r.error_type == "TimeoutExpired"
    time.sleep(4)  # grandchild would write at +3s if it survived
    assert not marker.exists(), "grandchild process was not killed"


def test_peak_memory_reflects_allocation():
    code = (
        "import time; buf = bytearray(64 * 1024 * 1024); "
        "buf[::4096] = b'\\x01' * len(buf[::4096]); "
        "time.sleep(0.4); print(len(buf))"
    )
    r = run_with_telemetry(_py(code))
    assert r.passed is True
    assert r.peak_memory_mb is not None and r.peak_memory_mb > 30


def test_command_not_found():
    r = run_with_telemetry("this-binary-does-not-exist-morph-xyz --flag")
    assert r.passed is False
    assert r.exit_code == 127
    assert r.error_type == "FileNotFoundError"


def test_empty_command_raises():
    with pytest.raises(ValueError):
        run_with_telemetry("   ")


def test_cwd_is_respected(tmp_path):
    r = run_with_telemetry(
        _py("import os; print(os.path.realpath(os.getcwd()))"), cwd=str(tmp_path)
    )
    assert r.stdout.strip() == os.path.realpath(str(tmp_path))


def test_env_is_passed_verbatim():
    env = {**os.environ, "MORPH_TESTVAR": "xyz"}
    r = run_with_telemetry(
        _py("import os; print(os.environ.get('MORPH_TESTVAR', 'MISSING'))"), env=env
    )
    assert r.stdout.strip() == "xyz"


def test_result_round_trips_through_schema():
    r = run_with_telemetry(_py("print(1)"))
    assert RunResult.model_validate(r.model_dump()) == r
