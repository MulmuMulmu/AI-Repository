from __future__ import annotations

import asyncio
from typing import Any

import httpx


def request_json(app: Any, method: str, path: str, **kwargs: Any) -> httpx.Response:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    return asyncio.run(_request())

