from __future__ import annotations

import argparse
import asyncio
import json

from .models import RouterInput
from .service import build_router_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Route a request through the Gemma router.")
    parser.add_argument("--message", required=True, help="User message to route.")
    parser.add_argument(
        "--network-status",
        choices=["online", "degraded", "offline"],
        default="online",
        help="Current network state for the device.",
    )
    parser.add_argument(
        "--has-image",
        action="store_true",
        help="Mark the request as having an attached image or screenshot.",
    )
    args = parser.parse_args()

    request = RouterInput(
        user_message=args.message,
        network_status=args.network_status,  # type: ignore[arg-type]
        has_image=args.has_image,
    )

    decision = asyncio.run(_route(request))
    print(json.dumps(decision.model_dump(), indent=2, ensure_ascii=False))


async def _route(request: RouterInput) -> object:
    service = build_router_service()
    return await service.route(request)
