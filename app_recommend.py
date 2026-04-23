from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from recommendation.vector_engine import VectorRecommendEngine


DATA_DIR = Path(__file__).resolve().parent / "data" / "db"


def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)


_recipes_raw: list = _load_json("recipes.json")
_ingredients_raw: list = _load_json("ingredients.json")
_recipe_ingredients_raw: list = _load_json("recipe_ingredients.json")

RECIPES: Dict[str, dict] = {r["recipeId"]: r for r in _recipes_raw}
INGREDIENTS: Dict[str, dict] = {i["ingredientId"]: i for i in _ingredients_raw}
RECIPE_INGREDIENTS: Dict[str, List[dict]] = defaultdict(list)
for ri in _recipe_ingredients_raw:
    RECIPE_INGREDIENTS[ri["recipeId"]].append(ri)

_VECTOR_RECOMMEND_ENGINE = None


class RecommendRequest(BaseModel):
    ingredientIds: List[str] = Field(..., min_length=1)
    topK: int = Field(default=10, ge=1, le=100)
    minCoverageRatio: float = Field(default=0.5, ge=0.0, le=1.0)
    preferredIngredientIds: List[str] = Field(default_factory=list)
    dislikedIngredientIds: List[str] = Field(default_factory=list)
    allergyIngredientIds: List[str] = Field(default_factory=list)
    preferredCategories: List[str] = Field(default_factory=list)
    excludedCategories: List[str] = Field(default_factory=list)
    preferredKeywords: List[str] = Field(default_factory=list)
    excludedKeywords: List[str] = Field(default_factory=list)


class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: dict[str, str] | None = None


app = FastAPI(
    title="추천 AI API",
    version="1.0.0",
    description="벡터 기반 레시피 추천 API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_vector_recommend_engine() -> VectorRecommendEngine:
    global _VECTOR_RECOMMEND_ENGINE
    if _VECTOR_RECOMMEND_ENGINE is None:
        _VECTOR_RECOMMEND_ENGINE = VectorRecommendEngine(
            recipes=RECIPES,
            ingredients=INGREDIENTS,
            recipe_ingredients=RECIPE_INGREDIENTS,
        )
    return _VECTOR_RECOMMEND_ENGINE


@app.post("/recommend")
async def recommend(req: RecommendRequest):
    valid_ids = [ingredient_id for ingredient_id in req.ingredientIds if ingredient_id in INGREDIENTS]
    if not valid_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REQUEST",
                "message": "유효한 ingredientId가 없습니다.",
            },
        )

    result = _get_vector_recommend_engine().recommend(
        {
            "ingredientIds": valid_ids,
            "topK": req.topK,
            "minCoverageRatio": req.minCoverageRatio,
            "preferredIngredientIds": req.preferredIngredientIds,
            "dislikedIngredientIds": req.dislikedIngredientIds,
            "allergyIngredientIds": req.allergyIngredientIds,
            "preferredCategories": req.preferredCategories,
            "excludedCategories": req.excludedCategories,
            "preferredKeywords": req.preferredKeywords,
            "excludedKeywords": req.excludedKeywords,
        }
    )

    return ApiResponse(success=True, data=result)
