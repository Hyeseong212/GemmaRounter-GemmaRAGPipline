from __future__ import annotations

from contextlib import asynccontextmanager
import json

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from .config import FinalScoreSettings
from .models import FinalScoreCompactResult, FinalScoreInput, FinalScoreResult
from .service import FinalScoreService, build_final_score_service


class PrettyJSONResponse(JSONResponse):
    def render(self, content) -> bytes:
        return json.dumps(content, ensure_ascii=False, indent=2).encode("utf-8")


def create_app(service: FinalScoreService | None = None) -> FastAPI:
    score_service = service or build_final_score_service()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.score_service = score_service
        yield

    app = FastAPI(
        title="Final Score Gate",
        version="0.1.0",
        lifespan=lifespan,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/score", response_model=FinalScoreCompactResult, response_class=PrettyJSONResponse)
    async def score(request: FinalScoreInput) -> FinalScoreCompactResult:
        result = app.state.score_service.evaluate(request)
        return FinalScoreCompactResult(display=result.display, decision=result.decision)

    @app.post("/score/debug", response_model=FinalScoreResult, response_class=PrettyJSONResponse)
    async def score_debug(request: FinalScoreInput) -> FinalScoreResult:
        return app.state.score_service.evaluate(request)

    return app


app = create_app()


def run() -> None:
    settings = FinalScoreSettings()
    uvicorn.run(
        "final_score.api:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=False,
    )
