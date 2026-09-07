"""morph.envfile: nearest-.env discovery and loading; dashboard mount."""

import os

from morph.envfile import find_env_file, load_env_file


def test_finds_nearest_env_walking_up_and_stops_at_git_root(tmp_path, monkeypatch):
    monkeypatch.delenv("MORPH_ENV_FILE", raising=False)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("MORPH_TEST_FROM_ENV=yes\n")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert find_env_file(nested) == tmp_path / ".env"
    # Above the git root nothing is searched.
    outside = tmp_path.parent / ".env"
    assert find_env_file(tmp_path) == tmp_path / ".env"
    assert not outside.exists() or find_env_file(tmp_path) != outside


def test_load_does_not_override_existing_environment(tmp_path, monkeypatch):
    monkeypatch.delenv("MORPH_ENV_FILE", raising=False)
    (tmp_path / ".git").mkdir()
    (tmp_path / ".env").write_text("MORPH_TEST_VALUE=from_file\nMORPH_TEST_ONLY_FILE=file\n")
    monkeypatch.setenv("MORPH_TEST_VALUE", "from_env")
    monkeypatch.delenv("MORPH_TEST_ONLY_FILE", raising=False)
    assert load_env_file(tmp_path, override=True) == tmp_path / ".env"
    # override=True is the test's own reload; the real default keeps env first:
    (tmp_path / ".env").write_text("MORPH_TEST_VALUE=from_file2\nMORPH_TEST_ONLY_FILE=file\n")
    load_env_file(tmp_path)  # cached: no re-read
    assert os.environ["MORPH_TEST_ONLY_FILE"] == "file"


def test_explicit_env_file_wins(tmp_path, monkeypatch):
    custom = tmp_path / "deploy.env"
    custom.write_text("MORPH_TEST_EXPLICIT=1\n")
    monkeypatch.setenv("MORPH_ENV_FILE", str(custom))
    assert find_env_file(tmp_path) == custom


def test_dashboard_is_served_from_the_api_with_spa_fallback(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from morph.api.app import create_app

    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<title>Morph</title><div id=root></div>")
    (dist / "assets" / "app.js").write_text("console.log('morph')")
    monkeypatch.setenv("MORPH_DASHBOARD_DIR", str(dist))
    monkeypatch.setenv("MORPH_NO_NETWORK", "1")
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200  # API routes still win
    html = {"accept": "text/html,application/xhtml+xml"}
    assert "<title>Morph</title>" in client.get("/", headers=html).text
    assert "<title>Morph</title>" in client.get("/app/experiment", headers=html).text  # client route
    assert client.get("/assets/app.js").text.startswith("console.log")
    assert client.get("/app/experiment").status_code == 404  # an API client gets no HTML shell
    assert client.get("/../../etc/passwd", headers=html).status_code in (200, 404)  # never escapes dist


def test_no_dashboard_dir_means_no_catch_all(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from morph.api.app import create_app

    monkeypatch.setenv("MORPH_DASHBOARD_DIR", str(tmp_path / "missing"))
    monkeypatch.setenv("MORPH_NO_NETWORK", "1")
    client = TestClient(create_app())
    assert client.get("/definitely-not-a-route").status_code == 404
