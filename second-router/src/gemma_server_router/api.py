from __future__ import annotations

from contextlib import asynccontextmanager
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .adapter import ServerProcessAdapter, build_process_adapter
from .config import ServerRouterSettings
from .downstream import FinalScoreHttpClient, LegacyRagHttpClient, ServerAnswerHttpClient
from .models import (
    ServerProcessCompactResult,
    ServerProcessResult,
    ServerRouterCompactResult,
    ServerRouterFromFirstRouterInput,
    ServerRouterInput,
    ServerRouterResult,
)
from .service import ServerRouterService, build_server_router_service


class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


def create_app(service: ServerRouterService | None = None) -> FastAPI:
    if service is None:
        settings = ServerRouterSettings()
        router_service = build_server_router_service(settings)
    else:
        router_service = service
        settings = router_service.settings

    process_adapter = build_process_adapter(
        settings=settings,
        router_service=router_service,
        rag_client=LegacyRagHttpClient(settings),
        server_answer_client=ServerAnswerHttpClient(settings),
        final_score_client=FinalScoreHttpClient(settings),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.router_service = router_service
        app.state.process_adapter = process_adapter
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

    @app.post(
        "/route/from-first-router",
        response_model=ServerRouterCompactResult,
        response_class=PrettyJSONResponse,
    )
    async def route_from_first_router(
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerRouterCompactResult:
        result = await app.state.router_service.route_from_first_router(request)
        return ServerRouterCompactResult(display=result.display, handoff=result.handoff)

    @app.post("/route/debug", response_model=ServerRouterResult, response_class=PrettyJSONResponse)
    async def route_debug(request: ServerRouterInput) -> ServerRouterResult:
        return await app.state.router_service.route(request)

    @app.post(
        "/route/from-first-router/debug",
        response_model=ServerRouterResult,
        response_class=PrettyJSONResponse,
    )
    async def route_from_first_router_debug(
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerRouterResult:
        return await app.state.router_service.route_from_first_router(request)

    @app.post(
        "/process/from-first-router",
        response_model=ServerProcessCompactResult,
        response_class=PrettyJSONResponse,
    )
    async def process_from_first_router(
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerProcessCompactResult:
        result = await app.state.process_adapter.process_from_first_router(request)
        return ServerProcessCompactResult(
            request_id=result.request_id,
            original_question=result.original_question,
            second_route=result.routing.display,
            execution=result.execution,
            final_score=result.final_score,
            final_answer=result.final_answer,
        )

    @app.post(
        "/process/from-first-router/debug",
        response_model=ServerProcessResult,
        response_class=PrettyJSONResponse,
    )
    async def process_from_first_router_debug(
        request: ServerRouterFromFirstRouterInput,
    ) -> ServerProcessResult:
        return await app.state.process_adapter.process_from_first_router(request)

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
