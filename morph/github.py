"""GitHub auth + clone, shared by the API routes, the CLI, and the TUI.

Token resolution order (first hit wins):

1. an explicit token passed in
2. ``MORPH_GITHUB_TOKEN`` / ``GITHUB_TOKEN`` / ``GH_TOKEN``
3. ``gh auth token`` -- zero-config if the user has run ``gh auth login``

Only when all three miss does anything need the OAuth device flow.
"""

from __future__ import annotations

import base64
import os
import re
import shutil
import subprocess
from pathlib import Path

# Public client_id of Morph's GitHub OAuth App. The device flow carries no
# secret, so this can ship in the clear. Overridden by GITHUB_CLIENT_ID.
DEFAULT_CLIENT_ID = os.environ.get("GITHUB_CLIENT_ID", "").strip()

_TOKEN_ENV_VARS = ("MORPH_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN")

_SSH_RE = re.compile(r"^git@github\.com:([\w.-]+)/([\w.-]+?)(?:\.git)?$")
_NAME_RE = re.compile(r"^[\w.-]+$")


class GitHubError(RuntimeError):
    """A GitHub operation failed, with a message safe to show the user."""


# --------------------------------------------------------------------------- #
# auth
# --------------------------------------------------------------------------- #

def _gh_cli_token() -> str | None:
    gh = shutil.which("gh")
    if not gh:
        return None
    try:
        out = subprocess.run(
            [gh, "auth", "token"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    token = out.stdout.strip()
    return token or None


def resolve_token(explicit: str | None = None) -> str | None:
    """Best available GitHub token, or None if the user must authenticate."""
    if explicit and explicit.strip():
        return explicit.strip()
    for var in _TOKEN_ENV_VARS:
        value = (os.environ.get(var) or "").strip()
        if value:
            return value
    return _gh_cli_token()


def token_source(explicit: str | None = None) -> str:
    """Where :func:`resolve_token` would get a token -- for status display."""
    if explicit and explicit.strip():
        return "argument"
    for var in _TOKEN_ENV_VARS:
        if (os.environ.get(var) or "").strip():
            return var
    if _gh_cli_token():
        return "gh cli"
    return "none"


# --------------------------------------------------------------------------- #
# repo identifiers + clone
# --------------------------------------------------------------------------- #

def normalize_repo(repo: str) -> tuple[str, str]:
    """``owner/repo`` from any of owner/repo, a URL, or an SSH remote."""
    cleaned = (repo or "").strip()
    if not cleaned or cleaned.startswith("-"):
        raise GitHubError(f"Invalid repository: {repo!r}")

    ssh = _SSH_RE.match(cleaned)
    if ssh:
        owner, name = ssh.groups()
    else:
        body = re.sub(r"^https?://", "", cleaned)
        body = re.sub(r"^github\.com/", "", body)
        body = re.sub(r"\.git$", "", body).strip("/")
        parts = body.split("/")
        if len(parts) != 2 or not all(parts):
            raise GitHubError(
                f"Invalid GitHub repository {repo!r}. "
                "Use 'owner/repo' or 'https://github.com/owner/repo'."
            )
        owner, name = parts

    if not _NAME_RE.match(owner) or not _NAME_RE.match(name):
        raise GitHubError(f"Invalid repository name: {owner}/{name}")
    return owner, name


def clone_url(owner: str, name: str, token: str | None = None) -> str:
    """The clone URL. The token is deliberately NOT embedded: it would land in
    argv (visible to `ps`) and in `.git/config` as remote.origin.url for the
    life of the checkout. Credentials travel via :func:`git_auth_env` instead."""
    return f"https://github.com/{owner}/{name}.git"


def git_auth_env(token: str | None) -> dict[str, str]:
    """Environment that authenticates git to github.com for ONE process.

    Uses git's env-only config mechanism (GIT_CONFIG_COUNT/KEY/VALUE), so the
    header exists only in the child's environment: nothing is written to any
    config file and nothing appears on a command line.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    if token and token.strip():
        b64 = base64.b64encode(f"x-access-token:{token.strip()}".encode()).decode()
        env.update({
            "GIT_CONFIG_COUNT": "1",
            "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
            "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {b64}",
        })
    return env


def redact(text: str, token: str | None) -> str:
    """Remove the token (raw and base64-encoded) from any text shown to a user."""
    out = text or ""
    if token and token.strip():
        raw = token.strip()
        out = out.replace(raw, "***")
        b64 = base64.b64encode(f"x-access-token:{raw}".encode()).decode()
        out = out.replace(b64, "***")
    return re.sub(r"AUTHORIZATION:\s*basic\s+\S+", "AUTHORIZATION: basic ***", out)


def _friendly_clone_error(stderr: str, branch: str | None) -> str:
    low = stderr.lower()
    if any(s in stderr for s in ("Authentication failed", "could not read Username",
                                 "Invalid username or password")):
        return (
            "GitHub authentication failed. The repo may be private -- run "
            "`gh auth login`, or set MORPH_GITHUB_TOKEN."
        )
    if branch and "not found" in low and "branch" in low:
        return f"Branch {branch!r} not found in the repository."
    if "repository not found" in low or "not found" in low:
        return "Repository not found (or private and not authorized)."
    return f"git clone failed: {stderr.strip()}"


def clone(
    repo: str,
    dest: Path,
    *,
    token: str | None = None,
    branch: str | None = None,
    depth: int = 1,
    timeout: float = 120.0,
) -> tuple[Path, str]:
    """Clone ``repo`` into ``dest/<name>``; return ``(path, short_sha)``.

    ``token`` is resolved via :func:`resolve_token` when not given.
    """
    owner, name = normalize_repo(repo)
    token = resolve_token(token)
    target = Path(dest) / name

    cmd = ["git", "clone", "--depth", str(depth)]
    if branch and branch.strip():
        cmd += ["--branch", branch.strip()]
    cmd += [clone_url(owner, name), str(target)]
    env = git_auth_env(token)

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        raise GitHubError(f"Cloning {owner}/{name} timed out after {timeout:.0f}s")
    except (OSError, subprocess.SubprocessError) as exc:
        raise GitHubError(f"Could not run git clone: {redact(str(exc), token)}")

    if proc.returncode != 0:
        err = redact(proc.stderr or proc.stdout or "unknown error", token)
        raise GitHubError(_friendly_clone_error(err, branch))

    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--short", "HEAD"],
        capture_output=True, text=True,
    )
    return target, head.stdout.strip() or "unknown"
