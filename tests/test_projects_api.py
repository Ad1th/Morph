"""Tests for /projects, /platform, and the /run target guard."""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from morph.api.app import app
from morph.api.routes.projects import REPO_ROOT, _safe_relative

client = TestClient(app)


def _upload(files):
    return client.post("/projects/upload", files=files)


def test_upload_rejects_parent_traversal():
    res = _upload([("files", ("../../evil.py", b"pwned", "text/plain"))])
    assert res.status_code == 400
    assert "traversal" in res.json()["detail"].lower()


def test_upload_rejects_nested_parent_traversal():
    res = _upload([("files", ("app/../../evil.py", b"pwned", "text/plain"))])
    assert res.status_code == 400


def test_upload_rejects_posix_absolute_path():
    res = _upload([("files", ("/etc/passwd", b"x", "text/plain"))])
    assert res.status_code == 400
    assert "absolute" in res.json()["detail"].lower()


def test_safe_relative_rejects_windows_paths():
    # httpx's multipart encoder basenames a backslash path client-side, so a
    # real browser is the only thing that can send one. Exercise the guard
    # itself rather than trusting the test client to carry it over the wire.
    for name in ("C:\\Windows\\System32\\evil.py", "\\\\server\\share\\evil.py", "app\\..\\..\\evil.py"):
        with pytest.raises(HTTPException) as excinfo:
            _safe_relative(name)
        assert excinfo.value.status_code == 400


def test_upload_writes_tree_and_skips_junk_dirs():
    res = _upload(
        [
            ("files", ("myapp/app.py", b"print(1)\n", "text/plain")),
            ("files", ("myapp/src/util.py", b"x = 1\n", "text/plain")),
            ("files", ("myapp/node_modules/left-pad/index.js", b"junk", "text/plain")),
            ("files", ("myapp/__pycache__/app.pyc", b"junk", "application/octet-stream")),
        ]
    )
    assert res.status_code == 200
    info = res.json()

    assert info["name"] == "myapp"
    assert info["file_count"] == 2
    assert info["entrypoints"] == ["app.py"]
    assert info["project_id"].startswith("proj-")

    root = Path(info["path"])
    assert (root / "src" / "util.py").is_file()
    assert not (root / "node_modules").exists()
    assert not (root / "__pycache__").exists()


def test_upload_over_cap_is_413_and_leaves_no_temp_dir(monkeypatch, tmp_path):
    from morph.api.routes import projects

    monkeypatch.setattr(projects, "MAX_UPLOAD_BYTES", 16)
    monkeypatch.setattr(projects.tempfile, "mkdtemp", lambda **kw: str(tmp_path / "proj"))
    (tmp_path / "proj").mkdir()

    res = _upload([("files", ("myapp/big.bin", b"x" * 64, "application/octet-stream"))])
    assert res.status_code == 413
    assert not (tmp_path / "proj").exists()


def test_local_project_detects_timeout_app_module_command():
    res = client.post("/projects/local", json={"path": str(REPO_ROOT / "apps" / "timeout")})
    assert res.status_code == 200
    info = res.json()

    assert info["name"] == "timeout"
    assert info["suggested_command"].endswith("-m apps.timeout test")
    assert Path(info["suggested_cwd"]) == REPO_ROOT
    assert "__main__.py" in info["entrypoints"]
    assert info["file_count"] > 0


def test_local_project_accepts_repo_relative_path():
    res = client.post("/projects/local", json={"path": "apps/timeout"})
    assert res.status_code == 200
    assert res.json()["name"] == "timeout"


def test_local_project_missing_dir_is_404():
    res = client.post("/projects/local", json={"path": "definitely/not/here"})
    assert res.status_code == 404


def test_local_project_file_is_400():
    res = client.post("/projects/local", json={"path": str(REPO_ROOT / "pyproject.toml")})
    assert res.status_code == 400


def test_local_project_single_script_command(tmp_path):
    (tmp_path / "solo.py").write_text("print(1)\n", encoding="utf-8")
    res = client.post("/projects/local", json={"path": str(tmp_path)})
    assert res.status_code == 200
    assert res.json()["suggested_command"].endswith("solo.py")


def test_local_project_npm_test_command(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}', encoding="utf-8")
    res = client.post("/projects/local", json={"path": str(tmp_path)})
    assert res.status_code == 200
    assert res.json()["suggested_command"] == "npm test"


def test_local_project_unrecognised_returns_null_command(tmp_path):
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    res = client.post("/projects/local", json={"path": str(tmp_path)})
    assert res.status_code == 200
    assert res.json()["suggested_command"] is None


def test_module_command_is_null_when_dir_name_is_not_importable(tmp_path):
    # "morph-project-8jodbogg" (an upload temp dir) cannot be imported, so
    # "py -3 -m morph-project-8jodbogg" would fail every time it ran.
    project = tmp_path / "morph-project-8jodbogg"
    project.mkdir()
    (project / "__main__.py").write_text("print(1)\n", encoding="utf-8")

    res = client.post("/projects/local", json={"path": str(project)})
    assert res.status_code == 200
    assert res.json()["suggested_command"] is None
    assert res.json()["suggested_cwd"] is None


def test_module_command_is_returned_when_dir_name_is_importable(tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    (project / "__main__.py").write_text("print(1)\n", encoding="utf-8")

    res = client.post("/projects/local", json={"path": str(project)})
    assert res.status_code == 200
    assert res.json()["suggested_command"].endswith("-m myapp")


def test_platform_shape_matches_adapter_capabilities():
    from morph.runtime.controller import get_default_adapter

    res = client.get("/platform")
    assert res.status_code == 200
    data = res.json()

    assert set(data) == {"host", "targets"}
    assert set(data["host"]) == {"family", "version", "arch"}
    assert data["host"]["family"]
    assert data["host"]["arch"]

    targets = {t["id"]: t for t in data["targets"]}
    assert set(targets) == {"local", "remote-ssh"}

    local = targets["local"]
    assert local["available"] is True
    assert local["reason"] is None
    assert local["family"] == data["host"]["family"]
    # Never claim a capability the active adapter does not report.
    assert local["capabilities"] == get_default_adapter().capabilities()

    remote = targets["remote-ssh"]
    assert remote["available"] is False
    assert remote["reason"]
    assert remote["capabilities"] == {}


def test_run_rejects_non_local_target():
    res = client.post("/run", json={"command": "echo hi", "target": "remote-ssh"})
    assert res.status_code == 400
    assert "remote-ssh" in res.json()["detail"]


def test_run_defaults_to_local_target():
    res = client.post("/run", json={"command": "echo hi"})
    assert res.status_code == 200


def test_threshold_returns_contract_shape_with_captured_profile():
    # profile=null means "capture the host", and a captured profile has no
    # network section; the route must still be able to search network.*.
    res = client.post(
        "/threshold",
        json={
            "command": "py -3 -c \"print(1)\"",
            "parameter": "network.latency_ms",
            "low": 0,
            "high": 400,
            "trials": 1,
            "precision": 150,
            "timeout": 30,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert set(data) == {
        "parameter",
        "safe_value",
        "failure_value",
        "boundary_estimate",
        "search_points",
    }
    assert data["parameter"] == "network.latency_ms"
    assert data["search_points"]
    assert set(data["search_points"][0]) == {"value", "failure_rate", "passed"}


def test_threshold_accepts_supplied_profile_without_network_section():
    # Captured profiles now collect baseline host network conditions.
    profile = client.post("/profiles/capture").json()
    assert profile["network"] is not None
    assert profile["network"]["latency_ms"]["status"] == "captured"

    # If a supplied profile has an absent network section, threshold search
    # treats it as unconstrained and still runs without answering 400.
    profile["network"] = None
    res = client.post(
        "/threshold",
        json={
            "command": "py -3 -c \"print(1)\"",
            "parameter": "network.latency_ms",
            "low": 0,
            "high": 400,
            "trials": 1,
            "precision": 150,
            "profile": profile,
            "timeout": 30,
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["parameter"] == "network.latency_ms"



def test_threshold_rejects_non_local_target():
    res = client.post(
        "/threshold",
        json={"command": "echo hi", "parameter": "network.latency_ms", "target": "remote-ssh"},
    )
    assert res.status_code == 400


def test_threshold_rejects_unknown_parameter():
    res = client.post(
        "/threshold",
        json={"command": "echo hi", "parameter": "bogus.field", "low": 0, "high": 10},
    )
    assert res.status_code == 400


def test_threshold_rejects_non_positive_precision():
    res = client.post(
        "/threshold",
        json={"command": "echo hi", "parameter": "network.latency_ms", "precision": 0},
    )
    assert res.status_code == 400


def test_normalize_github_repo_formats():
    from morph.api.routes.projects import _normalize_github_repo

    assert _normalize_github_repo("owner/repo") == (
        "https://github.com/owner/repo.git",
        "owner",
        "repo",
    )
    assert _normalize_github_repo("https://github.com/owner/repo") == (
        "https://github.com/owner/repo.git",
        "owner",
        "repo",
    )
    assert _normalize_github_repo("https://github.com/owner/repo.git") == (
        "https://github.com/owner/repo.git",
        "owner",
        "repo",
    )
    assert _normalize_github_repo("git@github.com:owner/repo.git") == (
        "https://github.com/owner/repo.git",
        "owner",
        "repo",
    )
    assert _normalize_github_repo("owner/repo", token="ghp_secret123") == (
        "https://x-access-token:ghp_secret123@github.com/owner/repo.git",
        "owner",
        "repo",
    )


def test_normalize_github_repo_rejects_invalid():
    from morph.api.routes.projects import _normalize_github_repo

    with pytest.raises(HTTPException) as excinfo:
        _normalize_github_repo("")
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        _normalize_github_repo("-flag/repo")
    assert excinfo.value.status_code == 400

    with pytest.raises(HTTPException) as excinfo:
        _normalize_github_repo("invalid_format_without_slash")
    assert excinfo.value.status_code == 400


def test_github_project_clones_and_describes(monkeypatch, tmp_path):
    from morph.api.routes import projects

    def fake_clone(clone_url, repo_name, branch=None, token=None):
        repo_dir = tmp_path / repo_name
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "main.py").write_text("print('hello')", encoding="utf-8")
        return repo_dir

    monkeypatch.setattr(projects, "_clone_github_repo", fake_clone)

    res = client.post("/projects/github", json={"repo": "myorg/sample-app", "token": "ghp_tok"})
    assert res.status_code == 200
    info = res.json()
    assert info["name"] == "sample-app"
    assert "main.py" in info["entrypoints"]
    assert info["file_count"] == 1


def test_github_project_redacts_token_on_clone_error(monkeypatch):
    import subprocess

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=128,
            stdout="",
            stderr=(
                "fatal: could not read Username for "
                "'https://x-access-token:ghp_supersecret@github.com': terminal prompts disabled"
            ),
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    res = client.post(
        "/projects/github",
        json={"repo": "myorg/private-repo", "token": "ghp_supersecret"},
    )
    assert res.status_code in (400, 401)
    assert "ghp_supersecret" not in res.text


def test_github_device_code_and_poll(monkeypatch):
    from morph.api.routes import projects

    def fake_http_json(url, method="GET", payload=None, token=None):
        if "device/code" in url:
            return {
                "device_code": "dev-1234",
                "user_code": "ABCD-5678",
                "verification_uri": "https://github.com/login/device",
                "expires_in": 900,
                "interval": 5,
            }
        if "oauth/access_token" in url:
            return {"access_token": "gho_access_token_123", "token_type": "bearer"}
        if "user/repos" in url:
            return [
                {
                    "full_name": "Ad1th/Morph",
                    "name": "Morph",
                    "private": False,
                    "default_branch": "main",
                    "description": "Cross-environment testing",
                    "html_url": "https://github.com/Ad1th/Morph",
                }
            ]
        return {}

    monkeypatch.setattr(projects, "_github_http_json", fake_http_json)

    res_code = client.post("/projects/github/device-code", json={"client_id": "client_123"})
    assert res_code.status_code == 200
    assert res_code.json()["user_code"] == "ABCD-5678"

    res_poll = client.post(
        "/projects/github/poll-token",
        json={"client_id": "client_123", "device_code": "dev-1234"},
    )
    assert res_poll.status_code == 200
    assert res_poll.json()["access_token"] == "gho_access_token_123"

    res_repos = client.post("/projects/github/repos", json={"token": "gho_access_token_123"})
    assert res_repos.status_code == 200
    repos = res_repos.json()
    assert len(repos) == 1
    assert repos[0]["full_name"] == "Ad1th/Morph"



