import os
import shlex
import subprocess
import sys

from morph.runtime.runner import execute_command
from morph.schema.telemetry import RunResult


def _py(code: str) -> str:
    # OS-native quoting: run_with_telemetry passes Windows commands straight
    # to CreateProcess (its own quoting rules) and shlex-splits POSIX ones,
    # so the join style must match whichever the current OS will use.
    if os.name == "nt":
        return subprocess.list2cmdline([sys.executable, "-c", code])
    return shlex.join([sys.executable, "-c", code])


def test_returns_runresult_and_passes():
    r = execute_command(_py("print('hi')"))
    assert isinstance(r, RunResult)
    assert r.passed is True
    assert r.exit_code == 0
    assert "hi" in r.stdout


def test_merges_with_os_environ(monkeypatch):
    monkeypatch.setenv("MORPH_BASE", "base-value")
    code = (
        "import os; print(os.environ.get('MORPH_BASE'), "
        "os.environ.get('MORPH_OVER'), bool(os.environ.get('PATH')))"
    )
    r = execute_command(_py(code), env_overrides={"MORPH_OVER": "over-value"})
    assert r.stdout.strip() == "base-value over-value True"


def test_override_shadows_existing(monkeypatch):
    monkeypatch.setenv("LC_ALL", "en_US.UTF-8")
    r = execute_command(
        _py("import os; print(os.environ['LC_ALL'])"),
        env_overrides={"LC_ALL": "de_DE.UTF-8"},
    )
    assert r.stdout.strip() == "de_DE.UTF-8"


def test_non_string_values_are_coerced():
    r = execute_command(
        _py("import os; print(os.environ['MORPH_PROXY_PORT'])"),
        env_overrides={"MORPH_PROXY_PORT": 8080},
    )
    assert r.stdout.strip() == "8080"


def test_none_value_unsets_key(monkeypatch):
    monkeypatch.setenv("MORPH_REMOVE_ME", "present")
    r = execute_command(
        _py("import os; print(os.environ.get('MORPH_REMOVE_ME', 'GONE'))"),
        env_overrides={"MORPH_REMOVE_ME": None},
    )
    assert r.stdout.strip() == "GONE"


def test_no_overrides_still_inherits_environ():
    r = execute_command(_py("import os; print(bool(os.environ.get('PATH')))"))
    assert r.stdout.strip() == "True"


def test_timeout_propagates():
    r = execute_command(_py("import time; time.sleep(10)"), timeout=0.5)
    assert r.passed is False
    assert r.error_type == "TimeoutExpired"


def test_error_parsing_propagates():
    r = execute_command(_py("raise RuntimeError('nope')"))
    assert r.passed is False
    assert r.error_type == "RuntimeError"
    assert r.error_message == "nope"


def test_cwd_propagates(tmp_path):
    r = execute_command(
        _py("import os; print(os.path.realpath(os.getcwd()))"), cwd=str(tmp_path)
    )
    assert r.stdout.strip() == os.path.realpath(str(tmp_path))


def test_fd_limit_is_posix_only():
    if os.name != "posix":
        # No pywin32 dependency: must be silently ignored, never crash the run.
        r = execute_command(_py("print('ok')"), max_processes=64, fd_limit=256)
        assert r.passed is True
        return

    r = execute_command(
        _py("import resource; print(resource.getrlimit(resource.RLIMIT_NOFILE)[0])"),
        fd_limit=256,
    )
    assert r.passed is True
    assert r.stdout.strip() == "256"
