from __future__ import annotations

import math
from collections import Counter
from typing import Any, Dict, List, Set


CATEGORY_IMPORTANCE = {
    "정육/계란": 1.65,
    "해산물": 1.65,
    "채소/과일": 1.15,
    "유제품": 1.2,
    "쌀/면/빵": 1.5,
    "소스/조미료/오일": 0.7,
    "가공식품": 0.95,
    "기타": 0.8,
}


class VectorRecommendEngine:
    def __init__(
        self,
        recipes: Dict[str, dict],
        ingredients: Dict[str, dict],
        recipe_ingredients: Dict[str, List[dict]],
    ) -> None:
        self._recipes = recipes
        self._ingredients = ingredients
        self._recipe_ingredients = recipe_ingredients
        self._idf = self._build_idf()
        self._profiles = self._build_recipe_profiles()

    def _build_idf(self) -> Dict[str, float]:
        counts: Counter[str] = Counter()
        for ri_list in self._recipe_ingredients.values():
            seen = {
                str(ri["ingredientId"])
                for ri in ri_list
                if isinstance(ri, dict) and ri.get("ingredientId")
            }
            for ingredient_id in seen:
                counts[ingredient_id] += 1

        recipe_count = max(len(self._recipe_ingredients), 1)
        idf: Dict[str, float] = {}
        for ingredient_id, freq in counts.items():
            idf[ingredient_id] = math.log((1 + recipe_count) / (1 + freq)) + 1.0
        return idf

    def _normalize_string_list(self, values: List[str] | None) -> List[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values or []:
            cleaned = str(value or "").strip()
            if not cleaned:
                continue
            lowered = cleaned.casefold()
            if lowered in seen:
                continue
            seen.add(lowered)
            normalized.append(cleaned)
        return normalized

    def _keyword_blob(self, recipe: dict) -> str:
        return " ".join(
            [
                str(recipe.get("name", "")),
                str(recipe.get("category", "")),
                str(recipe.get("cookingMethod", "")),
            ]
        ).casefold()

    def _ingredient_category(self, ingredient_id: str) -> str:
        ingredient = self._ingredients.get(ingredient_id, {})
        return str(ingredient.get("category", "기타"))

    def _category_multiplier(self, ingredient_id: str) -> float:
        return CATEGORY_IMPORTANCE.get(self._ingredient_category(ingredient_id), 1.0)

    def _coerce_amount(self, value: Any) -> float:
        try:
            amount = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(amount, 0.0)

    def _amount_multiplier(self, amount: float, unit: str) -> float:
        if amount <= 0:
            return 1.0

        normalized_unit = str(unit or "").strip().casefold()
        if normalized_unit in {"개", "장", "봉", "팩", "병", "캔"}:
            scaled = amount * 30.0
        elif normalized_unit in {"큰술", "작은술", "tbsp", "tsp"}:
            scaled = amount * 12.0
        else:
            scaled = amount

        return 1.0 + min(math.log1p(scaled) / 5.0, 0.85)

    def _recipe_ingredient_weight(self, ingredient_row: dict) -> float:
        ingredient_id = str(ingredient_row.get("ingredientId"))
        return (
            self._idf.get(ingredient_id, 1.0)
            * self._category_multiplier(ingredient_id)
            * self._amount_multiplier(
                self._coerce_amount(ingredient_row.get("amount")),
                str(ingredient_row.get("unit", "")),
            )
        )

    def _owned_ingredient_weight(self, ingredient_id: str) -> float:
        return self._idf.get(ingredient_id, 1.0) * self._category_multiplier(ingredient_id)

    def _build_recipe_profiles(self) -> Dict[str, dict]:
        profiles: Dict[str, dict] = {}
        for recipe_id, rows in self._recipe_ingredients.items():
            ingredient_weights: Dict[str, float] = {}
            for row in rows:
                if not isinstance(row, dict) or not row.get("ingredientId"):
                    continue
                ingredient_id = str(row["ingredientId"])
                ingredient_weights[ingredient_id] = max(
                    ingredient_weights.get(ingredient_id, 0.0),
                    self._recipe_ingredient_weight(row),
                )

            if not ingredient_weights:
                continue

            sorted_ids = sorted(
                ingredient_weights,
                key=lambda ingredient_id: (
                    ingredient_weights[ingredient_id],
                    self._ingredients.get(ingredient_id, {}).get("ingredientName", ""),
                ),
                reverse=True,
            )
            if len(sorted_ids) <= 3:
                core_count = 1
            elif len(sorted_ids) <= 6:
                core_count = 2
            else:
                core_count = 3
            core_ids = set(sorted_ids[:core_count])
            profiles[recipe_id] = {
                "ingredient_ids": set(ingredient_weights.keys()),
                "ingredient_weights": ingredient_weights,
                "total_weight": sum(ingredient_weights.values()),
                "core_ids": core_ids,
            }
        return profiles

    def _cosine_similarity(self, owned_ids: Set[str], recipe_ids: Set[str], recipe_weights: Dict[str, float]) -> float:
        if not owned_ids or not recipe_ids:
            return 0.0

        owned_weights = {ingredient_id: self._owned_ingredient_weight(ingredient_id) for ingredient_id in owned_ids}
        dot = sum(
            owned_weights[ingredient_id] * recipe_weights[ingredient_id]
            for ingredient_id in owned_ids & recipe_ids
            if ingredient_id in recipe_weights
        )
        owned_norm = math.sqrt(sum(weight * weight for weight in owned_weights.values()))
        recipe_norm = math.sqrt(sum(weight * weight for weight in recipe_weights.values()))
        if owned_norm == 0 or recipe_norm == 0:
            return 0.0
        return dot / (owned_norm * recipe_norm)

    def _ingredient_summary(self, ingredient_ids: Set[str]) -> List[dict]:
        return [
            {
                "ingredientId": ingredient_id,
                "ingredientName": self._ingredients[ingredient_id]["ingredientName"],
            }
            for ingredient_id in sorted(ingredient_ids)
            if ingredient_id in self._ingredients
        ]

    def _build_reason_summary(
        self,
        *,
        matched_count: int,
        total_count: int,
        core_matched_count: int,
        core_total_count: int,
        missing_core_names: List[str],
    ) -> str:
        summary = f"보유 재료 {matched_count}/{total_count}개, 핵심 재료 {core_matched_count}/{core_total_count}개 충족"
        if missing_core_names:
            return summary + f", 부족 핵심 재료: {', '.join(missing_core_names)}"
        return summary

    def recommend(self, payload: dict[str, Any]) -> dict[str, Any]:
        owned_ids = {
            ingredient_id
            for ingredient_id in payload.get("ingredientIds", [])
            if ingredient_id in self._ingredients
        }
        if not owned_ids:
            return {"recommendations": [], "totalCount": 0, "inputIngredientCount": 0}

        top_k = int(payload.get("topK", 10))
        min_coverage_ratio = float(payload.get("minCoverageRatio", 0.5))
        preferred_ids = {
            ingredient_id
            for ingredient_id in payload.get("preferredIngredientIds", [])
            if ingredient_id in self._ingredients
        }
        blocked_ids = {
            ingredient_id
            for ingredient_id in [
                *payload.get("dislikedIngredientIds", []),
                *payload.get("allergyIngredientIds", []),
            ]
            if ingredient_id in self._ingredients
        }
        preferred_categories = {
            value.casefold() for value in self._normalize_string_list(payload.get("preferredCategories"))
        }
        excluded_categories = {
            value.casefold() for value in self._normalize_string_list(payload.get("excludedCategories"))
        }
        preferred_keywords = {
            value.casefold() for value in self._normalize_string_list(payload.get("preferredKeywords"))
        }
        excluded_keywords = {
            value.casefold() for value in self._normalize_string_list(payload.get("excludedKeywords"))
        }

        recommendations: list[dict[str, Any]] = []
        for recipe_id, recipe in self._recipes.items():
            profile = self._profiles.get(recipe_id)
            if not profile:
                continue

            recipe_ids: Set[str] = profile["ingredient_ids"]
            recipe_weights: Dict[str, float] = profile["ingredient_weights"]
            total_weight: float = profile["total_weight"]
            core_ids: Set[str] = profile["core_ids"]

            recipe_category = str(recipe.get("category", "")).casefold()
            if recipe_category in excluded_categories:
                continue

            keyword_blob = self._keyword_blob(recipe)
            if any(keyword in keyword_blob for keyword in excluded_keywords):
                continue
            if recipe_ids & blocked_ids:
                continue

            matched_ids = owned_ids & recipe_ids
            coverage_ratio = len(matched_ids) / len(recipe_ids)
            if coverage_ratio < min_coverage_ratio:
                continue

            missing_ids = recipe_ids - owned_ids
            matched_weight = sum(recipe_weights[ingredient_id] for ingredient_id in matched_ids)
            missing_weight = sum(recipe_weights[ingredient_id] for ingredient_id in missing_ids)
            weighted_coverage = matched_weight / total_weight if total_weight else 0.0

            matched_core_ids = core_ids & owned_ids
            missing_core_ids = core_ids - owned_ids
            core_coverage = len(matched_core_ids) / max(len(core_ids), 1)

            cosine_score = self._cosine_similarity(owned_ids, recipe_ids, recipe_weights)
            missing_penalty = missing_weight / total_weight if total_weight else 0.0
            core_missing_penalty = len(missing_core_ids) / max(len(core_ids), 1)

            preference_bonus = 0.0
            if preferred_ids:
                preferred_match_count = len(matched_ids & preferred_ids)
                preference_bonus += 0.06 * (preferred_match_count / max(len(preferred_ids), 1))
            if preferred_categories and recipe_category in preferred_categories:
                preference_bonus += 0.04
            if preferred_keywords and any(keyword in keyword_blob for keyword in preferred_keywords):
                preference_bonus += 0.04

            score = (
                (0.4 * weighted_coverage)
                + (0.2 * cosine_score)
                + (0.2 * core_coverage)
                + (0.2 * coverage_ratio)
                + preference_bonus
                - (0.1 * missing_penalty)
                - (0.15 * core_missing_penalty)
            )
            score = max(0.0, min(score, 1.0))

            recommendations.append(
                {
                    "recipeId": recipe_id,
                    "name": recipe.get("name", ""),
                    "category": recipe.get("category", ""),
                    "imageUrl": recipe.get("imageUrl", ""),
                    "score": round(score, 4),
                    "coverageRatio": round(coverage_ratio, 4),
                    "weightedCoverage": round(weighted_coverage, 4),
                    "coreCoverage": round(core_coverage, 4),
                    "matchedIngredients": self._ingredient_summary(matched_ids),
                    "missingIngredients": self._ingredient_summary(missing_ids),
                    "matchedCoreIngredients": self._ingredient_summary(matched_core_ids),
                    "missingCoreIngredients": self._ingredient_summary(missing_core_ids),
                    "reasonSummary": self._build_reason_summary(
                        matched_count=len(matched_ids),
                        total_count=len(recipe_ids),
                        core_matched_count=len(matched_core_ids),
                        core_total_count=len(core_ids),
                        missing_core_names=[
                            self._ingredients[ingredient_id]["ingredientName"]
                            for ingredient_id in sorted(missing_core_ids)
                            if ingredient_id in self._ingredients
                        ],
                    ),
                    "totalIngredientCount": len(recipe_ids),
                }
            )

        recommendations.sort(
            key=lambda item: (
                item["score"],
                item["coreCoverage"],
                item["weightedCoverage"],
                item["coverageRatio"],
                -item["totalIngredientCount"],
                item["recipeId"],
            ),
            reverse=True,
        )

        limited = recommendations[:top_k]
        return {
            "recommendations": limited,
            "totalCount": len(limited),
            "inputIngredientCount": len(owned_ids),
        }
