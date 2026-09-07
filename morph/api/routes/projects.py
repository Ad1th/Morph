"""FastAPI routes for selecting the project Morph will run.

Two ways in, both ending at the same `ProjectInfo`:

- `POST /projects/upload` writes an uploaded directory tree into a fresh temp
  dir. Uploaded filenames are attacker-controlled, so every one is validated
  against absolute paths and `..` segments before it is joined to the temp dir.
- `POST /projects/local` points at a directory that already exists on this
  machine. Morph is local-first and the API runs on the same box as the
  browser, so copying the `apps/` demos would be pure ceremony.

`suggested_command` is a detection, not a guess: when nothing matches it stays
None and the frontend asks the user for the command.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

import morph
from morph.schema.project import ProjectInfo

router = APIRouter()

REPO_ROOT = Path(morph.__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"})

# Ordered: the first one present is the most likely thing the user runs.
ENTRYPOINT_NAMES = ("__main__.py", "main.py", "app.py", "run.py", "manage.py", "index.js", "server.js")

PYTHON = "py -3" if platform.system() == "Windows" else "python3"


class LocalProjectRequest(BaseModel):
    path: str


class GithubProjectRequest(BaseModel):
    repo: str
    token: str | None = None
    branch: str | None = None


def _normalize_github_repo(repo: str, token: str | None = None) -> tuple[str, str, str]:
    """Parse a GitHub repository identifier and return (clone_url, owner, repo_name).

    Supports 'owner/repo', 'github.com/owner/repo', 'https://github.com/owner/repo',
    or 'git@github.com:owner/repo'.
    """
    cleaned = repo.strip()
    if not cleaned:
        raise HTTPException(status_code=400, detail="Repository URL or owner/repo is required")

    if cleaned.startswith("-"):
        raise HTTPException(status_code=400, detail=f"Invalid repository format: '{cleaned}'")

    ssh_match = re.match(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?$", cleaned)
    if ssh_match:
        owner, repo_name = ssh_match.groups()
    else:
        without_scheme = re.sub(r"^https?://", "", cleaned)
        without_host = re.sub(r"^github\.com/", "", without_scheme)
        without_dot_git = re.sub(r"\.git$", "", without_host).strip("/")
        parts = without_dot_git.split("/")
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid GitHub repository '{cleaned}'. "
                    "Expected format: 'owner/repo' or 'https://github.com/owner/repo'"
                ),
            )
        owner, repo_name = parts[0], parts[1]

    if not re.match(r"^[\w.-]+$", owner) or not re.match(r"^[\w.-]+$", repo_name):
        raise HTTPException(status_code=400, detail=f"Invalid repository name: '{owner}/{repo_name}'")

    if token and token.strip():
        token_clean = token.strip()
        clone_url = f"https://x-access-token:{token_clean}@github.com/{owner}/{repo_name}.git"
    else:
        clone_url = f"https://github.com/{owner}/{repo_name}.git"

    return clone_url, owner, repo_name


def _clone_github_repo(
    clone_url: str,
    repo_name: str,
    branch: str | None = None,
    token: str | None = None,
) -> Path:
    temp_dir = Path(tempfile.mkdtemp(prefix="morph-github-"))
    target_dir = temp_dir / repo_name

    cmd = ["git", "clone", "--depth", "1"]
    if branch and branch.strip():
        cmd.extend(["--branch", branch.strip()])
    cmd.extend([clone_url, str(target_dir)])

    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            env=env,
        )
    except subprocess.TimeoutExpired:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=408, detail="Cloning repository timed out (limit: 60s)")
    except Exception as exc:
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Failed to execute git clone: {exc}")

    if proc.returncode != 0:
        shutil.rmtree(temp_dir, ignore_errors=True)
        err_msg = proc.stderr or proc.stdout or "Unknown git error"
        if token and token.strip() and token.strip() in err_msg:
            err_msg = err_msg.replace(token.strip(), "***")

        if (
            "Authentication failed" in err_msg
            or "could not read Username" in err_msg
            or "Invalid username or password" in err_msg
        ):
            raise HTTPException(
                status_code=401,
                detail=(
                    "GitHub authentication failed. "
                    "Please verify your repository URL and Personal Access Token."
                ),
            )
        if "Remote branch" in err_msg and "not found" in err_msg:
            raise HTTPException(
                status_code=404,
                detail=f"Branch '{branch}' not found in repository.",
            )
        if "Repository not found" in err_msg or "not found" in err_msg.lower():
            raise HTTPException(
                status_code=404,
                detail=(
                    "Repository not found. "
                    "For private repositories, please provide a valid GitHub Personal Access Token."
                ),
            )
        raise HTTPException(status_code=400, detail=f"Git clone failed: {err_msg.strip()}")

    return target_dir


def _safe_relative(filename: str) -> PurePosixPath:
    """Validate one uploaded filename as a relative path inside the project.

    Trust boundary: rejects absolute paths (POSIX or Windows drive/UNC form)
    and any `..` segment, so the join below can never escape the temp dir.
    """
    if not filename:
        raise HTTPException(status_code=400, detail="Upload contains a file with no name")

    normalized = filename.replace("\\", "/")
    rel = PurePosixPath(normalized)

    if rel.is_absolute() or normalized.startswith("//"):
        raise HTTPException(status_code=400, detail=f"Absolute path rejected: '{filename}'")
    # "C:/x" is not absolute to PurePosixPath but is to Windows.
    head = rel.parts[0] if rel.parts else ""
    if len(head) == 2 and head[1] == ":":
        raise HTTPException(status_code=400, detail=f"Absolute path rejected: '{filename}'")
    if any(part == ".." for part in rel.parts):
        raise HTTPException(status_code=400, detail=f"Path traversal rejected: '{filename}'")
    if not rel.name:
        raise HTTPException(status_code=400, detail=f"Not a file path: '{filename}'")

    return rel


def _has_npm_test_script(package_json: Path) -> bool:
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and "test" in (data.get("scripts") or {})


def _detect_command(project_dir: Path) -> tuple[str | None, str | None]:
    """Return (suggested_command, suggested_cwd) for a project directory."""
    if (project_dir / "__main__.py").is_file():
        # Module form needs the package's parent on sys.path, so cwd is the
        # root the dotted path is measured from: the repo root when the
        # project sits inside it (this is what makes `apps/timeout` work),
        # otherwise the project's own parent.
        try:
            parts = project_dir.relative_to(REPO_ROOT).parts
            candidate = (f"{PYTHON} -m {'.'.join(parts)} test", str(REPO_ROOT))
        except ValueError:
            parts = (project_dir.name,)
            candidate = (f"{PYTHON} -m {project_dir.name}", str(project_dir.parent))
        # `-m` needs an importable dotted name, so a directory such as an
        # upload's "morph-project-8jodbogg" has no module form at all. Report
        # nothing rather than a command that is known to fail on sight.
        return candidate if all(p.isidentifier() for p in parts) else (None, None)

    cwd = str(project_dir)
    package_json = project_dir / "package.json"
    if package_json.is_file() and _has_npm_test_script(package_json):
        return "npm test", cwd
    if (project_dir / "manage.py").is_file():
        return f"{PYTHON} manage.py test", cwd
    if (project_dir / "pytest.ini").is_file() or (project_dir / "tests").is_dir():
        return f"{PYTHON} -m pytest -q", cwd

    top_level_py = [p for p in project_dir.glob("*.py") if p.is_file()]
    if len(top_level_py) == 1:
        return f"{PYTHON} {top_level_py[0].name}", cwd

    return None, None


def _count_files(project_dir: Path) -> int:
    total = 0
    for path in project_dir.rglob("*"):
        if path.is_file() and not SKIP_DIRS.intersection(path.relative_to(project_dir).parts):
            total += 1
    return total


def describe_project(project_dir: Path) -> ProjectInfo:
    """Build the ProjectInfo for a directory that already exists on disk."""
    command, cwd = _detect_command(project_dir)
    return ProjectInfo(
        project_id=f"proj-{uuid.uuid4().hex[:8]}",
        name=project_dir.name,
        path=str(project_dir),
        file_count=_count_files(project_dir),
        entrypoints=[n for n in ENTRYPOINT_NAMES if (project_dir / n).is_file()],
        suggested_command=command,
        suggested_cwd=cwd,
    )


@router.post("/upload", response_model=ProjectInfo)
async def upload_project(files: list[UploadFile] = File(...)) -> ProjectInfo:
    """Write an uploaded project tree to a temp dir and describe it."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    temp_root = Path(tempfile.mkdtemp(prefix="morph-project-"))
    total_bytes = 0
    try:
        for upload in files:
            rel = _safe_relative(upload.filename or "")
            if SKIP_DIRS.intersection(rel.parts):
                continue

            destination = temp_root / Path(*rel.parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with destination.open("wb") as handle:
                while chunk := await upload.read(CHUNK_BYTES):
                    total_bytes += len(chunk)
                    if total_bytes > MAX_UPLOAD_BYTES:
                        raise HTTPException(
                            status_code=413,
                            detail=f"Upload exceeds the {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit",
                        )
                    handle.write(chunk)
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise

    # webkitRelativePath always starts with the selected folder's name, so the
    # real project root is that single directory rather than the temp dir.
    entries = list(temp_root.iterdir())
    project_dir = entries[0] if len(entries) == 1 and entries[0].is_dir() else temp_root
    return describe_project(project_dir)


@router.post("/local", response_model=ProjectInfo)
def use_local_project(req: LocalProjectRequest) -> ProjectInfo:
    """Describe a directory that already exists on this machine."""
    candidate = Path(req.path).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate

    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path '{req.path}': {exc}")

    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Path '{req.path}' does not exist")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Path '{req.path}' is a file, not a directory")

    return describe_project(resolved)


@router.post("/github", response_model=ProjectInfo)
def connect_github_project(req: GithubProjectRequest) -> ProjectInfo:
    """Clone a GitHub repository (with optional authentication) and describe it."""
    clone_url, _, repo_name = _normalize_github_repo(req.repo, req.token)
    cloned_dir = _clone_github_repo(clone_url, repo_name, req.branch, req.token)
    return describe_project(cloned_dir)

