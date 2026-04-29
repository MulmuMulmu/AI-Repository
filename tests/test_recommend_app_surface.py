from __future__ import annotations

import asyncio

import httpx

import app_recommend


def test_ingredient_recommondation_scores_backend_candidates() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/recommondation",
                json={
                    "userIngredient": {
                        "ingredients": ["김치", "양파"],
                        "preferIngredients": ["소고기"],
                        "dispreferIngredients": ["오이"],
                        "IngredientRatio": 0.5,
                    },
                    "candidates": [
                        {
                            "recipe_id": "recipe-kimchi-stew",
                            "title": "돼지고기 김치찌개",
                            "ingredients": ["김치", "돼지고기", "두부", "대파", "고춧가루"],
                        },
                        {
                            "recipe_id": "recipe-kimchi-rice",
                            "title": "김치볶음밥",
                            "ingredients": ["김치", "밥", "스팸", "양파"],
                        },
                        {
                            "recipe_id": "recipe-cucumber",
                            "title": "오이 김치무침",
                            "ingredients": ["오이", "김치"],
                        },
                    ],
                },
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    recommendations = payload["data"]["recommendations"]
    assert [item["recipeId"] for item in recommendations] == ["recipe-kimchi-rice"]
    assert recommendations[0]["title"] == "김치볶음밥"
    assert recommendations[0]["score"] > 0
    assert recommendations[0]["match_details"] == {
        "matched": ["김치", "양파"],
        "missing": ["밥", "스팸"],
    }


def test_ingredient_recommondation_returns_ai500_on_unexpected_error(monkeypatch) -> None:
    def _raise_error(payload: dict) -> dict:
        raise RuntimeError("boom")

    monkeypatch.setattr(app_recommend, "_recommend_backend_candidates", _raise_error)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app_recommend.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/recommondation",
                json={
                    "userIngredient": {"ingredients": ["김치"], "IngredientRatio": 0.5},
                    "candidates": [
                        {
                            "recipe_id": "recipe-kimchi",
                            "title": "김치찌개",
                            "ingredients": ["김치", "두부"],
                        }
                    ],
                },
            )

    response = asyncio.run(_request())

    assert response.status_code == 500
    assert response.json() == {
        "success": False,
        "code": "AI500",
        "result": "레시피를 추천할 수 없습니다.",
    }
