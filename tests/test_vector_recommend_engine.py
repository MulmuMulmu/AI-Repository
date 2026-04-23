from __future__ import annotations

from recommendation.vector_engine import VectorRecommendEngine


def _engine() -> VectorRecommendEngine:
    return VectorRecommendEngine(
        recipes={
            "r1": {"recipeId": "r1", "name": "양파볶음", "category": "반찬", "imageUrl": ""},
            "r2": {"recipeId": "r2", "name": "감자수프", "category": "국", "imageUrl": ""},
            "r3": {"recipeId": "r3", "name": "땅콩볶음", "category": "안주", "imageUrl": ""},
        },
        ingredients={
            "i1": {"ingredientId": "i1", "ingredientName": "양파", "category": "채소/과일"},
            "i2": {"ingredientId": "i2", "ingredientName": "고추장", "category": "소스/조미료/오일"},
            "i3": {"ingredientId": "i3", "ingredientName": "감자", "category": "채소/과일"},
            "i4": {"ingredientId": "i4", "ingredientName": "우유", "category": "유제품"},
            "i5": {"ingredientId": "i5", "ingredientName": "땅콩", "category": "기타"},
        },
        recipe_ingredients={
            "r1": [
                {"recipeId": "r1", "ingredientId": "i1"},
                {"recipeId": "r1", "ingredientId": "i2"},
            ],
            "r2": [
                {"recipeId": "r2", "ingredientId": "i3"},
                {"recipeId": "r2", "ingredientId": "i4"},
            ],
            "r3": [
                {"recipeId": "r3", "ingredientId": "i5"},
                {"recipeId": "r3", "ingredientId": "i1"},
            ],
        },
    )


def test_vector_engine_recommends_when_all_ingredients_are_owned() -> None:
    results = _engine().recommend({"ingredientIds": ["i1", "i2"]})

    assert results["recommendations"][0]["recipeId"] == "r1"
    assert results["recommendations"][0]["coverageRatio"] == 1.0


def test_vector_engine_recommends_when_half_or_more_ingredients_are_owned() -> None:
    results = _engine().recommend({"ingredientIds": ["i1"]})

    recipe_ids = [item["recipeId"] for item in results["recommendations"]]
    assert "r1" in recipe_ids


def test_vector_engine_excludes_when_coverage_is_below_threshold() -> None:
    results = _engine().recommend({"ingredientIds": ["i1"], "minCoverageRatio": 0.75})

    recipe_ids = [item["recipeId"] for item in results["recommendations"]]
    assert "r1" not in recipe_ids


def test_vector_engine_excludes_blocked_allergy_recipe() -> None:
    results = _engine().recommend({"ingredientIds": ["i1", "i5"], "allergyIngredientIds": ["i5"]})

    recipe_ids = [item["recipeId"] for item in results["recommendations"]]
    assert "r3" not in recipe_ids


def test_vector_engine_prioritizes_recipe_with_core_ingredient_match() -> None:
    engine = VectorRecommendEngine(
        recipes={
            "r1": {"recipeId": "r1", "name": "돼지고기볶음", "category": "반찬", "imageUrl": ""},
            "r2": {"recipeId": "r2", "name": "양파볶음", "category": "반찬", "imageUrl": ""},
        },
        ingredients={
            "i1": {"ingredientId": "i1", "ingredientName": "돼지고기", "category": "정육/계란"},
            "i2": {"ingredientId": "i2", "ingredientName": "양파", "category": "채소/과일"},
            "i3": {"ingredientId": "i3", "ingredientName": "간장", "category": "소스/조미료/오일"},
            "i4": {"ingredientId": "i4", "ingredientName": "대파", "category": "채소/과일"},
        },
        recipe_ingredients={
            "r1": [
                {"recipeId": "r1", "ingredientId": "i1", "amount": 300.0, "unit": "g"},
                {"recipeId": "r1", "ingredientId": "i2", "amount": 80.0, "unit": "g"},
                {"recipeId": "r1", "ingredientId": "i3", "amount": 1.0, "unit": "큰술"},
                {"recipeId": "r1", "ingredientId": "i4", "amount": 30.0, "unit": "g"},
            ],
            "r2": [
                {"recipeId": "r2", "ingredientId": "i2", "amount": 150.0, "unit": "g"},
                {"recipeId": "r2", "ingredientId": "i3", "amount": 1.0, "unit": "큰술"},
            ],
        },
    )

    results = engine.recommend({"ingredientIds": ["i2", "i3", "i4"]})

    assert [item["recipeId"] for item in results["recommendations"]] == ["r2", "r1"]
    assert results["recommendations"][1]["missingCoreIngredients"][0]["ingredientId"] == "i1"


def test_vector_engine_returns_weighted_coverage_debug_fields() -> None:
    engine = VectorRecommendEngine(
        recipes={
            "r1": {"recipeId": "r1", "name": "볶음밥", "category": "밥", "imageUrl": ""},
        },
        ingredients={
            "i1": {"ingredientId": "i1", "ingredientName": "쌀", "category": "쌀/면/빵"},
            "i2": {"ingredientId": "i2", "ingredientName": "참기름", "category": "소스/조미료/오일"},
            "i3": {"ingredientId": "i3", "ingredientName": "소금", "category": "소스/조미료/오일"},
        },
        recipe_ingredients={
            "r1": [
                {"recipeId": "r1", "ingredientId": "i1", "amount": 300.0, "unit": "g"},
                {"recipeId": "r1", "ingredientId": "i2", "amount": 5.0, "unit": "ml"},
                {"recipeId": "r1", "ingredientId": "i3", "amount": 1.0, "unit": "g"},
            ],
        },
    )

    results = engine.recommend({"ingredientIds": ["i1"], "minCoverageRatio": 0.3})

    recommendation = results["recommendations"][0]
    assert recommendation["coverageRatio"] == 0.3333
    assert recommendation["weightedCoverage"] > recommendation["coverageRatio"]
    assert recommendation["coreCoverage"] == 1.0
    assert recommendation["reasonSummary"]
