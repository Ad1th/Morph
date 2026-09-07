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


def _pyproject_scripts(project_dir: Path) -> list[str]:
    pyproject = project_dir / "pyproject.toml"
    if not pyproject.is_file():
        return []
    try:
        import tomllib

        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except Exception:
        return []
    return list((data.get("project") or {}).get("scripts", {}))


def _pytest_target(project_dir: Path) -> str:
    """A scoped pytest invocation: run one tests dir, stop at the first failure,
    and drop project addopts (e.g. --doctest-modules pulls in the whole tree)."""
    for name in ("tests", "test"):
        if (project_dir / name).is_dir():
            target = name
            break
    else:
        target = "."
    return f"{PYTHON} -m pytest -q -x -p no:cacheprovider -o addopts= {target}"


def detect_command(project_dir: Path) -> tuple[str | None, str | None]:
    """Return ``(suggested_command, suggested_cwd)`` -- a detection, not a guess.

    Prefers running *the app* (an entrypoint / console script) over its whole
    test suite. Nothing recognised -> ``(None, None)`` so the caller asks.
    """
    project_dir = Path(project_dir)
    cwd = str(project_dir)

    # 1. an installed console script (needs `-e .`, which --install does)
    scripts = _pyproject_scripts(project_dir)
    if scripts:
        return f"{scripts[0]} --help", cwd

    # 2. a runnable entrypoint at the repo root
    if (project_dir / "__main__.py").is_file():
        try:
            parts = project_dir.relative_to(REPO_ROOT).parts
            if all(p.isidentifier() for p in parts):
                return f"{PYTHON} -m {'.'.join(parts)}", str(REPO_ROOT)
        except ValueError:
            pass
        return f"{PYTHON} __main__.py", cwd
    for name in ("main.py", "app.py", "run.py", "server.py", "cli.py"):
        if (project_dir / name).is_file():
            return f"{PYTHON} {name}", cwd

    # 3. framework / package conventions
    if (project_dir / "manage.py").is_file():
        return f"{PYTHON} manage.py check", cwd

    package_json = project_dir / "package.json"
    if package_json.is_file():
        try:
            import json

            scripts_js = json.loads(package_json.read_text(encoding="utf-8")).get("scripts", {})
        except (OSError, ValueError):
            scripts_js = {}
        if "start" in scripts_js:
            return "npm start", cwd
        if "test" in scripts_js:
            return "npm test", cwd

    top_level_py = [p for p in project_dir.glob("*.py") if p.is_file()]
    if len(top_level_py) == 1:
        return f"{PYTHON} {top_level_py[0].name}", cwd

    # 4. last resort: a scoped run of the test suite
    if (project_dir / "pytest.ini").is_file() or (project_dir / "tests").is_dir() \
            or (project_dir / "test").is_dir():
        return _pytest_target(project_dir), cwd

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
        venv_path = runenv.prepare(path, VENVS_DIR / f"{ident}", command=command, logger=logger)
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
