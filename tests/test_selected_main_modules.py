from __future__ import annotations

from expiry_calculator import ExpiryCalculator
from quality_monitor import QualityMonitor
from recipe_recommender import RecipeRecommender
from sharing_filter import SharingFilter


def test_sharing_filter_classifies_blocked_review_and_allowed_items() -> None:
    result = SharingFilter().check(["생고기 모둠", "수제잼", "통조림 참치"])

    assert result["summary"] == {"blocked": 1, "review": 1, "allowed": 1}
    assert result["blocked"][0]["category"] == "생고기/생선"
    assert result["review_required"][0]["item_name"] == "수제잼"
    assert result["allowed"][0]["item_name"] == "통조림 참치"


def test_quality_monitor_records_metrics() -> None:
    monitor = QualityMonitor()
    monitor.log_request("/ai/v1/ocr/normalize", elapsed_ms=120.0, status_code=200)
    monitor.log_request("/ai/v1/ocr/normalize", elapsed_ms=240.0, status_code=500, error="boom")

    metrics = monitor.get_metrics("1h")

    assert metrics["total_requests"] == 2
    assert metrics["error_count"] == 1
    assert metrics["endpoints"]["/ai/v1/ocr/normalize"]["count"] == 2


def test_expiry_calculator_uses_rule_based_fallback_without_openai() -> None:
    calculator = ExpiryCalculator()
    calculator._openai_client = None
    calculator._api_key = ""

    result = calculator.calculate(
        item_name="양파",
        purchase_date="2026-04-10",
        storage_method="냉장",
        category="채소/과일",
    )

    assert result["method"] == "rule-based"
    assert result["expiry_date"] == "2026-05-10"
    assert result["risk_level"] in {"safe", "caution", "danger", "expired"}


def test_recipe_recommender_returns_partial_match_recommendation() -> None:
    recommender = RecipeRecommender(
        recipes={
            "r1": {
                "recipeId": "r1",
                "name": "라면볶이",
                "category": "분식",
                "cookingMethod": "볶기",
                "cookingMethodCode": "STIRFRY",
                "imageUrl": "",
            }
        },
        ingredients={
            "i1": {"ingredientId": "i1", "ingredientName": "라면", "category": "쌀/면/빵"},
            "i2": {"ingredientId": "i2", "ingredientName": "고추장", "category": "소스/조미료/오일"},
        },
        recipe_ingredients={
            "r1": [
                {"recipeId": "r1", "ingredientId": "i1"},
                {"recipeId": "r1", "ingredientId": "i2"},
            ]
        },
    )

    recommendations = recommender.recommend(["i1"], top_k=5)

    assert len(recommendations) == 1
    assert recommendations[0]["recipeId"] == "r1"
    assert recommendations[0]["missingIngredients"][0]["ingredientId"] == "i2"


def test_recipe_recommender_applies_personalization_filters_and_boosts() -> None:
    recommender = RecipeRecommender(
        recipes={
            "r1": {
                "recipeId": "r1",
                "name": "양파볶음",
                "category": "반찬",
                "cookingMethod": "볶기",
                "cookingMethodCode": "STIRFRY",
                "imageUrl": "",
            },
            "r2": {
                "recipeId": "r2",
                "name": "감자수프",
                "category": "국",
                "cookingMethod": "끓이기",
                "cookingMethodCode": "BOIL",
                "imageUrl": "",
            },
            "r3": {
                "recipeId": "r3",
                "name": "땅콩볶음",
                "category": "안주",
                "cookingMethod": "볶기",
                "cookingMethodCode": "STIRFRY",
                "imageUrl": "",
            },
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

    recommendations = recommender.recommend(
        ["i1", "i2", "i3", "i4"],
        top_k=5,
        preferred_categories=["국"],
        preferred_keywords=["수프"],
        blocked_ingredient_ids=["i5"],
        excluded_categories=["안주"],
    )

    assert [recommendation["recipeId"] for recommendation in recommendations] == ["r2", "r1"]
