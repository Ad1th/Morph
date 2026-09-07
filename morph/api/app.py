"""FastAPI application factory for the Morph backend server.

Security posture (this server executes commands on the developer's machine):

* CORS allows only the dashboard's dev origins (``http://localhost:5173``,
  ``http://127.0.0.1:5173``) plus the origin of the port the server itself is
  bound to, never ``*``, and never with credentials. A hostile page open in the
  same browser therefore cannot call ``/run``.
* ``TrustedHostMiddleware`` pins the ``Host`` header to loopback names so DNS
  rebinding cannot bypass the origin list.
* ``morph serve`` binds ``127.0.0.1``; ``--host`` is an explicit opt-in.

Every router is mounted twice: at ``/api/v1`` (the versioned contract) and at
the root (the paths the GUI and TUI already use).
"""

from __future__ import annotations

import logging
import os
import platform
from collections.abc import Iterable
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

import morph
from morph.api import defaults
from morph.api.routes import (
    experiments,
    minimize,
    parameters,
    profiles,
    projects,
    regressions,
    runs,
    surface,
    threshold,
    ws,
)
from morph.api.routes import (
    platform as platform_routes,
)

logger = logging.getLogger("morph.api")

API_PREFIX = "/api/v1"

#: Host header values always accepted (loopback names, and Starlette's TestClient).
LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "testserver")

OPENAPI_TAGS = [
    {"name": "meta", "description": "Liveness and version."},
    {"name": "profiles", "description": "Capture, save, load and reconcile environment profiles."},
    {"name": "parameters", "description": "Parameter metadata the UI renders its controls from."},
    {"name": "runs", "description": "Run a command once under a profile."},
    {
        "name": "experiments",
        "description": "Causal isolation experiments: sequential (e-value, early stopping) or batch "
        "(Fisher). Stream progress over `/ws/experiment/{id}`.",
    },
    {
        "name": "threshold",
        "description": "Locate the value of one parameter at which failures begin "
        "(probabilistic bisection by default). Stream over `/ws/threshold/{id}`.",
    },
    {
        "name": "minimize",
        "description": "Minimal failing condition set: delta debugging over the target's deviations.",
    },
    {"name": "regressions", "description": "Flight-recorder bundles: save, replay, delete."},
    {"name": "projects", "description": "Connect a local directory, upload, or GitHub repo to run."},
    {"name": "platform", "description": "Host OS, adapter capabilities and available run targets."},
    {"name": "surface", "description": "2D failure surface, differential blame, invariant export."},
    {"name": "websocket", "description": "Progress streams for experiments and threshold searches."},
]


def _serve_origins(port: int | None) -> list[str]:
    origins = list(defaults.DEV_ORIGINS)
    if port is not None:
        origins += [f"http://localhost:{port}", f"http://127.0.0.1:{port}"]
    return origins


def _env_list(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app(
    *,
    origins: Iterable[str] | None = None,
    port: int | None = None,
    allowed_hosts: Iterable[str] | None = None,
) -> FastAPI:
    """Create and configure the FastAPI application instance.

    ``origins`` adds browser origins to the CORS allow-list; ``port`` adds the
    server's own origin (for a bundled dashboard served from it);
    ``allowed_hosts`` extends the Host allow-list when ``--host`` is not
    loopback. ``morph serve`` passes these through the environment
    (``MORPH_SERVE_PORT``, ``MORPH_EXTRA_ORIGINS``, ``MORPH_ALLOWED_HOSTS``)
    because uvicorn imports the module-level ``app``.
    """
    from morph.envfile import load_env_file

    load_env_file()  # tokens / origins from the nearest .env, before os.environ is read below
    if port is None and os.environ.get("MORPH_SERVE_PORT", "").isdigit():
        port = int(os.environ["MORPH_SERVE_PORT"])
    origins = [*(origins or []), *_env_list("MORPH_EXTRA_ORIGINS")]
    allowed_hosts = [*(allowed_hosts or []), *_env_list("MORPH_ALLOWED_HOSTS")]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        # Capture the server loop once so worker threads can post progress.
        ws.manager.bind_loop()
        try:
            yield
        finally:
            # Ctrl-C must not leave tc/dnctl shaping applied: stop every
            # running experiment and clean up any adapter still mid-trial.
            experiments.jobs.shutdown()

    app = FastAPI(
        title="Morph API Server",
        version=morph.__version__,
        description=(
            "Local environment reproduction and causal experiment API. "
            "Every route is available under `/api/v1` and, for existing clients, at the root."
        ),
        openapi_tags=OPENAPI_TAGS,
        lifespan=lifespan,
    )

    allow_origins = list(dict.fromkeys([*_serve_origins(port), *(origins or [])]))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Accept"],
    )
    hosts = list(dict.fromkeys([*LOOPBACK_HOSTS, *(allowed_hosts or [])]))
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=hosts)
    app.state.allow_origins = allow_origins
    app.state.allowed_hosts = hosts

    @app.get("/health", tags=["meta"], summary="Liveness probe")
    async def health_check() -> dict:
        """Cheap, non-blocking: safe to poll while long experiments occupy the thread pool."""
        return {
            "status": "ok",
            "service": "morph-api",
            "version": morph.__version__,
            "running_jobs": len(experiments.jobs.running()),
        }

    @app.get("/version", tags=["meta"], summary="Morph and runtime versions")
    async def version() -> dict:
        return {
            "morph": morph.__version__,
            "python": platform.python_version(),
            "platform": platform.system().lower(),
            "api": "v1",
        }

    def mount(prefix: str) -> None:
        app.include_router(profiles.router, prefix=f"{prefix}/profiles", tags=["profiles"])
        app.include_router(parameters.router, prefix=f"{prefix}/parameters", tags=["parameters"])
        app.include_router(runs.router, prefix=f"{prefix}/run", tags=["runs"])
        app.include_router(experiments.router, prefix=f"{prefix}/experiments", tags=["experiments"])
        app.include_router(regressions.router, prefix=f"{prefix}/regressions", tags=["regressions"])
        app.include_router(projects.router, prefix=f"{prefix}/projects", tags=["projects"])
        app.include_router(platform_routes.router, prefix=f"{prefix}/platform", tags=["platform"])
        app.include_router(threshold.router, prefix=f"{prefix}/threshold", tags=["threshold"])
        app.include_router(minimize.router, prefix=f"{prefix}/minimize", tags=["minimize"])
        app.include_router(surface.router, prefix=prefix, tags=["surface"])
        app.include_router(ws.router, prefix=f"{prefix}/ws", tags=["websocket"])

    mount("")
    mount(API_PREFIX)
    app.add_api_route(f"{API_PREFIX}/health", health_check, methods=["GET"], tags=["meta"],
                      summary="Liveness probe", include_in_schema=False)
    app.add_api_route(f"{API_PREFIX}/version", version, methods=["GET"], tags=["meta"],
                      summary="Morph and runtime versions", include_in_schema=False)
    _mount_dashboard(app)
    return app


def dashboard_dir() -> Path | None:
    """Where a built dashboard lives, if one does: ``MORPH_DASHBOARD_DIR`` or
    ``frontend/dist`` next to the package. ``None`` when nothing is built."""
    explicit = os.environ.get("MORPH_DASHBOARD_DIR")
    candidates = [Path(explicit).expanduser()] if explicit else []
    candidates.append(Path(__file__).resolve().parents[2] / "frontend" / "dist")
    for directory in candidates:
        if (directory / "index.html").is_file():
            return directory
    return None


def _mount_dashboard(app: FastAPI) -> None:
    """Serve the built React dashboard from the same origin as the API.

    One process, one port, no CORS: ``morph serve`` after ``npm run build``
    is a complete deployment. Every path that is not an API route or a real
    file returns ``index.html`` so the dashboard's client-side routes
    (``/app/experiment`` ...) survive a reload. Registered last, so API
    routes always win.
    """
    directory = dashboard_dir()
    if directory is None:
        return
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=directory / "assets"), name="dashboard-assets")
    index = directory / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    async def dashboard(path: str, request: Request) -> FileResponse:
        candidate = (directory / path).resolve()
        if path and candidate.is_file() and directory in candidate.parents:
            return FileResponse(candidate)
        # Only a browser navigation gets the SPA shell; an API client asking for
        # JSON at an unknown path still gets a 404 (and the TestClient does too).
        if "text/html" not in request.headers.get("accept", ""):
            raise HTTPException(status_code=404, detail="Not found")
        return FileResponse(index)


app = create_app()
