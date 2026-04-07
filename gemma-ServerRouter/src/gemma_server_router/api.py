from __future__ import annotations

from contextlib import asynccontextmanager
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import ServerRouterSettings
from .models import ServerRouterCompactResult, ServerRouterInput, ServerRouterResult
from .service import ServerRouterService, build_server_router_service


class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


def create_app(service: ServerRouterService | None = None) -> FastAPI:
    router_service = service or build_server_router_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.router_service = router_service
        yield

    app = FastAPI(
        title="Gemma Server Router",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/route", response_model=ServerRouterCompactResult, response_class=PrettyJSONResponse)
    async def route(request: ServerRouterInput) -> ServerRouterCompactResult:
        result = await app.state.router_service.route(request)
        return ServerRouterCompactResult(display=result.display, handoff=result.handoff)

    @app.post("/route/debug", response_model=ServerRouterResult, response_class=PrettyJSONResponse)
    async def route_debug(request: ServerRouterInput) -> ServerRouterResult:
        return await app.state.router_service.route(request)

    return app


app = create_app()


def run() -> None:
    settings = ServerRouterSettings()
    uvicorn.run(
        "gemma_server_router.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
