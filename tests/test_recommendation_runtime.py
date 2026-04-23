from __future__ import annotations

import asyncio

import httpx

import app_recommend


def test_recommend_endpoint_returns_empty_when_only_non_recommendable_valid_ids(monkeypatch) -> None:
    class StubEngine:
        def recommend(self, payload: dict) -> dict:
            assert payload["ingredientIds"] == ["ingredient-2"]
            return {
                "recommendations": [],
                "totalCount": 0,
                "inputIngredientCount": 1,
            }

    monkeypatch.setattr(
        app_recommend,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
            "ingredient-2": {"ingredientId": "ingredient-2", "ingredientName": "맥주"},
        },
    )
    monkeypatch.setattr(app_recommend, "_get_vector_recommend_engine", lambda: StubEngine())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/recommend", json={"ingredientIds": ["ingredient-2"]})

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["recommendations"] == []
    assert payload["totalCount"] == 0
    assert payload["inputIngredientCount"] == 1


def test_recommend_endpoint_keeps_400_for_only_invalid_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        app_recommend,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
        },
    )

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/recommend", json={"ingredientIds": ["ingredient-x"]})

    response = asyncio.run(_request())

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_REQUEST"


def test_recommend_endpoint_accepts_personalization_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        app_recommend,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
            "ingredient-2": {"ingredientId": "ingredient-2", "ingredientName": "감자"},
            "ingredient-3": {"ingredientId": "ingredient-3", "ingredientName": "땅콩"},
        },
    )

    captured: dict[str, object] = {}

    class StubEngine:
        def recommend(self, payload: dict) -> dict:
            captured.update(payload)
            return {"recommendations": [], "totalCount": 0, "inputIngredientCount": 1}

    monkeypatch.setattr(app_recommend, "_get_vector_recommend_engine", lambda: StubEngine())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/recommend",
                json={
                    "ingredientIds": ["ingredient-1"],
                    "preferredIngredientIds": ["ingredient-2"],
                    "allergyIngredientIds": ["ingredient-3"],
                    "preferredCategories": ["국"],
                    "excludedCategories": ["안주"],
                    "preferredKeywords": ["감자"],
                    "excludedKeywords": ["매운"],
                },
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    assert captured == {
        "ingredientIds": ["ingredient-1"],
        "topK": 10,
        "minCoverageRatio": 0.5,
        "preferredIngredientIds": ["ingredient-2"],
        "dislikedIngredientIds": [],
        "allergyIngredientIds": ["ingredient-3"],
        "preferredCategories": ["국"],
        "excludedCategories": ["안주"],
        "preferredKeywords": ["감자"],
        "excludedKeywords": ["매운"],
    }
