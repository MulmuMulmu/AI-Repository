from __future__ import annotations

import asyncio

import httpx

import app_recommend


def test_recommend_app_exposes_recommend_endpoint(monkeypatch) -> None:
    class StubEngine:
        def recommend(self, payload: dict) -> dict:
            assert payload["ingredientIds"] == ["ingredient-1"]
            return {
                "recommendations": [
                    {
                        "recipeId": "recipe-1",
                        "score": 0.91,
                        "coverageRatio": 1.0,
                        "matchedIngredients": [{"ingredientId": "ingredient-1", "ingredientName": "양파"}],
                        "missingIngredients": [],
                        "totalIngredientCount": 1,
                    }
                ],
                "totalCount": 1,
            }

    monkeypatch.setattr(
        app_recommend,
        "INGREDIENTS",
        {"ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"}},
    )
    monkeypatch.setattr(app_recommend, "_get_vector_recommend_engine", lambda: StubEngine())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/recommend", json={"ingredientIds": ["ingredient-1"]})

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["recommendations"][0]["recipeId"] == "recipe-1"
    assert payload["recommendations"][0]["coverageRatio"] == 1.0
