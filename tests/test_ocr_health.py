from __future__ import annotations

import asyncio

import httpx

import main


def test_health_endpoint_reports_prototype_ocr_capabilities() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/api/health")

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["status"] == "healthy"
    assert data["services"]["paddleocr"] == "available"
    assert data["services"]["preprocess"] == "available"
    assert data["services"]["bbox_contract"] == "enabled"
    assert "qwen_llm" in data["services"]
    assert data["services"]["database"] == "connected"
