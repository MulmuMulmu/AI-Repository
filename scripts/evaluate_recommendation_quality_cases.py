from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommendation.vector_engine import VectorRecommendEngine

DATA_DIR = ROOT / "data" / "db"
FIXTURE_PATH = ROOT / "data" / "labels" / "recommendation_quality_cases.json"


def _load_engine() -> VectorRecommendEngine:
    recipes = {row["recipeId"]: row for row in json.loads((DATA_DIR / "recipes.json").read_text(encoding="utf-8"))}
    ingredients = {row["ingredientId"]: row for row in json.loads((DATA_DIR / "ingredients.json").read_text(encoding="utf-8"))}
    raw_recipe_ingredients = json.loads((DATA_DIR / "recipe_ingredients.json").read_text(encoding="utf-8"))
    recipe_ingredients: dict[str, list[dict]] = {}
    for row in raw_recipe_ingredients:
        recipe_ingredients.setdefault(row["recipeId"], []).append(row)
    return VectorRecommendEngine(
        recipes=recipes,
        ingredients=ingredients,
        recipe_ingredients=recipe_ingredients,
    )


def main() -> None:
    engine = _load_engine()
    cases = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))

    details: list[dict] = []
    passed = 0
    positive_case_count = 0
    top1_hit_count = 0
    top3_hit_count = 0
    exclusion_case_count = 0
    exclusion_pass_count = 0
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
        expected_recipe_id = case.get("expectedRecipeId")
        forbidden_recipe_id = case.get("forbiddenRecipeId")
        require_empty = bool(case.get("requireEmpty"))

        rank = recipe_ids.index(expected_recipe_id) + 1 if expected_recipe_id in recipe_ids else None
        if require_empty:
            success = not recommendations
            exclusion_case_count += 1
            if success:
                exclusion_pass_count += 1
        elif forbidden_recipe_id:
            success = forbidden_recipe_id not in recipe_ids
            exclusion_case_count += 1
            if success:
                exclusion_pass_count += 1
        else:
            positive_case_count += 1
            if rank == 1:
                top1_hit_count += 1
            if rank is not None and rank <= 3:
                top3_hit_count += 1
            success = rank is not None and rank <= case.get("maxRank", 1)
        if success:
            passed += 1
        top = recommendations[0] if recommendations else None
        details.append(
            {
                "caseId": case["caseId"],
                "expectedRecipeId": expected_recipe_id,
                "expectedRecipeName": case.get("expectedRecipeName"),
                "forbiddenRecipeId": forbidden_recipe_id,
                "requireEmpty": require_empty,
                "maxRank": case.get("maxRank", 1),
                "actualRank": rank,
                "topRecipeId": top["recipeId"] if top else None,
                "topRecipeName": top["name"] if top else None,
                "topScore": top["score"] if top else None,
                "passed": success,
            }
        )

    summary = {
        "fixturePath": str(FIXTURE_PATH.relative_to(ROOT)),
        "caseCount": len(cases),
        "passedCount": passed,
        "passRate": round(passed / len(cases), 4) if cases else 0.0,
        "positiveCaseCount": positive_case_count,
        "top1HitCount": top1_hit_count,
        "top1HitRate": round(top1_hit_count / positive_case_count, 4) if positive_case_count else 0.0,
        "top3HitCount": top3_hit_count,
        "top3HitRate": round(top3_hit_count / positive_case_count, 4) if positive_case_count else 0.0,
        "exclusionCaseCount": exclusion_case_count,
        "exclusionPassCount": exclusion_pass_count,
        "exclusionPassRate": round(exclusion_pass_count / exclusion_case_count, 4) if exclusion_case_count else 0.0,
        "details": details,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
