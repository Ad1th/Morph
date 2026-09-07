"""Add a project to Morph and get it ready to run.

`connect()` is the one call the CLI, TUI, and API share: point it at a local
path or a GitHub repo, and it clones (if needed), detects the run command,
optionally installs dependencies into a per-project venv, records the result in
:mod:`morph.projects`, and returns the :class:`~morph.projects.Project`.
"""

from __future__ import annotations

import platform
import shutil
from collections.abc import Callable
from pathlib import Path

import morph
from morph import github, projects, runenv
from morph.projects import Project

REPO_ROOT = Path(morph.__file__).resolve().parent.parent
CHECKOUTS_DIR = Path.home() / ".morph" / "checkouts"
VENVS_DIR = Path.home() / ".morph" / "venvs"

SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"})
ENTRYPOINT_NAMES = (
    "__main__.py", "main.py", "app.py", "run.py", "manage.py", "index.js", "server.js",
)
PYTHON = "py -3" if platform.system() == "Windows" else "python3"

Logger = Callable[[str], None]


def count_files(project_dir: Path) -> int:
    total = 0
    for path in Path(project_dir).rglob("*"):
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(project_dir).parts):
            total += 1
    return total


def detect_command(project_dir: Path) -> tuple[str | None, str | None]:
    """Return ``(suggested_command, suggested_cwd)`` -- a detection, not a guess.

    Nothing recognised -> ``(None, None)`` so the caller asks for the command
    rather than running something known to fail.
    """
    project_dir = Path(project_dir)

    if (project_dir / "__main__.py").is_file():
        try:
            parts = project_dir.relative_to(REPO_ROOT).parts
            candidate = (f"{PYTHON} -m {'.'.join(parts)}", str(REPO_ROOT))
        except ValueError:
            parts = (project_dir.name,)
            candidate = (f"{PYTHON} -m {project_dir.name}", str(project_dir.parent))
        return candidate if all(p.isidentifier() for p in parts) else (None, None)

    cwd = str(project_dir)
    package_json = project_dir / "package.json"
    if package_json.is_file():
        try:
            import json

            scripts = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            scripts = {}
        if "test" in scripts:
            return "npm test", cwd
        if "start" in scripts:
            return "npm start", cwd
    if (project_dir / "manage.py").is_file():
        return f"{PYTHON} manage.py test", cwd
    if (project_dir / "pytest.ini").is_file() or (project_dir / "tests").is_dir():
        return f"{PYTHON} -m pytest -q", cwd

    top_level_py = [p for p in project_dir.glob("*.py") if p.is_file()]
    if len(top_level_py) == 1:
        return f"{PYTHON} {top_level_py[0].name}", cwd
    for name in ("main.py", "app.py", "run.py"):
        if (project_dir / name).is_file():
            return f"{PYTHON} {name}", cwd

    return None, None


def _looks_like_repo(source: str) -> bool:
    s = source.strip()
    if Path(s).expanduser().exists():
        return False
    return s.startswith(("http://", "https://", "git@")) or (
        "/" in s and " " not in s and not s.startswith((".", "/", "~"))
    )


def connect(
    source: str,
    *,
    token: str | None = None,
    branch: str | None = None,
    install: bool = False,
    name: str | None = None,
    logger: Logger | None = None,
    base: Path | str | None = None,
) -> Project:
    """Add ``source`` (a local path or a GitHub repo) as a runnable project."""
    if _looks_like_repo(source):
        owner, repo_name = github.normalize_repo(source)
        CHECKOUTS_DIR.mkdir(parents=True, exist_ok=True)
        dest = CHECKOUTS_DIR / f"{owner}-{repo_name}"
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        path, commit = github.clone(source, dest, token=token, branch=branch)
        src, repo, ident = "github", f"{owner}/{repo_name}", repo_name
    else:
        path = Path(source).expanduser().resolve()
        if not path.is_dir():
            raise FileNotFoundError(f"{source!r} is not a directory")
        src, repo, commit, ident = "local", None, None, path.name

    command, cwd = detect_command(path)

    venv: str | None = None
    if install:
        if logger:
            logger(f"preparing environment for {ident}…")
        venv_path = runenv.prepare(path, VENVS_DIR / f"{ident}", logger=logger)
        if venv_path is not None:
            venv = str(venv_path)
            command = runenv.command_in_env(command, venv) if command else command

    project = Project(
        name=name or ident,
        source=src,
        path=str(path),
        command=command,
        cwd=cwd,
        repo=repo,
        branch=branch,
        commit=commit,
        venv=venv,
        entrypoints=[n for n in ENTRYPOINT_NAMES if (path / n).is_file()],
        file_count=count_files(path),
    )
    projects.save(project, base=base)
    return project
