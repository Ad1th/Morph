"""Security posture of the API server: CORS, Host pinning, id validation.

The server executes commands on the developer's machine, so a hostile web
page open in the same browser must not be able to talk to it.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from morph.api.app import LOOPBACK_HOSTS, app, create_app
from tests.test_api import make_test_profile

client = TestClient(app)


# --- CORS ------------------------------------------------------------------ #


def _preflight(origin: str, path: str = "/run") -> object:
    return client.options(
        path,
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )


def test_cors_allows_dashboard_dev_origins_without_credentials():
    for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
        res = _preflight(origin)
        assert res.status_code == 200, origin
        assert res.headers["access-control-allow-origin"] == origin
        assert "access-control-allow-credentials" not in res.headers


def test_cors_rejects_foreign_origin():
    res = _preflight("https://evil.example")
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers

    # A simple request from a foreign origin gets no CORS grant either.
    res = client.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in res.headers


def test_cors_never_echoes_wildcard():
    res = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert res.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert res.headers.get("access-control-allow-origin") != "*"


def test_serve_port_origin_is_added():
    served = TestClient(create_app(port=9123))
    res = served.options(
        "/run",
        headers={"Origin": "http://localhost:9123", "Access-Control-Request-Method": "POST"},
    )
    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == "http://localhost:9123"


# --- Host header (DNS rebinding) ------------------------------------------- #


def test_trusted_host_rejects_foreign_host_header():
    res = client.get("/health", headers={"Host": "evil.example"})
    assert res.status_code == 400
    for host in LOOPBACK_HOSTS:
        assert client.get("/health", headers={"Host": host}).status_code == 200
    assert client.get("/health", headers={"Host": "127.0.0.1:8000"}).status_code == 200


def test_serve_with_explicit_host_extends_allowlist():
    served = TestClient(create_app(allowed_hosts=["0.0.0.0", "*.lan"]))
    assert served.get("/health", headers={"Host": "box.lan"}).status_code == 200
    assert served.get("/health", headers={"Host": "evil.example"}).status_code == 400


# --- id validation ----------------------------------------------------------- #


def test_profile_id_traversal_is_rejected(tmp_path, monkeypatch):
    from morph.api.routes import profiles

    monkeypatch.setattr(profiles, "PROFILES_DIR", tmp_path / "profiles")
    profile = make_test_profile().model_dump()
    for bad in ("../../../tmp/evil", "/tmp/evil", "a/b", "..", "", "x" * 65, "sp ace"):
        res = client.post("/profiles", json={"id": bad, "profile": profile})
        assert res.status_code == 422, bad
    assert not (tmp_path / "tmp").exists()

    ok = client.post("/profiles", json={"id": "good_id-1.0", "profile": profile})
    assert ok.status_code == 200
    assert (tmp_path / "profiles" / "good_id-1.0.json").is_file()
    assert client.get("/profiles/good_id-1.0").status_code == 200
    assert client.get("/profiles/..%2F..%2Fpyproject").status_code in (404, 422)
    assert client.get("/profiles/bad%24id").status_code == 422
    assert client.get("/profiles/" + "x" * 65).status_code == 422
    assert client.delete("/profiles/good_id-1.0").status_code == 200
    assert client.get("/profiles/good_id-1.0").status_code == 404


def test_regression_id_traversal_is_rejected(tmp_path, monkeypatch):
    import morph.regression.artifact

    monkeypatch.setattr(morph.regression.artifact, "DEFAULT_REGRESSIONS_DIR", tmp_path / "regs")
    artifact = {
        "regression_id": str(tmp_path / "evil"),
        "environment": make_test_profile().model_dump(),
        "command": "echo hi",
    }
    res = client.post("/regressions", json=artifact)
    assert res.status_code == 422
    assert not (tmp_path / "evil").exists()

    assert client.get("/regressions/..%2F..%2Fetc").status_code in (404, 422)
    assert client.get("/regressions/bad%24id").status_code == 422
    assert client.post("/regressions/bad%20id/replay").status_code == 422
    assert client.delete("/regressions/" + "x" * 65).status_code == 422


def test_experiment_id_is_validated():
    assert client.get("/experiments/..%2F..%2Fx").status_code in (404, 422)
    assert client.get("/experiments/bad%24id").status_code == 422
    assert client.get("/experiments/exp-unknown").status_code == 404
    assert client.delete("/experiments/exp-unknown").status_code == 404


def test_run_target_and_execution_are_localhost_only_by_default():
    from morph.api import defaults

    assert defaults.SERVE_HOST == "127.0.0.1"
    assert "*" not in app.state.allow_origins
    assert all(h in ("127.0.0.1", "localhost", "testserver") for h in app.state.allowed_hosts)
