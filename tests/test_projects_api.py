"""Tests for /projects, /platform, and the /run target guard.

Everything here runs against a temporary HOME: the registry, checkouts and
venvs are pointed at ``tmp_path`` so nothing is written to the developer's
real ``~/.morph``.
"""

from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from morph.api.app import app
from morph.api.routes.projects import REPO_ROOT, _safe_relative

client = TestClient(app)


@pytest.fixture(autouse=True)
def _temp_home(tmp_path, monkeypatch):
    """A throwaway HOME for every test in this module (conftest also patches the
    registry / checkouts / venvs module attributes, this covers anything that
    computes ``Path.home()`` afresh)."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    # CI sets MORPH_NO_NETWORK=1; the GitHub tests below stub the network out.
    monkeypatch.delenv("MORPH_NO_NETWORK", raising=False)
    yield home


def _upload(files):
    return client.post("/projects/upload", files=files)


# --- upload: trust boundary ------------------------------------------------ #


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
    assert res.status_code == 200, res.text
    info = res.json()

    assert info["name"] == "myapp"
    assert info["file_count"] == 2
    assert info["entrypoints"] == ["app.py"]
    assert info["project_id"].startswith("proj-")
    assert info["source"] == "upload"
    assert info["suggested_command"] == "python3 app.py"

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


def test_upload_too_many_files_is_413(monkeypatch):
    from morph.api.routes import projects

    monkeypatch.setattr(projects, "MAX_UPLOAD_FILES", 2)
    res = _upload([("files", (f"myapp/f{i}.py", b"x", "text/plain")) for i in range(3)])
    assert res.status_code == 413


def test_upload_never_follows_a_symlink_out_of_the_temp_dir(monkeypatch, tmp_path):
    from morph.api.routes import projects

    root = tmp_path / "proj"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "myapp").symlink_to(outside, target_is_directory=True)
    monkeypatch.setattr(projects.tempfile, "mkdtemp", lambda **kw: str(root))

    res = _upload([("files", ("myapp/escaped.py", b"pwned", "text/plain"))])
    assert res.status_code == 400
    assert not (outside / "escaped.py").exists()


# --- local: same detection as `morph connect` ----------------------------- #


def test_local_project_detects_timeout_app_module_command():
    res = client.post("/projects/local", json={"path": str(REPO_ROOT / "apps" / "timeout")})
    assert res.status_code == 200
    info = res.json()

    assert info["name"] == "timeout"
    assert info["suggested_command"].endswith("-m apps.timeout")
    assert Path(info["suggested_cwd"]) == REPO_ROOT
    assert "__main__.py" in info["entrypoints"]
    assert info["file_count"] > 0
    assert info["source"] == "local"


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


def test_api_and_cli_agree_on_detected_command(tmp_path):
    """The API must delegate to project_setup.detect_command, not re-implement it."""
    from morph import project_setup

    project = tmp_path / "morph-project-8jodbogg"
    project.mkdir()
    (project / "__main__.py").write_text("print(1)\n", encoding="utf-8")

    res = client.post("/projects/local", json={"path": str(project)})
    assert res.status_code == 200
    expected_cmd, expected_cwd = project_setup.detect_command(project)
    assert res.json()["suggested_command"] == expected_cmd
    assert res.json()["suggested_cwd"] == expected_cwd


def test_module_command_is_returned_when_dir_name_is_importable(tmp_path):
    project = tmp_path / "myapp"
    project.mkdir()
    (project / "__main__.py").write_text("print(1)\n", encoding="utf-8")

    res = client.post("/projects/local", json={"path": str(project)})
    assert res.status_code == 200
    assert res.json()["suggested_command"].endswith("__main__.py")


# --- platform / run target --------------------------------------------------- #


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
    assert remote["capabilities"] == {}
    assert isinstance(remote["available"], bool)


def test_platform_reflects_configured_worker(monkeypatch):
    monkeypatch.setenv("MORPH_CLOUD_HOST", "worker.example")
    res = client.get("/platform")
    remote = {t["id"]: t for t in res.json()["targets"]}["remote-ssh"]
    assert remote["available"] is True
    assert "worker.example" in remote["label"]


def test_run_rejects_non_local_target():
    res = client.post("/run", json={"command": "echo hi", "target": "remote-ssh"})
    assert res.status_code == 400
    assert "remote-ssh" in res.json()["detail"]


def test_run_defaults_to_local_target():
    res = client.post("/run", json={"command": "echo hi"})
    assert res.status_code == 200


# --- threshold ------------------------------------------------------------- #


def test_threshold_bisect_returns_contract_shape_with_captured_profile():
    # profile=null means "capture the host", and a captured profile has no
    # network section; the route must still be able to search network.*.
    res = client.post(
        "/threshold",
        json={
            "command": "python3 -c \"print(1)\"",
            "parameter": "network.latency_ms",
            "low": 0,
            "high": 400,
            "trials": 1,
            "precision": 150,
            "timeout": 30,
            "method": "bisect",
        },
    )
    assert res.status_code == 200, res.text
    data = res.json()
    assert {"parameter", "safe_value", "failure_value", "boundary_estimate", "search_points",
            "outcome", "method"} <= set(data)
    assert data["parameter"] == "network.latency_ms"
    assert data["method"] == "bisection"
    assert data["outcome"] == "never_fails"
    assert data["search_points"]
    assert {"value", "failure_rate", "passed"} <= set(data["search_points"][0])


def test_threshold_accepts_supplied_profile_without_network_section():
    profile = client.post("/profiles/capture").json()
    # If a supplied profile has an absent network section, threshold search
    # treats it as unconstrained and still runs without answering 400.
    profile["network"] = None
    res = client.post(
        "/threshold",
        json={
            "command": "python3 -c \"print(1)\"",
            "parameter": "network.latency_ms",
            "low": 0,
            "high": 400,
            "max_trials": 4,
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
    assert res.status_code == 422


# --- github ---------------------------------------------------------------- #


def test_github_project_rejects_invalid_repo():
    for repo in ("", "-flag/repo", "invalid_format_without_slash"):
        res = client.post("/projects/github", json={"repo": repo})
        assert res.status_code in (400, 422), repo


def test_github_project_clones_into_checkouts_and_describes(monkeypatch, tmp_path):
    from morph import github, project_setup

    seen = {}

    def fake_clone(repo, dest, *, token=None, branch=None, **kw):
        seen["dest"] = Path(dest)
        seen["token"] = token
        repo_dir = Path(dest) / "sample-app"
        repo_dir.mkdir(parents=True, exist_ok=True)
        (repo_dir / "main.py").write_text("print('hello')", encoding="utf-8")
        return repo_dir, "abc1234"

    monkeypatch.setattr(github, "clone", fake_clone)

    res = client.post("/projects/github", json={"repo": "myorg/sample-app", "token": "ghp_tok"})
    assert res.status_code == 200, res.text
    info = res.json()
    assert info["name"] == "sample-app"
    assert "main.py" in info["entrypoints"]
    assert info["file_count"] == 1
    assert info["source"] == "github"
    assert info["repo"] == "myorg/sample-app"
    assert info["commit"] == "abc1234"
    # Cloned where docs/projects.md says, not into /tmp.
    assert seen["dest"] == project_setup.CHECKOUTS_DIR / "myorg-sample-app"
    assert seen["token"] == "ghp_tok"
    assert "ghp_tok" not in res.text


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


def test_github_cli_token_endpoint_is_gone_and_auth_status_has_no_token(monkeypatch):
    from morph import github

    assert client.post("/projects/github/cli-token").status_code in (404, 405)

    monkeypatch.setattr(github, "_gh_cli_token", lambda: "gho_live_token_value")
    res = client.get("/projects/github/auth-status")
    assert res.status_code == 200
    assert res.json() == {"authenticated": True, "source": "gh cli"}
    assert "gho_live_token_value" not in res.text


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
            assert token == "gho_access_token_123"
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


def test_github_repos_resolves_token_server_side(monkeypatch):
    from morph import github
    from morph.api.routes import projects

    monkeypatch.setattr(projects, "_github_http_json", lambda url, method="GET", payload=None, token=None: [])
    monkeypatch.setattr(github, "_gh_cli_token", lambda: None)
    for var in ("MORPH_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert client.post("/projects/github/repos", json={}).status_code == 401

    monkeypatch.setenv("MORPH_GITHUB_TOKEN", "ghp_from_env")
    assert client.post("/projects/github/repos", json={}).status_code == 200


# --- registry -------------------------------------------------------------- #


def test_projects_registry_endpoints(tmp_path):
    proj_dir = tmp_path / "regproj"
    proj_dir.mkdir()
    (proj_dir / "main.py").write_text("print('x')\n")

    created = client.post("/projects/local", json={"path": str(proj_dir)})
    assert created.status_code == 200
    pid = created.json()["project_id"]

    listing = client.get("/projects")
    assert listing.status_code == 200
    assert any(p["project_id"] == pid for p in listing.json())

    one = client.get(f"/projects/{pid}")
    assert one.status_code == 200
    assert one.json()["name"] == "regproj"
    assert one.json()["suggested_command"] == "python3 main.py"

    updated = client.put(f"/projects/{pid}", json={"command": "python3 other.py"})
    assert updated.status_code == 200
    assert updated.json()["suggested_command"] == "python3 other.py"
    assert client.get(f"/projects/{pid}").json()["suggested_command"] == "python3 other.py"

    assert client.delete(f"/projects/{pid}").json() == {"deleted": True}
    assert client.get(f"/projects/{pid}").status_code == 404
    assert client.delete(f"/projects/{pid}").status_code == 404


def test_project_ids_are_validated():
    # An encoded slash never reaches the handler (no single-segment match);
    # anything that does reach it must satisfy the id pattern.
    assert client.get("/projects/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get("/projects/has%20space").status_code == 422
    assert client.get("/projects/bad%24id").status_code == 422
    assert client.delete("/projects/" + "x" * 65).status_code == 422
    assert client.post("/projects/bad%24id/install").status_code == 422


def test_nothing_written_outside_temp_home(tmp_path, _temp_home):
    """Guard for the guard: the registry the routes write to is under tmp_path."""
    import morph.projects as registry

    assert str(registry.REGISTRY_DIR).startswith(str(tmp_path))
    assert str(Path.home()).startswith(str(tmp_path))


def test_device_flow_without_client_id_explains_how_to_configure(monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    from morph.api.routes import projects as routes
    from morph.schema.config import MorphConfig

    monkeypatch.setattr("morph.config.load_config", lambda *a, **k: MorphConfig())
    monkeypatch.setattr(routes.gh, "DEFAULT_CLIENT_ID", "")
    r = client.post("/projects/github/device-code", json={})
    assert r.status_code == 400
    assert "github.client_id" in r.json()["detail"]
    assert "GITHUB_CLIENT_ID" in r.json()["detail"]


def test_device_flow_reads_client_id_from_morph_yaml(monkeypatch):
    monkeypatch.delenv("GITHUB_CLIENT_ID", raising=False)
    from morph.api.routes import projects as routes
    from morph.schema.config import MorphConfig

    cfg = MorphConfig()
    cfg.github.client_id = "Iv1.fromyaml"
    monkeypatch.setattr("morph.config.load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(routes.gh, "DEFAULT_CLIENT_ID", "")
    seen = {}

    def fake_http(url, *, method, payload):
        seen.update(url=url, payload=payload)
        return {"device_code": "d", "user_code": "ABCD-1234", "verification_uri": "https://github.com/login/device",
                "expires_in": 900, "interval": 5}

    monkeypatch.setattr(routes, "_github_http_json", fake_http)
    r = client.post("/projects/github/device-code", json={})
    assert r.status_code == 200
    assert seen["payload"]["client_id"] == "Iv1.fromyaml"
    assert r.json()["user_code"] == "ABCD-1234"
