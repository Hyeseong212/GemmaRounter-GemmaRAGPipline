from __future__ import annotations

from contextlib import asynccontextmanager
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import RouterSettings
from .models import (
    CompactHandoff,
    RouterCompactResult,
    RouterHandledResult,
    RouterInput,
    RouterResult,
)
from .service import RouterService, build_router_service


class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


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

    @app.post("/route", response_model=RouterCompactResult, response_class=PrettyJSONResponse)
    async def route(request: RouterInput) -> RouterCompactResult:
        result = await app.state.router_service.route(request)
        return _to_compact_result(result)

    @app.post("/handle", response_model=RouterHandledResult, response_class=PrettyJSONResponse)
    async def handle(request: RouterInput) -> RouterHandledResult:
        return await app.state.router_service.handle(request)

    @app.post("/route/debug", response_model=RouterResult, response_class=PrettyJSONResponse)
    async def route_debug(request: RouterInput) -> RouterResult:
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


def _to_compact_result(result: RouterResult) -> RouterCompactResult:
    handoff = result.handoff
    if handoff is None:
        raise ValueError("Router result is missing a downstream handoff")

    return RouterCompactResult(
        display=result.display,
        handoff=CompactHandoff(
            route=handoff.route,
            target_system=handoff.target_system,
            task_type=handoff.task_type,
            summary=handoff.summary,
            required_inputs=handoff.required_inputs,
            metadata=handoff.metadata,
        ),
    )
