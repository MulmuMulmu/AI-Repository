from __future__ import annotations

import asyncio

import httpx

import main


def test_build_recommendable_ingredient_ids_uses_recipe_graph() -> None:
    result = main._build_recommendable_ingredient_ids(
        [
            {"recipeId": "r1", "ingredientId": "i1"},
            {"recipeId": "r1", "ingredientId": "i2"},
            {"recipeId": "r2", "ingredientId": "i1"},
            {"recipeId": "r3", "ingredientId": "i3"},
        ]
    )

    assert result == {"i1", "i2", "i3"}


def test_recommend_recipes_uses_recommender_and_downmaps_response(monkeypatch) -> None:
    class StubRecommender:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def recommend(
            self,
            ingredient_ids: list[str],
            *,
            top_k: int,
            category: str | None,
            min_match_rate: float,
            preferred_ingredient_ids: list[str] | None = None,
            blocked_ingredient_ids: list[str] | None = None,
            preferred_categories: list[str] | None = None,
            excluded_categories: list[str] | None = None,
            preferred_keywords: list[str] | None = None,
            excluded_keywords: list[str] | None = None,
            diversity: bool = True,
            **_: object,
        ) -> list[dict]:
            self.calls.append(
                {
                    "ingredient_ids": list(ingredient_ids),
                    "top_k": top_k,
                    "category": category,
                    "min_match_rate": min_match_rate,
                    "preferred_ingredient_ids": preferred_ingredient_ids,
                    "blocked_ingredient_ids": blocked_ingredient_ids,
                    "preferred_categories": preferred_categories,
                    "excluded_categories": excluded_categories,
                    "preferred_keywords": preferred_keywords,
                    "excluded_keywords": excluded_keywords,
                    "diversity": diversity,
                }
            )
            return [
                {
                    "recipeId": "recipe-1",
                    "name": "양파볶음",
                    "category": "반찬",
                    "imageUrl": "",
                    "matchedIngredients": [
                        {"ingredientId": "ingredient-1", "ingredientName": "양파", "category": "채소/과일"},
                    ],
                    "missingIngredients": [
                        {"ingredientId": "ingredient-2", "ingredientName": "고추장", "category": "소스/조미료/오일"},
                    ],
                    "matchRate": 0.5,
                    "totalIngredientCount": 2,
                    "score": 0.9321,
                    "weightedMatchRate": 0.8123,
                    "coreCoverage": 1.0,
                    "substitutions": [],
                }
            ]

    stub = StubRecommender()
    monkeypatch.setattr(main, "RECOMMENDABLE_INGREDIENT_IDS", {"ingredient-1"})
    monkeypatch.setattr(
        main,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
            "ingredient-2": {"ingredientId": "ingredient-2", "ingredientName": "맥주"},
            "ingredient-3": {"ingredientId": "ingredient-3", "ingredientName": "감자"},
            "ingredient-4": {"ingredientId": "ingredient-4", "ingredientName": "땅콩"},
        },
    )
    monkeypatch.setattr(main, "_get_recipe_recommender", lambda: stub)

    recommendations = main.recommend_recipes(
        ingredient_ids=["ingredient-1", "ingredient-2"],
        top_k=3,
        category="반찬",
        min_match_rate=0.4,
        preferred_ingredient_ids=["ingredient-3", "ingredient-x"],
        blocked_ingredient_ids=["ingredient-4", "ingredient-y"],
        preferred_categories=["국", "찌개"],
        excluded_categories=["안주"],
        preferred_keywords=["감자", "수프"],
        excluded_keywords=["매운"],
    )

    assert stub.calls == [
        {
            "ingredient_ids": ["ingredient-1"],
            "top_k": 3,
            "category": "반찬",
            "min_match_rate": 0.4,
            "preferred_ingredient_ids": ["ingredient-3"],
            "blocked_ingredient_ids": ["ingredient-4"],
            "preferred_categories": ["국", "찌개"],
            "excluded_categories": ["안주"],
            "preferred_keywords": ["감자", "수프"],
            "excluded_keywords": ["매운"],
            "diversity": True,
        }
    ]
    assert recommendations == [
        {
            "recipeId": "recipe-1",
            "name": "양파볶음",
            "category": "반찬",
            "imageUrl": "",
            "matchedIngredients": [{"ingredientId": "ingredient-1", "ingredientName": "양파"}],
            "missingIngredients": [{"ingredientId": "ingredient-2", "ingredientName": "고추장"}],
            "matchRate": 0.5,
            "totalIngredientCount": 2,
        }
    ]


def test_recommend_recipes_returns_empty_for_only_non_recommendable_valid_ids(monkeypatch) -> None:
    class StubRecommender:
        def recommend(self, *args: object, **kwargs: object) -> list[dict]:
            raise AssertionError("recommender should not be called when no recommendable ingredient ids remain")

    monkeypatch.setattr(main, "RECOMMENDABLE_INGREDIENT_IDS", {"ingredient-1"})
    monkeypatch.setattr(main, "_get_recipe_recommender", lambda: StubRecommender())

    recommendations = main.recommend_recipes(
        ingredient_ids=["ingredient-2"],
        top_k=5,
        category=None,
        min_match_rate=0.0,
    )

    assert recommendations == []


def test_recommend_endpoint_returns_empty_when_only_non_recommendable_valid_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
            "ingredient-2": {"ingredientId": "ingredient-2", "ingredientName": "맥주"},
        },
    )
    monkeypatch.setattr(main, "RECOMMENDABLE_INGREDIENT_IDS", {"ingredient-1"})

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/ai/recommend", json={"ingredientIds": ["ingredient-2"]})

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["recommendations"] == []
    assert payload["total_count"] == 0
    assert payload["input_ingredient_count"] == 1


def test_recommend_endpoint_keeps_400_for_only_invalid_ids(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
        },
    )

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/ai/recommend", json={"ingredientIds": ["ingredient-x"]})

    response = asyncio.run(_request())

    assert response.status_code == 400
    detail = response.json()["detail"]
    assert detail["code"] == "INVALID_REQUEST"


def test_recommend_endpoint_accepts_personalization_fields(monkeypatch) -> None:
    monkeypatch.setattr(
        main,
        "INGREDIENTS",
        {
            "ingredient-1": {"ingredientId": "ingredient-1", "ingredientName": "양파"},
            "ingredient-2": {"ingredientId": "ingredient-2", "ingredientName": "감자"},
            "ingredient-3": {"ingredientId": "ingredient-3", "ingredientName": "땅콩"},
        },
    )

    captured: dict[str, object] = {}

    def _recommend_recipes(**kwargs: object) -> list[dict]:
        captured.update(kwargs)
        return []

    monkeypatch.setattr(main, "recommend_recipes", _recommend_recipes)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/recommend",
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
        "ingredient_ids": ["ingredient-1"],
        "top_k": 10,
        "category": None,
        "min_match_rate": 0.0,
        "preferred_ingredient_ids": ["ingredient-2"],
        "blocked_ingredient_ids": ["ingredient-3"],
        "preferred_categories": ["국"],
        "excluded_categories": ["안주"],
        "preferred_keywords": ["감자"],
        "excluded_keywords": ["매운"],
    }
