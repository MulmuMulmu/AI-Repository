from __future__ import annotations

import asyncio

import httpx

import main


def test_ingredient_prediction_endpoint_returns_match_result(monkeypatch) -> None:
    def _stub_match(product_name: str) -> dict | None:
        if product_name == "국산콩 두부":
            return {
                "product_name": product_name,
                "ingredientId": "ingredient-1",
                "ingredientName": "두부",
                "category": "가공식품",
                "similarity": 0.92,
            }
        return None

    monkeypatch.setattr(main, "_match_product_to_ingredient", _stub_match)
    monkeypatch.setattr(main, "_find_suggestions", lambda product_name: ["두부", "순두부"])

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/prediction",
                json={"product_names": ["국산콩 두부", "알수없는상품"]},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["matched_count"] == 1
    assert data["unmatched_count"] == 1
    assert data["matched"][0]["ingredientName"] == "두부"
    assert data["matched"][0]["mapping_status"] == "MAPPED"
    assert data["matched"][0]["item_type"] == "INGREDIENT"
    assert data["unmatched"][0]["suggestions"] == ["두부", "순두부"]
    assert data["unmatched"][0]["mapping_status"] == "UNMAPPED"
    assert data["unmatched"][0]["item_type"] == "UNKNOWN"


def test_ingredient_prediction_endpoint_keeps_non_food_as_excluded(monkeypatch) -> None:
    monkeypatch.setattr(main, "_match_product_to_ingredient", lambda product_name: None)
    monkeypatch.setattr(main, "_find_suggestions", lambda product_name: [])

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/prediction",
                json={"product_names": ["구글홈미니"]},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["matched_count"] == 0
    assert payload["unmatched_count"] == 1
    assert payload["unmatched"][0]["mapping_status"] == "EXCLUDED"
    assert payload["unmatched"][0]["item_type"] == "NON_FOOD"


def test_legacy_api_routes_are_not_exposed() -> None:
    async def _request() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            ocr_response = await client.post("/api/ocr/receipt")
            match_response = await client.post("/api/ingredients/match", json={"product_names": []})
            health_response = await client.get("/api/health")
            return ocr_response, match_response, health_response

    ocr_response, match_response, health_response = asyncio.run(_request())

    assert ocr_response.status_code == 404
    assert match_response.status_code == 404
    assert health_response.status_code == 404
