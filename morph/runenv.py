"""Turn a cloned/added project into something Morph can actually run.

`prepare()` builds a per-project virtualenv and installs its declared
dependencies (``requirements*.txt`` / ``pyproject.toml`` via ``uv``, or
``package.json`` via ``npm``). When the run command is ``pytest`` it also
installs pytest and the project's test/dev extras. `command_in_env()` rewrites
a leading ``python``/``python3``/``pytest`` so the detected command uses that
venv.

Best-effort: a dependency install that partly fails still returns the venv (the
failure is logged); if there is nothing to install it returns ``None`` and the
command runs against the ambient environment.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

Logger = Callable[[str], None]


class EnvError(RuntimeError):
    """Dependency installation failed hard (could not even create the venv)."""


@dataclass
class EnvResult:
    """Outcome of :func:`prepare`."""

    venv: Path | None
    ok: bool = True  # every dependency step succeeded (or there were none)
    failed: list[str] = field(default_factory=list)  # human-readable step labels

    def __bool__(self) -> bool:  # keep `if prepare(...):` working
        return self.venv is not None


def _log(logger: Logger | None, message: str) -> None:
    if logger is not None:
        logger(message)


def venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


# A slow or lossy network is the usual reason a dependency install fails, and
# it is exactly the class of failure Morph exists to reason about -- so give the
# child plenty of time and retry the whole step a couple of times.
_INSTALL_ENV = {"UV_HTTP_TIMEOUT": "120", "PIP_DEFAULT_TIMEOUT": "120"}
_TRANSIENT = (
    "timed out", "timeout", "connection", "temporary failure", "network",
    "reset by peer", "could not resolve", "ssl", "handshake", "503", "502", "429",
    "failed to fetch", "read error", "eof occurred",
)


def _run(
    cmd: list[str],
    cwd: Path,
    logger: Logger | None,
    timeout: float = 900.0,
    retries: int = 0,
) -> bool:
    """Run one install step. Returns True on success; logs and returns False on
    a non-fatal failure so the rest of prepare() can continue. A failure whose
    output looks like a network hiccup is retried up to ``retries`` times."""
    import os
    import time

    env = {**os.environ, **_INSTALL_ENV}
    last = ""
    for attempt in range(retries + 1):
        if attempt:
            _log(logger, f"  retry {attempt}/{retries} (looked like a network error)…")
            time.sleep(2.0 * attempt)
        _log(logger, "$ " + " ".join(cmd))
        try:
            proc = subprocess.run(
                cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env
            )
        except (OSError, subprocess.SubprocessError) as exc:
            last = str(exc)
            _log(logger, f"  ! {last}")
            continue
        if proc.stdout.strip():
            _log(logger, proc.stdout.strip()[-1500:])
        if proc.returncode == 0:
            return True
        last = (proc.stderr or proc.stdout or "failed").strip()
        _log(logger, "  ! " + last[-1500:])
        if not any(word in last.lower() for word in _TRANSIENT):
            break  # deterministic failure -- retrying won't help
    return False


def _pyproject_has_metadata(project_dir: Path) -> bool:
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return False
    text = pyproject.read_text(encoding="utf-8", errors="replace")
    return "[project]" in text or "[build-system]" in text or "[tool.poetry]" in text


def _test_extras(project_dir: Path) -> list[str]:
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return []
    optional = (data.get("project") or {}).get("optional-dependencies", {})
    return [name for name in ("test", "tests", "dev", "testing") if name in optional]


def _extra_requirement_files(project_dir: Path) -> list[Path]:
    found: list[Path] = []
    for pattern in ("requirements-dev.txt", "requirements-test.txt", "requirements_dev.txt",
                    "dev-requirements.txt", "test-requirements.txt"):
        p = project_dir / pattern
        if p.is_file():
            found.append(p)
    reqs_dir = project_dir / "requirements"
    if reqs_dir.is_dir():
        found.extend(sorted(reqs_dir.glob("*.txt")))
    return found


def prepare(
    project_dir: Path,
    venv_dir: Path,
    *,
    command: str | None = None,
    logger: Logger | None = None,
) -> EnvResult:
    """Create ``venv_dir`` and install ``project_dir``'s deps into it.

    Every install step is retried through transient (network) failures, and if
    ``uv`` keeps failing it is retried once with the venv's own ``pip``. A step
    that still fails is recorded in the result's ``failed`` list rather than
    aborting -- a partly-installed project can still be useful.
    """
    project_dir = Path(project_dir)
    venv_dir = Path(venv_dir)

    requirements = project_dir / "requirements.txt"
    pyproject = project_dir / "pyproject.toml"
    setup_py = project_dir / "setup.py"
    package_json = project_dir / "package.json"
    wants_pytest = bool(command) and (
        " pytest" in f" {command}" or command.strip().startswith("pytest")
    )

    python_project = requirements.is_file() or pyproject.is_file() or setup_py.is_file()
    if python_project or wants_pytest:
        uv = shutil.which("uv")
        if uv:
            if not _run([uv, "venv", str(venv_dir)], project_dir, logger):
                raise EnvError("could not create the virtualenv")
            py = str(venv_python(venv_dir))
            uv_pip = [uv, "pip", "install", "--python", py]
        else:
            if not _run([sys.executable, "-m", "venv", str(venv_dir)], project_dir, logger):
                raise EnvError("could not create the virtualenv")
            uv_pip = None
        venv_pip = [str(venv_python(venv_dir)), "-m", "pip", "install"]

        failed: list[str] = []

        def install(label: str, args: list[str]) -> None:
            primary = ([*uv_pip, *args]) if uv_pip else ([*venv_pip, *args])
            if _run(primary, project_dir, logger, retries=2):
                return
            if uv_pip is not None:
                _log(logger, "  falling back to the venv's own pip…")
                if _run([*venv_pip, *args], project_dir, logger, retries=1):
                    return
            failed.append(label)

        if requirements.is_file():
            install("requirements.txt", ["-r", str(requirements)])
        for extra_req in _extra_requirement_files(project_dir):
            install(extra_req.name, ["-r", str(extra_req)])
        if _pyproject_has_metadata(project_dir) or setup_py.is_file():
            extras = _test_extras(project_dir) if wants_pytest else []
            spec = f".[{','.join(extras)}]" if extras else "."
            install(f"pip install -e {spec}", ["-e", spec])
        if wants_pytest:
            install("pytest", ["pytest"])

        if failed:
            _log(logger, f"  [!] some dependencies did not install: {', '.join(failed)}")
        return EnvResult(venv_dir, ok=not failed, failed=failed)

    if package_json.is_file():
        npm = shutil.which("npm")
        if npm:
            lock = project_dir / "package-lock.json"
            ok = _run([npm, "ci" if lock.is_file() else "install"], project_dir, logger, retries=2)
            return EnvResult(None, ok=ok, failed=[] if ok else ["npm install"])
        return EnvResult(None)

    _log(logger, "no requirements.txt / pyproject.toml / package.json -- nothing to install")
    return EnvResult(None)


def _venv_bin(venv: Path) -> Path:
    return venv / ("Scripts" if sys.platform == "win32" else "bin")


def command_in_env(command: str, venv: Path | str | None) -> str:
    """Point a leading ``python`` / ``python3`` / ``pytest`` token -- or a
    console script the install created -- at the venv."""
    if not venv or not command:
        return command
    venv = Path(venv)
    py = venv_python(venv)
    if not py.exists():
        return command
    head, sep, tail = command.partition(" ")
    if head in ("python", "python3") or head.startswith("python3."):
        return f'"{py}"{sep}{tail}'
    if head == "pytest":
        return f'"{py}" -m pytest{sep}{tail}'

    bindir = _venv_bin(venv)
    for candidate in (bindir / head, bindir / f"{head}.exe"):
        if candidate.exists():
            return f'"{candidate}"{sep}{tail}'
    return command
