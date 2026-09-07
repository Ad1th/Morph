"""FastAPI application factory for the Morph backend server."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from morph.api.routes import (
    experiments,
    parameters,
    platform,
    profiles,
    projects,
    regressions,
    runs,
    threshold,
    ws,
)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title="Morph API Server",
        version="0.1.0",
        description="Local environment reproduction and causal experiment API server",
    )

    # CORS configuration for Vite / React frontend (e.g. localhost:5173, localhost:3000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health_check():
        return {"status": "ok", "service": "morph-api"}

    app.include_router(profiles.router, prefix="/profiles", tags=["profiles"])
    app.include_router(parameters.router, prefix="/parameters", tags=["parameters"])
    app.include_router(runs.router, prefix="/run", tags=["runs"])
    app.include_router(experiments.router, prefix="/experiments", tags=["experiments"])
    app.include_router(regressions.router, prefix="/regressions", tags=["regressions"])
    app.include_router(projects.router, prefix="/projects", tags=["projects"])
    app.include_router(platform.router, prefix="/platform", tags=["platform"])
    app.include_router(threshold.router, prefix="/threshold", tags=["threshold"])
    app.include_router(ws.router, prefix="/ws", tags=["websocket"])

    return app


app = create_app()
