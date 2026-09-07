"""FastAPI routes for selecting the project Morph will run.

Three ways in, all ending in :func:`morph.project_setup.connect` -- the same
call `morph connect` and the TUI make, so a repo connected from the dashboard
lives where docs/projects.md says (``~/.morph/checkouts/<owner>-<repo>``),
gets the same detected command, and is registered in ``~/.morph/projects``:

- ``POST /projects/local`` points at a directory on this machine.
- ``POST /projects/upload`` writes an uploaded tree into a fresh temp dir first.
  Uploaded filenames are attacker-controlled, so every one is validated
  against absolute paths and ``..`` segments and the final path is checked to
  still be inside the temp dir before anything is written.
- ``POST /projects/github`` clones a repository (auth: request token, then
  ``MORPH_GITHUB_TOKEN`` / ``GITHUB_TOKEN`` / ``GH_TOKEN``, then ``gh auth token``).

Tokens are resolved server-side and never returned to the browser.
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

import morph
from morph import github as gh
from morph import project_setup
from morph import projects as registry
from morph.api.validation import IdPath
from morph.projects import Project
from morph.schema.project import ProjectInfo

router = APIRouter()

REPO_ROOT = Path(morph.__file__).resolve().parent.parent
# Kept as a module attribute for test fixtures that isolate ~/.morph; the
# install route itself goes through project_setup, which owns the real path.
VENVS_DIR = project_setup.VENVS_DIR

MAX_UPLOAD_BYTES = 50 * 1024 * 1024
MAX_UPLOAD_FILES = 5000
CHUNK_BYTES = 1024 * 1024
SKIP_DIRS = project_setup.SKIP_DIRS


class LocalProjectRequest(BaseModel):
    path: str = Field(min_length=1)
    install: bool = False
    name: str | None = None


class GithubProjectRequest(BaseModel):
    repo: str = Field(min_length=1)
    token: str | None = None
    branch: str | None = None
    install: bool = False
    name: str | None = None


class ProjectUpdateRequest(BaseModel):
    command: str | None = None
    cwd: str | None = None


class DeviceCodeRequest(BaseModel):
    client_id: str | None = None
    scope: str = "repo,read:user"


class PollTokenRequest(BaseModel):
    device_code: str
    client_id: str | None = None


class GithubReposRequest(BaseModel):
    # Optional: when absent the server resolves a token itself (env / gh CLI).
    token: str | None = None


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #


def _github_http_json(
    url: str,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    token: str | None = None,
) -> Any:
    if os.environ.get("MORPH_NO_NETWORK"):
        raise HTTPException(status_code=503, detail="Network access disabled (MORPH_NO_NETWORK)")
    headers = {"User-Agent": "Morph-App/1.0", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token.strip()}"

    data_bytes = None
    if payload is not None:
        headers["Content-Type"] = "application/json"
        data_bytes = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_text = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(err_text)
            msg = parsed.get("message") or parsed.get("error_description") or err_text
        except ValueError:
            msg = err_text
        raise HTTPException(
            status_code=exc.code, detail=f"GitHub request failed ({exc.code}): {msg}"
        ) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise HTTPException(status_code=502, detail=f"Failed to connect to GitHub: {exc}") from exc


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


def _inside(root: Path, candidate: Path) -> bool:
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


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
        source=project.source,
        repo=project.repo,
        branch=project.branch,
        commit=project.commit,
        venv=project.venv,
        created_at=project.created_at,
    )


def describe_project(project_dir: Path) -> ProjectInfo:
    """The ProjectInfo for a directory, using the shared detection (no registry write)."""
    command, cwd = project_setup.detect_command(project_dir)
    return ProjectInfo(
        project_id="",
        name=project_dir.name,
        path=str(project_dir),
        file_count=project_setup.count_files(project_dir),
        entrypoints=[n for n in project_setup.ENTRYPOINT_NAMES if (project_dir / n).is_file()],
        suggested_command=command,
        suggested_cwd=cwd,
    )


def _github_error(exc: gh.GitHubError) -> HTTPException:
    msg = str(exc)
    low = msg.lower()
    if "authentication" in low:
        return HTTPException(status_code=401, detail=msg)
    if "timed out" in low:
        return HTTPException(status_code=408, detail=msg)
    if "not found" in low:
        return HTTPException(status_code=404, detail=msg)
    return HTTPException(status_code=400, detail=msg)


def _connect(source: str, **kwargs: Any) -> Project:
    try:
        return project_setup.connect(source, **kwargs)
    except gh.GitHubError as exc:
        raise _github_error(exc) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


def _load(project_id: str) -> Project:
    try:
        return registry.load(project_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}") from exc


# --------------------------------------------------------------------------- #
# connect: upload / local / github
# --------------------------------------------------------------------------- #


@router.post(
    "/upload",
    response_model=ProjectInfo,
    summary="Upload a project directory",
    responses={
        400: {"description": "A filename is absolute, escapes the upload, or is empty"},
        413: {"description": "Upload exceeds the size or file-count limit"},
    },
)
async def upload_project(files: list[UploadFile] = File(...)) -> ProjectInfo:
    """Write an uploaded project tree to a temp dir, detect its command, register it."""
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_UPLOAD_FILES:
        raise HTTPException(status_code=413, detail=f"Upload exceeds {MAX_UPLOAD_FILES} files")

    temp_root = Path(tempfile.mkdtemp(prefix="morph-project-"))
    total_bytes = 0
    try:
        for upload in files:
            rel = _safe_relative(upload.filename or "")
            if SKIP_DIRS.intersection(rel.parts):
                continue

            destination = temp_root / Path(*rel.parts)
            if not _inside(temp_root, destination.parent) or destination.is_symlink():
                raise HTTPException(status_code=400, detail=f"Path rejected: '{upload.filename}'")
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
    project = _connect(str(project_dir))
    project.source = "upload"
    registry.save(project)
    return _as_info(project)


@router.post(
    "/local",
    response_model=ProjectInfo,
    summary="Connect a directory on this machine",
    responses={400: {"description": "Path is a file"}, 404: {"description": "Path does not exist"}},
)
def use_local_project(req: LocalProjectRequest) -> ProjectInfo:
    """Register a directory that already exists on this machine (relative
    paths resolve against the Morph repo root)."""
    candidate = Path(req.path).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    try:
        resolved = candidate.resolve()
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid path '{req.path}': {exc}") from exc
    if not resolved.exists():
        raise HTTPException(status_code=404, detail=f"Path '{req.path}' does not exist")
    if not resolved.is_dir():
        raise HTTPException(status_code=400, detail=f"Path '{req.path}' is a file, not a directory")
    return _as_info(_connect(str(resolved), install=req.install, name=req.name))


@router.post(
    "/github",
    response_model=ProjectInfo,
    summary="Clone and connect a GitHub repository",
    responses={
        400: {"description": "Invalid repository identifier or clone failure"},
        401: {"description": "Authentication failed (private repo without a usable token)"},
        404: {"description": "Repository or branch not found"},
        408: {"description": "Clone timed out"},
    },
)
def connect_github_project(req: GithubProjectRequest) -> ProjectInfo:
    """Clone into ``~/.morph/checkouts/<owner>-<repo>`` and register the project.
    The token, if any, is used server-side only."""
    try:
        gh.normalize_repo(req.repo)
    except gh.GitHubError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if os.environ.get("MORPH_NO_NETWORK"):
        raise HTTPException(status_code=503, detail="Network access disabled (MORPH_NO_NETWORK)")
    project = _connect(
        req.repo, token=req.token, branch=req.branch, install=req.install, name=req.name
    )
    return _as_info(project)


# --------------------------------------------------------------------------- #
# registry: list / get / update / delete / install
# --------------------------------------------------------------------------- #


@router.get("", response_model=list[ProjectInfo], summary="List connected projects")
def list_projects() -> list[ProjectInfo]:
    return [_as_info(p) for p in registry.list_projects()]


@router.get(
    "/github/auth-status",
    summary="Whether the server can authenticate to GitHub on its own",
)
def github_auth_status() -> dict[str, Any]:
    """Reports the token *source* (never the token) so the dashboard can skip
    the device flow when the machine is already authenticated."""
    source = gh.token_source()
    return {"authenticated": source != "none", "source": source}


@router.post(
    "/{project_id}/install",
    response_model=ProjectInfo,
    summary="Build a venv and install dependencies",
    responses={
        404: {"description": "No such project"},
        410: {"description": "Project directory is gone"},
        422: {"description": "Environment could not be built"},
    },
)
def install_project(project_id: IdPath) -> ProjectInfo:
    """Build the project an isolated venv and install its dependencies."""
    from morph import runenv

    project = _load(project_id)
    if not Path(project.path).is_dir():
        raise HTTPException(status_code=410, detail=f"Project directory is gone: {project.path}")
    try:
        updated = project_setup.reinstall(project)
    except runenv.EnvError as exc:
        raise HTTPException(status_code=422, detail=f"Could not build the environment: {exc}") from exc
    return _as_info(updated)


@router.get(
    "/{project_id}",
    response_model=ProjectInfo,
    summary="Fetch a connected project",
    responses={404: {"description": "No such project"}},
)
def get_project(project_id: IdPath) -> ProjectInfo:
    return _as_info(_load(project_id))


@router.put(
    "/{project_id}",
    response_model=ProjectInfo,
    summary="Set the run command / cwd of a project",
    responses={404: {"description": "No such project"}},
)
def update_project(project_id: IdPath, req: ProjectUpdateRequest) -> ProjectInfo:
    """Persist the command the user typed when detection returned ``null``."""
    project = _load(project_id)
    if req.command is not None:
        project.command = req.command.strip() or None
    if req.cwd is not None:
        project.cwd = req.cwd.strip() or None
    registry.save(project)
    return _as_info(project)


@router.delete(
    "/{project_id}",
    summary="Forget a connected project",
    responses={404: {"description": "No such project"}},
)
def delete_project(project_id: IdPath) -> dict[str, bool]:
    if not registry.delete(project_id):
        raise HTTPException(status_code=404, detail=f"No project {project_id!r}")
    return {"deleted": True}


# --------------------------------------------------------------------------- #
# GitHub OAuth device flow (browser fallback when the machine has no token)
# --------------------------------------------------------------------------- #


def _configured_client_id() -> str | None:
    """`github.client_id` from morph.yaml, if the project sets one."""
    try:
        from morph.config import load_config

        return (load_config().github.client_id or "").strip() or None
    except Exception:  # a malformed config must not break sign-in
        return None


def _client_id(explicit: str | None) -> str:
    client_id = (
        explicit or os.environ.get("GITHUB_CLIENT_ID") or _configured_client_id() or gh.DEFAULT_CLIENT_ID
    )
    if not client_id:
        raise HTTPException(
            status_code=400,
            detail=(
                "GitHub sign-in is not configured on this server. The device flow needs the "
                "public client id of a GitHub OAuth App with Device Flow enabled: put it under "
                "`github.client_id` in morph.yaml or export GITHUB_CLIENT_ID. Alternatively run "
                "`gh auth login` (Morph reads that token automatically) or set MORPH_GITHUB_TOKEN."
            ),
        )
    return client_id


@router.post("/github/device-code", summary="Start the GitHub device flow")
def request_device_code(req: DeviceCodeRequest) -> dict[str, Any]:
    """Request a device verification code from GitHub OAuth."""
    return _github_http_json(
        "https://github.com/login/device/code",
        method="POST",
        payload={"client_id": _client_id(req.client_id), "scope": req.scope},
    )


@router.post("/github/poll-token", summary="Poll the GitHub device flow")
def poll_device_token(req: PollTokenRequest) -> dict[str, Any]:
    """Poll GitHub OAuth for access token completion using the device code."""
    return _github_http_json(
        "https://github.com/login/oauth/access_token",
        method="POST",
        payload={
            "client_id": _client_id(req.client_id),
            "device_code": req.device_code,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        },
    )


@router.post(
    "/github/repos",
    summary="List repositories the token can see",
    responses={401: {"description": "No token given and none available on the server"}},
)
def list_github_repositories(req: GithubReposRequest | None = None) -> list[dict[str, Any]]:
    """Repositories accessible to the request token, or to the server's own
    token (env / ``gh`` CLI) when none is given. The token never leaves the server."""
    token = gh.resolve_token(req.token if req else None)
    if not token:
        raise HTTPException(
            status_code=401,
            detail="No GitHub token: pass one, run `gh auth login`, or set MORPH_GITHUB_TOKEN.",
        )
    raw_repos = _github_http_json(
        "https://api.github.com/user/repos?per_page=100&sort=updated", method="GET", token=token
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
