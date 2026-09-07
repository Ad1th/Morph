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
import re
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel

import morph
from morph import github as gh
from morph import projects as registry
from morph import runenv
from morph.projects import Project
from morph.schema.project import ProjectInfo

router = APIRouter()

VENVS_DIR = Path.home() / ".morph" / "venvs"

REPO_ROOT = Path(morph.__file__).resolve().parent.parent
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SKIP_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build"})

# Ordered: the first one present is the most likely thing the user runs.
ENTRYPOINT_NAMES = ("__main__.py", "main.py", "app.py", "run.py", "manage.py", "index.js", "server.js")

# Bare "python3": run_with_telemetry._pin_interpreter rewrites it to
# sys.executable, so the child gets the interpreter Morph is running under
# (and therefore Morph's dependencies) on every platform.
PYTHON = "python3"


class LocalProjectRequest(BaseModel):
    path: str


class GithubProjectRequest(BaseModel):
    repo: str
    token: str | None = None
    branch: str | None = None


class DeviceCodeRequest(BaseModel):
    client_id: str | None = None
    scope: str = "repo,read:user"


class PollTokenRequest(BaseModel):
    device_code: str
    client_id: str | None = None


class GithubReposRequest(BaseModel):
    token: str


def _github_http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    headers = {
        "User-Agent": "Morph-App/1.0",
        "Accept": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    data_bytes = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw)
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_text)
            msg = parsed.get("message") or parsed.get("error_description") or err_text
        except Exception:
            msg = err_text
        raise HTTPException(status_code=exc.code, detail=f"GitHub request failed ({exc.code}): {msg}")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to connect to GitHub: {exc}")



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


def _as_info(project: Project) -> ProjectInfo:
    return ProjectInfo(
        project_id=project.id,
        name=project.name,
        path=project.path,
        file_count=project.file_count,
        entrypoints=project.entrypoints,
        suggested_command=project.command,
        suggested_cwd=project.cwd,
        deps_failed=project.deps_failed,
    )


def _persist(
    info: ProjectInfo,
    *,
    source: str,
    repo: str | None = None,
    branch: str | None = None,
    commit: str | None = None,
    venv: str | None = None,
) -> ProjectInfo:
    """Mirror a described project into the durable registry and return it back."""
    project = Project(
        id=info.project_id,
        name=info.name,
        source=source,
        path=info.path,
        command=info.suggested_command,
        cwd=info.suggested_cwd,
        repo=repo,
        branch=branch,
        commit=commit,
        venv=venv,
        entrypoints=info.entrypoints,
        file_count=info.file_count,
    )
    registry.save(project)
    return info


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
    return _persist(describe_project(project_dir), source="upload")


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

    return _persist(describe_project(resolved), source="local")


@router.post("/github", response_model=ProjectInfo)
def connect_github_project(req: GithubProjectRequest) -> ProjectInfo:
    """Clone a GitHub repository (auth: token, then env, then `gh auth token`)."""
    token = gh.resolve_token(req.token)
    clone_url, owner, repo_name = _normalize_github_repo(req.repo, token)
    cloned_dir = _clone_github_repo(clone_url, repo_name, req.branch, token)
    commit = subprocess.run(
        ["git", "-C", str(cloned_dir), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    ).stdout.strip() or None
    return _persist(
        describe_project(cloned_dir),
        source="github", repo=f"{owner}/{repo_name}", branch=req.branch, commit=commit,
    )


# --- registry: list / get / delete / install ------------------------------- #


@router.get("", response_model=list[ProjectInfo])
def list_projects() -> list[ProjectInfo]:
    return [_as_info(p) for p in registry.list_projects()]


@router.post("/github/cli-token")
def github_cli_token() -> dict[str, Any]:
    """A token from the local `gh` CLI or environment, so the browser can skip
    the device flow when the machine is already authenticated."""
    return {"token": gh.resolve_token(), "source": gh.token_source()}


@router.post("/{project_id}/install", response_model=ProjectInfo)
def install_project(project_id: str) -> ProjectInfo:
    """Build the project an isolated venv and install its dependencies."""
    try:
        project = registry.load(project_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")

    project_dir = Path(project.path)
    if not project_dir.is_dir():
        raise HTTPException(status_code=410, detail=f"Project directory is gone: {project.path}")

    try:
        result = runenv.prepare(project_dir, VENVS_DIR / project.name, command=project.command)
    except runenv.EnvError as exc:
        raise HTTPException(status_code=422, detail=f"Could not build the environment: {exc}")

    project.deps_failed = result.failed
    if result.venv is not None:
        project.venv = str(result.venv)
        if project.command:
            project.command = runenv.command_in_env(project.command, str(result.venv))
    registry.save(project)
    return _as_info(project)


@router.get("/{project_id}", response_model=ProjectInfo)
def get_project(project_id: str) -> ProjectInfo:
    try:
        return _as_info(registry.load(project_id))
    except KeyError:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")


@router.delete("/{project_id}")
def delete_project(project_id: str) -> dict[str, bool]:
    return {"deleted": registry.delete(project_id)}


@router.post("/github/device-code")
def request_device_code(req: DeviceCodeRequest) -> dict[str, Any]:
    """Request a device verification code from GitHub OAuth."""
    client_id = req.client_id or os.environ.get("GITHUB_CLIENT_ID") or gh.DEFAULT_CLIENT_ID
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "No GitHub OAuth client_id. Authenticate with `gh auth login` (Morph "
                "reads its token automatically), set MORPH_GITHUB_TOKEN, or set "
                "GITHUB_CLIENT_ID for the device flow."
            ),
        )
    return _github_http_json(
        "https://github.com/login/device/code",
        method="POST",
        payload={"client_id": client_id, "scope": req.scope},
    )


@router.post("/github/poll-token")
def poll_device_token(req: PollTokenRequest) -> dict[str, Any]:
    """Poll GitHub OAuth for access token completion using the device code."""
    client_id = req.client_id or os.environ.get("GITHUB_CLIENT_ID") or gh.DEFAULT_CLIENT_ID
    if not client_id:
        raise HTTPException(status_code=400, detail="GitHub client_id is required to poll for a token.")
    return _github_http_json(
        "https://github.com/login/oauth/access_token",
        method="POST",
        payload={
            "client_id": client_id,
            "device_code": req.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )


@router.post("/github/repos")
def list_github_repositories(req: GithubReposRequest) -> list[dict[str, Any]]:
    """Fetch repositories accessible by the authorized GitHub token."""
    raw_repos = _github_http_json(
        "https://api.github.com/user/repos?per_page=100&sort=updated",
        method="GET",
        token=req.token,
    )
    if not isinstance(raw_repos, list):
        return []

    return [
        {
            "full_name": repo.get("full_name", ""),
            "name": repo.get("name", ""),
            "private": bool(repo.get("private")),
            "default_branch": repo.get("default_branch", "main"),
            "description": repo.get("description") or "",
            "html_url": repo.get("html_url", ""),
        }
        for repo in raw_repos
        if isinstance(repo, dict) and repo.get("full_name")
    ]


