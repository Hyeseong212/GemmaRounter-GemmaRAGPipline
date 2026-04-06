from __future__ import annotations

from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI

from .config import RouterSettings
from .models import RouterInput, RouterResult
from .service import RouterService, build_router_service


def create_app(service: RouterService | None = None) -> FastAPI:
    router_service = service or build_router_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.router_service = router_service
        yield

    app = FastAPI(
        title="Gemma Router",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/route", response_model=RouterResult)
    async def route(request: RouterInput) -> RouterResult:
        return await app.state.router_service.route(request)

    return app


app = create_app()


def run() -> None:
    settings = RouterSettings()
    uvicorn.run(
        "gemma_routing.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
