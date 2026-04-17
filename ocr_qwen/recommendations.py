from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path


URGENCY_WEIGHTS = {
    "safe": 0.0,
    "consume_soon": 0.75,
    "urgent": 1.5,
    "share_now": 0.0,
}


@dataclass(frozen=True)
class InventorySnapshot:
    normalized_name: str
    risk_level: str = "safe"
    is_expired: bool = False


@dataclass(frozen=True)
class RecipeCatalog:
    recipes: list[dict[str, object]]

    @classmethod
    def load_default(cls) -> "RecipeCatalog":
        override = os.getenv("RECIPE_CATALOG_PATH")
        if override:
            path = Path(override)
        else:
            generated_path = _generated_recipe_catalog_path()
            path = generated_path if generated_path.exists() else Path(__file__).with_name("recipes.json")
        recipes = json.loads(path.read_text(encoding="utf-8"))
        return cls(recipes=recipes)


@dataclass
class RecipeRecommendation:
    title: str
    used_ingredients: list[str]
    missing_ingredients: list[str]
    urgency_score: float
    recommendation_reason: str
    substitute_ingredients: list[str]
    share_message: str | None
    explanation_source: str = "rules"


class RecipeEngine:
    def __init__(self, catalog: RecipeCatalog | None = None, qwen_provider: object | None = None) -> None:
        self.catalog = catalog or RecipeCatalog.load_default()
        self.qwen_provider = qwen_provider

    def recommend(
        self,
        inventory_items: list[InventorySnapshot],
        limit: int = 3,
    ) -> list[RecipeRecommendation]:
        inventory_map = {
            item.normalized_name: item
            for item in inventory_items
            if not item.is_expired
        }
        ranked: list[tuple[float, RecipeRecommendation]] = []

        for recipe in self.catalog.recipes:
            ingredients = list(recipe["ingredients"])
            used = sorted([name for name in ingredients if name in inventory_map])
            if not used:
                continue

            missing = sorted([name for name in ingredients if name not in inventory_map])
            urgency_bonus = sum(URGENCY_WEIGHTS.get(inventory_map[name].risk_level, 0.0) for name in used)
            score = (len(used) * 2.0) + urgency_bonus - (len(missing) * 0.75)
            ranked.append(
                (
                    score,
                    RecipeRecommendation(
                        title=str(recipe["title"]),
                        used_ingredients=used,
                        missing_ingredients=missing,
                        urgency_score=round(score, 2),
                        recommendation_reason=self._build_reason(used, missing, inventory_map),
                        substitute_ingredients=[],
                        share_message=None,
                    ),
                )
            )

        ranked.sort(key=lambda item: (-item[0], item[1].title))
        recommendations = [recommendation for _, recommendation in ranked[:limit]]
        return self._enrich_with_qwen(recommendations, inventory_map)

    def _build_reason(
        self,
        used_ingredients: list[str],
        missing_ingredients: list[str],
        inventory_map: dict[str, InventorySnapshot],
    ) -> str:
        urgent = [
            name
            for name in used_ingredients
            if inventory_map.get(name) and inventory_map[name].risk_level == "urgent"
        ]
        if urgent:
            return (
                f"임박 재료 {', '.join(urgent)}를 먼저 쓰는 메뉴입니다. "
                f"부족 재료는 {', '.join(missing_ingredients) if missing_ingredients else '없습니다'}."
            )
        return (
            f"보유 재료 {', '.join(used_ingredients)}를 활용하는 메뉴입니다. "
            f"부족 재료는 {', '.join(missing_ingredients) if missing_ingredients else '없습니다'}."
        )

    def _enrich_with_qwen(
        self,
        recommendations: list[RecipeRecommendation],
        inventory_map: dict[str, InventorySnapshot],
    ) -> list[RecipeRecommendation]:
        if self.qwen_provider is None:
            return recommendations

        for recommendation in recommendations:
            payload = {
                "recipe": {
                    "title": recommendation.title,
                    "used_ingredients": recommendation.used_ingredients,
                    "missing_ingredients": recommendation.missing_ingredients,
                    "urgency_score": recommendation.urgency_score,
                },
                "inventory": [
                    {
                        "normalized_name": item.normalized_name,
                        "risk_level": item.risk_level,
                    }
                    for item in inventory_map.values()
                ],
            }
            try:
                enriched = self.qwen_provider.describe_recipe(payload)
            except Exception:
                enriched = None

            if not enriched:
                continue

            recommendation.recommendation_reason = enriched.get(
                "recommendation_reason",
                recommendation.recommendation_reason,
            )
            substitute_ingredients = enriched.get("substitute_ingredients", [])
            if isinstance(substitute_ingredients, list) and all(
                isinstance(item, str) for item in substitute_ingredients
            ):
                recommendation.substitute_ingredients = substitute_ingredients
            recommendation.share_message = enriched.get("share_message")
            recommendation.explanation_source = "qwen"

        return recommendations


def _generated_recipe_catalog_path() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "recipes_recommendation_seed.generated.json"
