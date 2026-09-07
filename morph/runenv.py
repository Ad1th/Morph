"""Turn a cloned/added project into something Morph can actually run.

`prepare()` builds a per-project virtualenv and installs its declared
dependencies (``requirements.txt`` / ``pyproject.toml`` via ``uv``, or
``package.json`` via ``npm``). `command_in_env()` rewrites a leading
``python``/``python3`` so the detected command uses that venv.

Best-effort: if there is nothing to install, or the toolchain is missing, it
returns ``None`` and the command runs against the ambient environment.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

Logger = Callable[[str], None]


class EnvError(RuntimeError):
    """Dependency installation failed."""


def _log(logger: Logger | None, message: str) -> None:
    if logger is not None:
        logger(message)


def venv_python(venv: Path) -> Path:
    if sys.platform == "win32":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


def _run(cmd: list[str], cwd: Path, logger: Logger | None, timeout: float = 600.0) -> None:
    _log(logger, "$ " + " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True, timeout=timeout)
    if proc.stdout.strip():
        _log(logger, proc.stdout.strip()[-2000:])
    if proc.returncode != 0:
        raise EnvError((proc.stderr or proc.stdout or "install failed").strip()[-2000:])


def prepare(project_dir: Path, venv_dir: Path, *, logger: Logger | None = None) -> Path | None:
    """Create ``venv_dir`` and install ``project_dir``'s deps into it.

    Returns the venv path (Python projects) or ``None`` (nothing to install, a
    Node project handled in place, or no usable toolchain).
    """
    project_dir = Path(project_dir)
    venv_dir = Path(venv_dir)

    requirements = project_dir / "requirements.txt"
    pyproject = project_dir / "pyproject.toml"
    setup_py = project_dir / "setup.py"
    package_json = project_dir / "package.json"

    if requirements.is_file() or pyproject.is_file() or setup_py.is_file():
        uv = shutil.which("uv")
        if uv:
            _run([uv, "venv", str(venv_dir)], project_dir, logger)
            py = str(venv_python(venv_dir))
            if requirements.is_file():
                _run([uv, "pip", "install", "--python", py, "-r", str(requirements)],
                     project_dir, logger)
            if pyproject.is_file() or setup_py.is_file():
                _run([uv, "pip", "install", "--python", py, "-e", "."], project_dir, logger)
            return venv_dir

        _run([sys.executable, "-m", "venv", str(venv_dir)], project_dir, logger)
        pip = str(venv_python(venv_dir))
        if requirements.is_file():
            _run([pip, "-m", "pip", "install", "-r", str(requirements)], project_dir, logger)
        if pyproject.is_file() or setup_py.is_file():
            _run([pip, "-m", "pip", "install", "-e", "."], project_dir, logger)
        return venv_dir

    if package_json.is_file():
        npm = shutil.which("npm")
        if npm:
            lock = project_dir / "package-lock.json"
            _run([npm, "ci" if lock.is_file() else "install"], project_dir, logger, timeout=900.0)
        return None

    _log(logger, "no requirements.txt / pyproject.toml / package.json -- nothing to install")
    return None


def command_in_env(command: str, venv: Path | str | None) -> str:
    """Rewrite a leading ``python`` / ``python3`` token to the venv's python."""
    if not venv or not command:
        return command
    py = venv_python(Path(venv))
    if not py.exists():
        return command
    head, sep, tail = command.partition(" ")
    if head in ("python", "python3") or head.startswith("python3."):
        return f'"{py}"{sep}{tail}'
    return command
