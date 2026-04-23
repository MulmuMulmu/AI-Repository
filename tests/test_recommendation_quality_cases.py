from __future__ import annotations

import json
from pathlib import Path

from recommendation.vector_engine import VectorRecommendEngine


def _load_engine() -> VectorRecommendEngine:
    data_dir = Path("data/db")
    recipes = {row["recipeId"]: row for row in json.loads((data_dir / "recipes.json").read_text(encoding="utf-8"))}
    ingredients = {row["ingredientId"]: row for row in json.loads((data_dir / "ingredients.json").read_text(encoding="utf-8"))}
    raw_recipe_ingredients = json.loads((data_dir / "recipe_ingredients.json").read_text(encoding="utf-8"))
    recipe_ingredients: dict[str, list[dict]] = {}
    for row in raw_recipe_ingredients:
        recipe_ingredients.setdefault(row["recipeId"], []).append(row)
    return VectorRecommendEngine(
        recipes=recipes,
        ingredients=ingredients,
        recipe_ingredients=recipe_ingredients,
    )


def _load_cases() -> list[dict]:
    fixture_path = Path("data/labels/recommendation_quality_cases.json")
    return json.loads(fixture_path.read_text(encoding="utf-8"))


def test_recommendation_quality_cases_fixture_passes() -> None:
    engine = _load_engine()
    cases = _load_cases()

    assert cases, "recommendation quality fixture must not be empty"

    for case in cases:
        result = engine.recommend(
            {
                "ingredientIds": case["ingredientIds"],
                "topK": case.get("topK", 5),
                "minCoverageRatio": case.get("minCoverageRatio", 0.5),
                "preferredCategories": case.get("preferredCategories", []),
                "preferredKeywords": case.get("preferredKeywords", []),
                "excludedCategories": case.get("excludedCategories", []),
                "excludedKeywords": case.get("excludedKeywords", []),
                "allergyIngredientIds": case.get("allergyIngredientIds", []),
                "dislikedIngredientIds": case.get("dislikedIngredientIds", []),
            }
        )

        recommendations = result["recommendations"]
        recipe_ids = [item["recipeId"] for item in recommendations]

        if case.get("requireEmpty"):
            assert recommendations == [], case["caseId"]
            continue

        forbidden_recipe_id = case.get("forbiddenRecipeId")
        if forbidden_recipe_id:
            assert forbidden_recipe_id not in recipe_ids, case["caseId"]

        expected_recipe_id = case.get("expectedRecipeId")
        if expected_recipe_id:
            assert expected_recipe_id in recipe_ids, case["caseId"]
            rank = recipe_ids.index(expected_recipe_id) + 1
            assert rank <= case.get("maxRank", 1), case["caseId"]
