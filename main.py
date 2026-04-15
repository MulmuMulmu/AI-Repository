"""
AI FastAPI 서버 — 영수증 OCR + 재료 매칭 + 레시피 추천

실행: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import re
import tempfile
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# ═══════════════════════════════════════════════════════════════
#  데이터 로드
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).resolve().parent / "data" / "db"

def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)

_recipes_raw: list = _load_json("recipes.json")
_ingredients_raw: list = _load_json("ingredients.json")
_recipe_ingredients_raw: list = _load_json("recipe_ingredients.json")
_recipe_steps_raw: list = _load_json("recipe_steps.json")

RECIPES: Dict[str, dict] = {r["recipeId"]: r for r in _recipes_raw}
INGREDIENTS: Dict[str, dict] = {i["ingredientId"]: i for i in _ingredients_raw}

RECIPE_INGR: Dict[str, List[dict]] = defaultdict(list)
for ri in _recipe_ingredients_raw:
    RECIPE_INGR[ri["recipeId"]].append(ri)

RECIPE_STEPS: Dict[str, List[dict]] = defaultdict(list)
for rs in _recipe_steps_raw:
    RECIPE_STEPS[rs["recipeId"]].append(rs)
for v in RECIPE_STEPS.values():
    v.sort(key=lambda s: s["stepOrder"])

INGR_NAME_INDEX: Dict[str, str] = {
    i["ingredientName"]: i["ingredientId"] for i in _ingredients_raw
}

# ═══════════════════════════════════════════════════════════════
#  FastAPI 앱
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="레시피 추천 AI API",
    version="1.0.0",
    description="영수증 OCR + 재료 매칭 + 레시피 추천 시스템",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_RECEIPT_BACKEND = None
_RECEIPT_PARSER = None
_RECEIPT_SERVICE_NOOP = None
_RECEIPT_SERVICE_QWEN = None

# ═══════════════════════════════════════════════════════════════
#  Pydantic 스키마
# ═══════════════════════════════════════════════════════════════

class MatchRequest(BaseModel):
    product_names: List[str] = Field(..., min_length=1)

class RecommendRequest(BaseModel):
    ingredientIds: List[str] = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    category: Optional[str] = None
    min_match_rate: float = Field(default=0.0, ge=0.0, le=1.0)

class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[Dict[str, str]] = None

# ═══════════════════════════════════════════════════════════════
#  유틸리티
# ═══════════════════════════════════════════════════════════════

def _normalize_name(name: str) -> str:
    """비교를 위한 이름 정규화: 공백·특수문자 제거, 소문자, NFC 정규화."""
    s = unicodedata.normalize("NFC", name.strip().lower())
    s = re.sub(r"[^\w가-힣]", "", s)
    return s


def _similarity(a: str, b: str) -> float:
    """두 문자열의 유사도 (0~1)."""
    na, nb = _normalize_name(a), _normalize_name(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def _match_product_to_ingredient(product_name: str) -> Dict[str, Any]:
    """상품명을 DB 재료와 매칭. 최고 유사도 재료를 반환."""
    best_score = 0.0
    best_ingr = None
    norm_product = _normalize_name(product_name)

    for ingr in _ingredients_raw:
        ingr_name = ingr["ingredientName"]
        norm_ingr = _normalize_name(ingr_name)

        if norm_product == norm_ingr:
            return {
                "product_name": product_name,
                "ingredientId": ingr["ingredientId"],
                "ingredientName": ingr_name,
                "category": ingr["category"],
                "similarity": 1.0,
            }

        if norm_product in norm_ingr or norm_ingr in norm_product:
            score = 0.9
        else:
            score = SequenceMatcher(None, norm_product, norm_ingr).ratio()

        if score > best_score:
            best_score = score
            best_ingr = ingr

    if best_ingr and best_score >= 0.5:
        return {
            "product_name": product_name,
            "ingredientId": best_ingr["ingredientId"],
            "ingredientName": best_ingr["ingredientName"],
            "category": best_ingr["category"],
            "similarity": round(best_score, 4),
        }
    return None


def _find_suggestions(product_name: str, top_n: int = 3) -> List[str]:
    """매칭 실패 시 유사한 재료명 추천."""
    scored = []
    for ingr in _ingredients_raw:
        s = _similarity(product_name, ingr["ingredientName"])
        if s >= 0.3:
            scored.append((s, ingr["ingredientName"]))
    scored.sort(key=lambda x: -x[0])
    return [name for _, name in scored[:top_n]]


def _normalize_food_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """OCR 또는 Qwen 결과를 API 계약에 맞는 식품 항목으로 정규화한다."""
    if not isinstance(item, dict):
        return None

    product_name = item.get("product_name") or item.get("name")
    if not isinstance(product_name, str):
        product_name = str(product_name or "").strip()
    product_name = product_name.strip()
    if not product_name:
        return None

    amount_krw = item.get("amount_krw")
    if amount_krw is not None and amount_krw != "":
        try:
            amount_krw = int(str(amount_krw).replace(",", ""))
        except (TypeError, ValueError):
            amount_krw = None
    else:
        amount_krw = None

    notes = item.get("notes", "")
    if notes is None:
        notes = ""

    return {
        "product_name": product_name,
        "amount_krw": amount_krw,
        "notes": str(notes).strip(),
    }


def _normalize_food_items(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    for item in items:
        normalized_item = _normalize_food_item(item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


def _legacy_food_items_from_parsed(parsed: Dict[str, Any]) -> list[Dict[str, Any]]:
    legacy_items: list[Dict[str, Any]] = []
    for item in parsed.get("items", []):
        if not isinstance(item, dict):
            continue
        product_name = item.get("normalized_name") or item.get("raw_name")
        if not product_name:
            continue
        amount = item.get("amount")
        if isinstance(amount, float) and amount.is_integer():
            amount = int(amount)
        legacy_items.append(
            {
                "product_name": product_name,
                "amount_krw": amount,
                "notes": ", ".join(item.get("review_reason", [])),
            }
        )
    return _normalize_food_items(legacy_items)


def _legacy_model_name_from_parsed(parsed: Dict[str, Any]) -> str:
    engine_version = str(parsed.get("engine_version") or "receipt-engine-v2")
    diagnostics = parsed.get("diagnostics", {})
    if isinstance(diagnostics, dict) and diagnostics.get("qwen_used"):
        return f"{engine_version}+qwen"
    return engine_version


def _get_receipt_backend():
    global _RECEIPT_BACKEND
    if _RECEIPT_BACKEND is None:
        from ocr_qwen.services import PaddleOcrBackend

        _RECEIPT_BACKEND = PaddleOcrBackend()
    return _RECEIPT_BACKEND


def _get_receipt_parser():
    global _RECEIPT_PARSER
    if _RECEIPT_PARSER is None:
        from ocr_qwen.receipts import ReceiptParser

        _RECEIPT_PARSER = ReceiptParser()
    return _RECEIPT_PARSER


def _get_receipt_service(use_qwen: bool):
    global _RECEIPT_SERVICE_NOOP, _RECEIPT_SERVICE_QWEN
    if use_qwen:
        if _RECEIPT_SERVICE_QWEN is None:
            from ocr_qwen.qwen import build_default_qwen_provider
            from ocr_qwen.services import ReceiptParseService

            _RECEIPT_SERVICE_QWEN = ReceiptParseService(
                ocr_backend=_get_receipt_backend(),
                parser=_get_receipt_parser(),
                qwen_provider=build_default_qwen_provider(),
            )
        return _RECEIPT_SERVICE_QWEN

    if _RECEIPT_SERVICE_NOOP is None:
        from ocr_qwen.qwen import NoopQwenProvider
        from ocr_qwen.services import ReceiptParseService

        _RECEIPT_SERVICE_NOOP = ReceiptParseService(
            ocr_backend=_get_receipt_backend(),
            parser=_get_receipt_parser(),
            qwen_provider=NoopQwenProvider(),
        )
    return _RECEIPT_SERVICE_NOOP


@app.on_event("startup")
def _warm_up_receipt_services() -> None:
    try:
        _get_receipt_backend().warm_up()
    except Exception as exc:
        print(f"[startup] receipt ocr warm-up skipped: {exc}")

# ═══════════════════════════════════════════════════════════════
#  레시피 추천 엔진
# ═══════════════════════════════════════════════════════════════

def recommend_recipes(
    ingredient_ids: List[str],
    top_k: int = 10,
    category: Optional[str] = None,
    min_match_rate: float = 0.0,
) -> List[dict]:
    """
    보유 재료 ID 목록으로 레시피를 추천.
    일부 재료만 있어도 matchRate(일치율) 기준으로 정렬하여 반환.
    """
    owned = set(ingredient_ids)
    results = []

    for recipe_id, recipe in RECIPES.items():
        if category and recipe["category"] != category:
            continue

        ri_list = RECIPE_INGR.get(recipe_id, [])
        if not ri_list:
            continue

        recipe_ingr_ids = {ri["ingredientId"] for ri in ri_list}
        matched_ids = owned & recipe_ingr_ids
        missing_ids = recipe_ingr_ids - owned

        match_rate = len(matched_ids) / len(recipe_ingr_ids)
        if match_rate < min_match_rate:
            continue
        if not matched_ids:
            continue

        matched_list = []
        for iid in matched_ids:
            ingr = INGREDIENTS.get(iid)
            if ingr:
                matched_list.append({
                    "ingredientId": iid,
                    "ingredientName": ingr["ingredientName"],
                })

        missing_list = []
        for iid in missing_ids:
            ingr = INGREDIENTS.get(iid)
            if ingr:
                missing_list.append({
                    "ingredientId": iid,
                    "ingredientName": ingr["ingredientName"],
                })

        results.append({
            "recipeId": recipe_id,
            "name": recipe["name"],
            "category": recipe["category"],
            "imageUrl": recipe.get("imageUrl", ""),
            "matchedIngredients": matched_list,
            "missingIngredients": missing_list,
            "matchRate": round(match_rate, 4),
            "totalIngredientCount": len(recipe_ingr_ids),
        })

    results.sort(key=lambda r: (-r["matchRate"], -len(r["matchedIngredients"])))
    return results[:top_k]

# ═══════════════════════════════════════════════════════════════
#  API 엔드포인트
# ═══════════════════════════════════════════════════════════════

@app.get("/api/health")
async def health_check():
    try:
        from ocr_qwen.qwen import local_qwen_enabled, qwen_runtime_available

        qwen_status = {
            "runtime_available": qwen_runtime_available(),
            "local_enabled": local_qwen_enabled(),
        }
    except Exception as exc:
        qwen_status = f"unavailable ({exc})"

    return ApiResponse(
        success=True,
        data={
            "status": "healthy",
            "version": "1.0.0",
            "services": {
                "paddleocr": "available",
                "preprocess": "available",
                "bbox_contract": "enabled",
                "qwen_llm": qwen_status,
                "database": "connected",
            },
            "stats": {
                "total_recipes": len(RECIPES),
                "total_ingredients": len(INGREDIENTS),
                "total_recipe_ingredients": len(_recipe_ingredients_raw),
                "total_recipe_steps": len(_recipe_steps_raw),
            },
        },
    )


@app.post("/api/ocr/receipt")
async def ocr_receipt(
    image: UploadFile = File(...),
    use_qwen: bool = Query(
        default=True,
        description=(
            "Local OpenAI-compatible Qwen 보정 사용 여부. "
            "true여도 Qwen 환경변수/로컬 서버가 없으면 OCR-only로 fallback하며, "
            "응답 계약(ocr_texts, food_items, food_count, model)은 유지됩니다."
        ),
    ),
):
    """영수증 이미지 → PaddleOCR 기반 OCR + 선택적 Qwen 보정 → 식품명 추출."""
    if image.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_IMAGE", "message": "jpg, png 파일만 지원합니다."},
        )

    suffix = ".jpg" if "jpeg" in (image.content_type or "") else ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await image.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        service = _get_receipt_service(use_qwen=use_qwen)
        parsed = service.parse({"receipt_image_url": tmp_path})

        ocr_texts = parsed.get("ocr_texts", [])
        food_items = _legacy_food_items_from_parsed(parsed)
        model_name = _legacy_model_name_from_parsed(parsed)

        return ApiResponse(
            success=True,
            data={
                "ocr_texts": ocr_texts,
                "food_items": food_items,
                "food_count": len(food_items),
                "model": model_name,
                "vendor_name": parsed.get("vendor_name"),
                "purchased_at": parsed.get("purchased_at"),
                "totals": parsed.get("totals", {}),
                "diagnostics": parsed.get("diagnostics", {}),
            },
        )
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail={"code": "SERVICE_UNAVAILABLE", "message": "PaddleOCR가 설치되지 않았습니다."},
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"code": "OCR_FAILED", "message": str(e)},
        )
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/api/ingredients/match")
async def match_ingredients(req: MatchRequest):
    """OCR 추출 상품명 → DB Ingredient 매칭."""
    matched = []
    unmatched = []

    for name in req.product_names:
        result = _match_product_to_ingredient(name)
        if result:
            matched.append(result)
        else:
            unmatched.append({
                "product_name": name,
                "reason": "DB에 일치하는 재료 없음",
                "suggestions": _find_suggestions(name),
            })

    return ApiResponse(
        success=True,
        data={
            "matched": matched,
            "unmatched": unmatched,
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
        },
    )


@app.post("/api/recipes/recommend")
async def recommend(req: RecommendRequest):
    """보유 재료 기반 레시피 추천. 일부 재료만 있어도 추천 가능."""
    valid_ids = [iid for iid in req.ingredientIds if iid in INGREDIENTS]
    if not valid_ids:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "INVALID_REQUEST",
                "message": "유효한 ingredientId가 없습니다.",
            },
        )

    recommendations = recommend_recipes(
        ingredient_ids=valid_ids,
        top_k=req.top_k,
        category=req.category,
        min_match_rate=req.min_match_rate,
    )

    return ApiResponse(
        success=True,
        data={
            "recommendations": recommendations,
            "total_count": len(recommendations),
            "input_ingredient_count": len(valid_ids),
        },
    )


@app.get("/api/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """레시피 상세 조회 (재료 + 조리 단계)."""
    recipe = RECIPES.get(recipe_id)
    if not recipe:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "RECIPE_NOT_FOUND",
                "message": f"레시피를 찾을 수 없습니다: {recipe_id}",
            },
        )

    ri_list = RECIPE_INGR.get(recipe_id, [])
    ingredients = []
    for ri in ri_list:
        ingr = INGREDIENTS.get(ri["ingredientId"])
        if ingr:
            ingredients.append({
                "recipeIngredientId": ri["recipeIngredientId"],
                "ingredientId": ri["ingredientId"],
                "ingredientName": ingr["ingredientName"],
                "category": ingr["category"],
                "amount": ri["amount"],
                "unit": ri["unit"],
            })

    steps = [
        {
            "recipeStepId": s["recipeStepId"],
            "stepOrder": s["stepOrder"],
            "description": s["description"],
        }
        for s in RECIPE_STEPS.get(recipe_id, [])
    ]

    return ApiResponse(
        success=True,
        data={
            "recipeId": recipe_id,
            "name": recipe["name"],
            "category": recipe["category"],
            "imageUrl": recipe.get("imageUrl", ""),
            "ingredients": ingredients,
            "steps": steps,
            "ingredient_count": len(ingredients),
            "step_count": len(steps),
        },
    )


@app.get("/api/ingredients/search")
async def search_ingredients(
    q: str = Query(..., min_length=1, description="검색 키워드"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    limit: int = Query(20, ge=1, le=100, description="최대 반환 개수"),
):
    """키워드로 재료 검색."""
    q_norm = _normalize_name(q)
    results = []

    for ingr in _ingredients_raw:
        if category and ingr["category"] != category:
            continue
        if q_norm in _normalize_name(ingr["ingredientName"]):
            results.append({
                "ingredientId": ingr["ingredientId"],
                "ingredientName": ingr["ingredientName"],
                "category": ingr["category"],
            })
            if len(results) >= limit:
                break

    return ApiResponse(
        success=True,
        data={
            "results": results,
            "total_count": len(results),
            "query": q,
        },
    )
