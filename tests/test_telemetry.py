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


def test_non_utf8_output_does_not_crash_the_collector():
    """A target printing latin-1 under LC_ALL=de_DE used to raise UnicodeDecodeError."""
    r = run_with_telemetry(_py("import sys; sys.stdout.buffer.write(b'caf\\xe9\\n')"))
    assert r.passed is True
    assert r.stdout.startswith("caf")  # the bad byte is replaced, the rest survives


def test_exit_code_2_is_an_invalid_trial_not_a_failure():
    """apps/README.md: exit 2 = the app could not even attempt the test."""
    r = run_with_telemetry(_py("import sys; sys.exit(2)"))
    assert r.passed is False
    assert r.invalid is True
    assert "exit 2" in (r.invalid_reason or "")
    assert RunResult.model_validate_json(r.model_dump_json()) == r


def test_command_not_found_is_invalid():
    r = run_with_telemetry("this-binary-does-not-exist-morph-xyz --flag")
    assert r.invalid is True and r.exit_code == 127


def test_ordinary_failure_is_not_invalid():
    r = run_with_telemetry(_py("raise ValueError('boom')"))
    assert r.invalid is False and r.invalid_reason is None


@pytest.mark.skipif(os.name == "nt", reason="rlimits are POSIX-only")
def test_oversized_rlimit_from_a_foreign_profile_is_clamped_not_fatal():
    """A Linux capture (NOFILE 1,048,576) replayed on macOS used to raise
    SubprocessError out of Popen and escape the engine."""
    import resource

    hard = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
    if hard == resource.RLIM_INFINITY:
        pytest.skip("no hard NOFILE limit on this host")
    r = run_with_telemetry(
        _py("import resource; print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])"),
        fd_limit=hard * 4,
    )
    assert r.passed is True, r.stderr
    assert int(r.stdout.strip()) == hard
    assert any("clamped" in n for n in r.telemetry.extra.get("rlimit_notes", []))


@pytest.mark.skipif(os.name == "nt", reason="preexec_fn is POSIX-only")
def test_preexec_failure_becomes_an_invalid_result(monkeypatch):
    import morph.telemetry.collector as collector

    def explode(*_a, **_k):
        raise ValueError("refused by the kernel")

    monkeypatch.setattr(collector, "_limit_resources", explode)
    r = run_with_telemetry(_py("print('never')"), fd_limit=256)
    assert r.passed is False and r.invalid is True
    assert r.exit_code == 126


def test_output_is_bounded_and_the_tail_is_kept():
    from morph.telemetry.collector import MAX_CAPTURE_BYTES

    code = (
        f"import sys; sys.stdout.write('x' * ({MAX_CAPTURE_BYTES} + 100000)); "
        "sys.stdout.write('THE-END')"
    )
    r = run_with_telemetry(_py(code))
    assert r.passed is True
    assert len(r.stdout) <= MAX_CAPTURE_BYTES + 200
    assert r.stdout.endswith("THE-END")
    assert r.stdout.startswith("[... morph: output truncated")


def test_result_carries_provenance():
    r = run_with_telemetry(_py("print(1)"))
    assert r.command.startswith(sys.executable) or "python" in r.command
    assert r.morph_version
    assert len(r.host_fingerprint) == 16
    assert run_with_telemetry(_py("print(1)")).host_fingerprint == r.host_fingerprint


def test_seed_is_read_from_the_child_environment():
    env = {**os.environ, "MORPH_SEED": "777"}
    r = run_with_telemetry(_py("print(1)"), env=env)
    assert r.seed == 777


@pytest.mark.skipif(os.name == "nt", reason="process groups are POSIX-only here")
def test_no_preexec_fn_without_limits(monkeypatch):
    """preexec_fn forces fork() and is unsafe with threads: only install it on request."""
    import subprocess as sp

    seen = {}
    real = sp.Popen

    class Spy(real):
        def __init__(self, *a, **k):
            seen.update(k)
            super().__init__(*a, **k)

    monkeypatch.setattr(sp, "Popen", Spy)
    run_with_telemetry(_py("print(1)"))
    assert "preexec_fn" not in seen
    assert seen.get("start_new_session") is True
