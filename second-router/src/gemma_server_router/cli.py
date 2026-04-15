from __future__ import annotations

import argparse
import asyncio
import json

from .models import ServerRouterInput
from .service import build_server_router_service


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Route a server-side request to either RAG or the general server LLM."
    )
    parser.add_argument("--message", required=True, help="User message to classify.")
    args = parser.parse_args()

    request = ServerRouterInput(user_message=args.message)
    result = asyncio.run(_route(request))
    print(json.dumps(result.model_dump(), indent=2, ensure_ascii=False))


async def _route(request: ServerRouterInput) -> object:
    service = build_server_router_service()
    return await service.route(request)
