"""Project registry, GitHub helpers, isolated-env prep, and `connect()`."""

from __future__ import annotations

from pathlib import Path

import pytest

from morph import github, project_setup, projects, runenv
from morph.projects import Project

# --------------------------------------------------------------------------- #
# github helpers
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("octocat/Hello-World", ("octocat", "Hello-World")),
        ("https://github.com/pallets/click", ("pallets", "click")),
        ("https://github.com/pallets/click.git", ("pallets", "click")),
        ("github.com/a/b", ("a", "b")),
        ("git@github.com:x/y.git", ("x", "y")),
    ],
)
def test_normalize_repo(raw, expected):
    assert github.normalize_repo(raw) == expected


@pytest.mark.parametrize("bad", ["", "just-a-word", "a/b/c", "-rf /", "https://gitlab.com/a/b"])
def test_normalize_repo_rejects(bad):
    with pytest.raises(github.GitHubError):
        github.normalize_repo(bad)


def test_resolve_token_precedence(monkeypatch):
    for var in ("MORPH_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(github, "_gh_cli_token", lambda: "gh-cli-tok")

    assert github.resolve_token("explicit") == "explicit"
    monkeypatch.setenv("GH_TOKEN", "env-gh")
    assert github.resolve_token() == "env-gh"
    monkeypatch.setenv("GITHUB_TOKEN", "env-github")
    assert github.resolve_token() == "env-github"
    monkeypatch.setenv("MORPH_GITHUB_TOKEN", "env-morph")
    assert github.resolve_token() == "env-morph"

    for var in ("MORPH_GITHUB_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"):
        monkeypatch.delenv(var, raising=False)
    assert github.resolve_token() == "gh-cli-tok"
    assert github.token_source() == "gh cli"


# --------------------------------------------------------------------------- #
# registry
# --------------------------------------------------------------------------- #

def test_registry_roundtrip(tmp_path):
    a = Project(name="alpha", path="/tmp/alpha", command="python3 main.py")
    b = Project(name="beta", path="/tmp/beta")
    projects.save(a, base=tmp_path)
    projects.save(b, base=tmp_path)

    names = {p.name for p in projects.list_projects(base=tmp_path)}
    assert names == {"alpha", "beta"}
    assert projects.load(a.id, base=tmp_path).command == "python3 main.py"
    assert projects.load("beta", base=tmp_path).id == b.id  # by name

    assert projects.delete("alpha", base=tmp_path) is True
    assert projects.delete("nope", base=tmp_path) is False
    assert {p.name for p in projects.list_projects(base=tmp_path)} == {"beta"}


# --------------------------------------------------------------------------- #
# detection + isolated env
# --------------------------------------------------------------------------- #

def test_detect_command_single_script(tmp_path):
    (tmp_path / "solver.py").write_text("print('hi')\n")
    cmd, cwd = project_setup.detect_command(tmp_path)
    assert cmd == "python3 solver.py"
    assert cwd == str(tmp_path)


def test_detect_command_pytest_layout(tmp_path):
    (tmp_path / "tests").mkdir()
    cmd, _ = project_setup.detect_command(tmp_path)
    # scoped: one tests dir, stop at first failure, ignore project addopts
    assert cmd.startswith("python3 -m pytest")
    assert "-x" in cmd and "-o addopts=" in cmd and cmd.endswith(" tests")


def test_detect_command_prefers_entrypoint_over_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "app.py").write_text("print('run me')\n")
    cmd, _ = project_setup.detect_command(tmp_path)
    assert cmd == "python3 app.py"


def test_detect_command_uses_pyproject_console_script(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n[project.scripts]\nmytool = "x:main"\n'
    )
    cmd, _ = project_setup.detect_command(tmp_path)
    assert cmd == "mytool --help"


def test_detect_command_none_when_unrecognised(tmp_path):
    (tmp_path / "a.py").write_text("")
    (tmp_path / "b.py").write_text("")
    assert project_setup.detect_command(tmp_path) == (None, None)


def test_command_in_env_rewrites_python(tmp_path):
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python").write_text("")
    (venv / "bin" / "python").chmod(0o755)

    out = runenv.command_in_env("python3 main.py --x 1", venv)
    assert out.startswith(f'"{venv / "bin" / "python"}" main.py --x 1')
    assert runenv.command_in_env("npm test", venv) == "npm test"
    assert runenv.command_in_env("python3 main.py", None) == "python3 main.py"


# --------------------------------------------------------------------------- #
# connect() on a local directory (no network)
# --------------------------------------------------------------------------- #

def test_connect_local_directory(tmp_path):
    proj_dir = tmp_path / "myproj"
    proj_dir.mkdir()
    (proj_dir / "main.py").write_text("print('ok')\n")

    registry = tmp_path / "registry"
    project = project_setup.connect(str(proj_dir), base=registry)

    assert project.source == "local"
    assert project.name == "myproj"
    assert project.command == "python3 main.py"
    assert Path(project.path) == proj_dir
    assert projects.load(project.id, base=registry).command == "python3 main.py"


def test_connect_rejects_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        project_setup.connect(str(tmp_path / "does-not-exist"), base=tmp_path)


def test_command_in_env_rewrites_console_script(tmp_path):
    venv = tmp_path / "venv"
    bindir = venv / ("Scripts" if __import__("sys").platform == "win32" else "bin")
    bindir.mkdir(parents=True)
    (bindir / "python").write_text("")
    (bindir / "mytool").write_text("")

    out = runenv.command_in_env("mytool --help", venv)
    assert out == f'"{bindir / "mytool"}" --help'
    # pytest -> module form under the venv python
    assert runenv.command_in_env("pytest -q tests", venv).startswith(f'"{bindir / "python"}" -m pytest')
    # an unknown bare command is left alone
    assert runenv.command_in_env("make run", venv) == "make run"
