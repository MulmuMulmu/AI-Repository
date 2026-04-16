"""
AI FastAPI 서버 — 설계서 v1.1 기준 /ai/v1/ API

엔드포인트 목록:
  ■ OCR  → /ai/v1/ocr/preprocess, /ai/v1/ocr/extract-lines, /ai/v1/ocr/normalize
  ■ 추천  → /ai/v1/recommendations/candidates, /ai/v1/recommendations/explanations
  ■ 레시피 → /ai/v1/recipes/{id}
  ■ 소비기한 → /ai/v1/expiry/calculate, /ai/v1/expiry/alerts
  ■ 나눔  → /ai/v1/sharing/check
  ■ 재료  → /ai/v1/ingredients/search, /ai/v1/cooking-methods
  ■ 운영  → /ai/v1/health, /ai/v1/quality/metrics, /ai/v1/quality/drift,
            /ai/v1/models/version, /ai/v1/dictionaries/version,
            /ai/v1/prompts/version, /ai/v1/cache/clear, /ai/v1/jobs/{id}

실행: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import re
import tempfile
import time
import unicodedata
import uuid
from collections import Counter, defaultdict
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from rule_based_normalizer import RuleBasedNormalizer
from recipe_recommender import RecipeRecommender
from expiry_calculator import ExpiryCalculator
from sharing_filter import SharingFilter
from quality_monitor import QualityMonitor

# ═══════════════════════════════════════════════════════════════
#  데이터 로드
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).resolve().parent / "data" / "db"

MODEL_VERSION = "ai-server-v1.1.0"


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
#  서비스 초기화
# ═══════════════════════════════════════════════════════════════

_normalizer = RuleBasedNormalizer()
_recommender = RecipeRecommender(
    recipes=RECIPES, ingredients=INGREDIENTS, recipe_ingredients=RECIPE_INGR,
)
_expiry_calc = ExpiryCalculator()
_sharing_filter = SharingFilter()
_monitor = QualityMonitor()

# 비동기 작업 저장소 (in-memory)
_jobs: Dict[str, Dict[str, Any]] = {}

# 캐시 (in-memory)
_cache: Dict[str, Dict[str, Any]] = {}

# ═══════════════════════════════════════════════════════════════
#  FastAPI 앱
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="레시피 추천 AI API",
    version=MODEL_VERSION,
    description="설계서 v1.1 — 영수증 OCR + 재료 매칭 + 레시피 추천 + 소비기한 + 나눔 필터링",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════════════════════
#  공통 응답 모델 (설계서 요구사항)
# ═══════════════════════════════════════════════════════════════


class AiResponse(BaseModel):
    """모든 AI API의 공통 응답 형식."""
    model_config = {"protected_namespaces": ()}

    result_code: str = "OK"
    trace_id: str = ""
    model_version: str = MODEL_VERSION
    result: Any = None
    error: Optional[Dict[str, str]] = None


def _ok(data: Any, trace_id: str = "") -> AiResponse:
    return AiResponse(
        result_code="OK",
        trace_id=trace_id or _gen_trace(),
        result=data,
    )


def _fail(code: str, message: str, trace_id: str = "") -> AiResponse:
    return AiResponse(
        result_code=code,
        trace_id=trace_id or _gen_trace(),
        error={"code": code, "message": message},
    )


def _gen_trace() -> str:
    return f"tr-{uuid.uuid4().hex[:12]}"


# ═══════════════════════════════════════════════════════════════
#  Pydantic 요청 스키마
# ═══════════════════════════════════════════════════════════════


class OcrNormalizeRequest(BaseModel):
    product_names: List[str] = Field(..., min_length=1)


class RecommendRequest(BaseModel):
    ingredientIds: List[str] = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)
    category: Optional[str] = None
    cookingMethod: Optional[str] = Field(
        default=None,
        description="조리방법 필터 — 한글명(끓이기, 굽기 등) 또는 코드(BOIL, GRILL 등)",
    )
    mode: str = Field(
        default="partial",
        description="partial: 부족 재료 50%까지 허용, exact: 보유 재료만 사용",
    )
    min_match_rate: float = Field(default=0.0, ge=0.0, le=1.0)


class ExpiryRequest(BaseModel):
    item_name: str
    purchase_date: str = Field(description="YYYY-MM-DD")
    storage_method: str = Field(default="냉장")
    category: Optional[str] = None


class ExpiryBatchRequest(BaseModel):
    items: List[ExpiryRequest]


class SharingCheckRequest(BaseModel):
    item_names: List[str] = Field(..., min_length=1)


class ExplainRequest(BaseModel):
    recipeId: str
    ingredientIds: List[str] = Field(..., min_length=1)


# ═══════════════════════════════════════════════════════════════
#  유틸리티
# ═══════════════════════════════════════════════════════════════


def _normalize_name(name: str) -> str:
    s = unicodedata.normalize("NFC", name.strip().lower())
    s = re.sub(r"[^\w가-힣]", "", s)
    return s


def _similarity(a: str, b: str) -> float:
    na, nb = _normalize_name(a), _normalize_name(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.9
    return SequenceMatcher(None, na, nb).ratio()


def _match_product_to_ingredient(product_name: str) -> Optional[Dict[str, Any]]:
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
    scored = []
    for ingr in _ingredients_raw:
        s = _similarity(product_name, ingr["ingredientName"])
        if s >= 0.3:
            scored.append((s, ingr["ingredientName"]))
    scored.sort(key=lambda x: -x[0])
    return [name for _, name in scored[:top_n]]


def _merge_rule_and_qwen(
    rule_items: List[Dict[str, Any]], qwen_items: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    rule_names = {
        _normalize_name(it.get("product_name", "")): i
        for i, it in enumerate(rule_items)
    }
    merged = list(rule_items)

    for qwen_it in qwen_items:
        q_name = qwen_it.get("product_name", "").strip()
        if not q_name:
            continue
        q_norm = _normalize_name(q_name)

        matched_idx = rule_names.get(q_norm)
        if matched_idx is not None:
            if qwen_it.get("amount_krw") and not merged[matched_idx].get("amount_krw"):
                merged[matched_idx]["amount_krw"] = qwen_it["amount_krw"]
            if qwen_it.get("notes"):
                existing_notes = merged[matched_idx].get("notes", "")
                if existing_notes:
                    merged[matched_idx]["notes"] = f"{existing_notes}; Qwen: {qwen_it['notes']}"
                else:
                    merged[matched_idx]["notes"] = f"Qwen: {qwen_it['notes']}"
            continue

        found = False
        for rn in rule_names:
            if q_norm in rn or rn in q_norm:
                found = True
                break
        if found:
            continue

        cat = _normalizer.classify_category(q_name)
        ingr_match = _normalizer.match_to_ingredient(q_name)
        merged.append({
            "product_name_raw": q_name,
            "product_name": q_name,
            "category_major": cat["major"],
            "category_sub": cat["sub"],
            "amount_krw": qwen_it.get("amount_krw"),
            "ingredient_match": ingr_match,
            "notes": f"Qwen 추가: {qwen_it.get('notes', '')}".strip(),
        })

    return merged


# ═══════════════════════════════════════════════════════════════
#  로깅 미들웨어
# ═══════════════════════════════════════════════════════════════


@app.middleware("http")
async def monitor_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    elapsed_ms = (time.time() - start) * 1000
    endpoint = request.url.path
    if endpoint.startswith("/ai/v1"):
        _monitor.log_request(
            endpoint=endpoint,
            elapsed_ms=elapsed_ms,
            status_code=response.status_code,
            trace_id=response.headers.get("X-Trace-Id", ""),
        )
    return response


# ═══════════════════════════════════════════════════════════════
#  1. 헬스체크
# ═══════════════════════════════════════════════════════════════


@app.get("/ai/v1/health")
async def health_check():
    return _ok({
        "status": "healthy",
        "version": MODEL_VERSION,
        "uptime": _monitor.get_uptime(),
        "services": {
            "paddleocr": "available",
            "rule_based_normalizer": "active (v1)",
            "recipe_recommender": "active (weighted_scoring_v1)",
            "expiry_calculator": "active (gpt4omini + rule_fallback)",
            "sharing_filter": "active (v1)",
            "qwen_llm": "optional",
        },
        "stats": {
            "total_recipes": len(RECIPES),
            "total_ingredients": len(INGREDIENTS),
            "total_recipe_ingredients": len(_recipe_ingredients_raw),
            "total_recipe_steps": len(_recipe_steps_raw),
        },
    })


# ═══════════════════════════════════════════════════════════════
#  2. OCR 파이프라인 (3단계 분리)
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/v1/ocr/preprocess")
async def ocr_preprocess(
    image: UploadFile = File(...),
    use_qwen: bool = False,
):
    """
    1단계: 영수증 이미지 → PaddleOCR → 원시 텍스트 추출.
    비동기 job 생성 후 job_id 반환.
    """
    trace_id = _gen_trace()

    if image.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=400, detail=_fail(
            "INVALID_IMAGE", "jpg, png 파일만 지원합니다.", trace_id,
        ).model_dump())

    suffix = ".jpg" if "jpeg" in (image.content_type or "") else ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await image.read()
        tmp.write(content)
        tmp_path = tmp.name

    job_id = f"ocr-{uuid.uuid4().hex[:8]}"

    try:
        from receipt_ocr import ReceiptOCR

        ocr = ReceiptOCR()
        analysis = ocr.analyze_receipt(tmp_path)
        ocr_texts = analysis.get("all_texts", [])

        rule_result = _normalizer.process(analysis)
        food_items = rule_result["items"]
        model_name = rule_result["model"]

        if use_qwen:
            try:
                from qwen_receipt_assistant import QwenReceiptAssistant
                assistant = QwenReceiptAssistant()
                refined = assistant.refine_analysis(analysis)
                qwen_items = refined.get("items", [])
                if qwen_items:
                    food_items = _merge_rule_and_qwen(food_items, qwen_items)
                    model_name = f"rule_based_v1 + {refined.get('model', 'qwen')}"
            except Exception as e:
                model_name = f"rule_based_v1 (Qwen 보강 실패: {e})"

        _jobs[job_id] = {
            "job_id": job_id,
            "status": "completed",
            "created_at": datetime.now().isoformat(),
            "completed_at": datetime.now().isoformat(),
            "result": {
                "ocr_texts": ocr_texts,
                "food_items": food_items,
                "food_count": len(food_items),
                "model": model_name,
                "store_name": rule_result.get("store_name"),
                "purchase_date": rule_result.get("purchase_date"),
            },
        }

        return _ok({
            "job_id": job_id,
            "status": "completed",
            "ocr_texts": ocr_texts,
            "food_items": food_items,
            "food_count": len(food_items),
            "model": model_name,
            "store_name": rule_result.get("store_name"),
            "purchase_date": rule_result.get("purchase_date"),
        }, trace_id)

    except ImportError:
        raise HTTPException(status_code=503, detail=_fail(
            "SERVICE_UNAVAILABLE", "PaddleOCR가 설치되지 않았습니다.", trace_id,
        ).model_dump())
    except Exception as e:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "failed",
            "created_at": datetime.now().isoformat(),
            "error": str(e),
        }
        raise HTTPException(status_code=500, detail=_fail(
            "OCR_FAILED", str(e), trace_id,
        ).model_dump())
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.post("/ai/v1/ocr/extract-lines")
async def ocr_extract_lines(req: OcrNormalizeRequest):
    """
    2단계: 텍스트 목록 → OCR 보정 → 라인 분류 → 상품-가격 페어링.
    """
    trace_id = _gen_trace()
    lines = []
    for raw_text in req.product_names:
        corrected = _normalizer.correct_ocr_errors(raw_text)
        line_type = _normalizer.classify_line(corrected)
        lines.append({
            "raw": raw_text,
            "corrected": corrected,
            "line_type": line_type,
            "ocr_changed": corrected != raw_text,
        })

    return _ok({"lines": lines, "line_count": len(lines)}, trace_id)


@app.post("/ai/v1/ocr/normalize")
async def ocr_normalize(req: OcrNormalizeRequest):
    """
    3단계: 상품명 목록 → 정규화 → 카테고리 분류 → DB 매칭.
    """
    trace_id = _gen_trace()
    items = []
    for raw_name in req.product_names:
        corrected = _normalizer.correct_ocr_errors(raw_name)
        normalized = _normalizer.normalize_product_name(corrected)
        if not normalized or len(normalized) < 2:
            continue
        cat = _normalizer.classify_category(normalized)
        ingr_match = _normalizer.match_to_ingredient(normalized)
        items.append({
            "product_name_raw": raw_name,
            "product_name": normalized,
            "category_major": cat["major"],
            "category_sub": cat["sub"],
            "ingredient_match": ingr_match,
            "confidence": ingr_match["similarity"] if ingr_match else 0.0,
            "needs_review": (ingr_match["similarity"] < 0.7) if ingr_match else True,
            "notes": f"OCR 보정: {raw_name} → {corrected}" if corrected != raw_name else "",
        })

    return _ok({
        "items": items,
        "item_count": len(items),
        "model": "rule_based_v1",
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  3. 재료 매칭
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/v1/ingredients/match")
async def match_ingredients(req: OcrNormalizeRequest):
    """OCR 추출 상품명 → DB Ingredient 매칭."""
    trace_id = _gen_trace()
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

    return _ok({
        "matched": matched,
        "unmatched": unmatched,
        "matched_count": len(matched),
        "unmatched_count": len(unmatched),
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  4. 레시피 추천 (candidates + explanations 분리)
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/v1/recommendations/candidates")
async def recommend_candidates(req: RecommendRequest):
    """
    보유 재료 기반 레시피 추천 후보 목록.

    mode:
      - partial: 부족 재료가 전체의 50% 이하인 레시피까지 허용
      - exact:   보유 재료만으로 만들 수 있는 레시피만
    """
    trace_id = _gen_trace()
    valid_ids = [iid for iid in req.ingredientIds if iid in INGREDIENTS]
    if not valid_ids:
        raise HTTPException(status_code=400, detail=_fail(
            "INVALID_REQUEST", "유효한 ingredientId가 없습니다.", trace_id,
        ).model_dump())

    if req.mode == "exact":
        min_match = max(req.min_match_rate, 1.0)
    elif req.mode == "partial":
        min_match = max(req.min_match_rate, 0.5)
    else:
        min_match = req.min_match_rate

    recommendations = _recommender.recommend(
        ingredient_ids=valid_ids,
        top_k=req.top_k,
        category=req.category,
        cooking_method=req.cookingMethod,
        min_match_rate=min_match,
    )

    return _ok({
        "recommendations": recommendations,
        "total_count": len(recommendations),
        "input_ingredient_count": len(valid_ids),
        "mode": req.mode,
    }, trace_id)


@app.post("/ai/v1/recommendations/explanations")
async def recommend_explanations(req: ExplainRequest):
    """특정 레시피에 대한 추천 이유를 상세히 설명한다."""
    trace_id = _gen_trace()
    valid_ids = [iid for iid in req.ingredientIds if iid in INGREDIENTS]
    if not valid_ids:
        raise HTTPException(status_code=400, detail=_fail(
            "INVALID_REQUEST", "유효한 ingredientId가 없습니다.", trace_id,
        ).model_dump())

    recipe = RECIPES.get(req.recipeId)
    if not recipe:
        raise HTTPException(status_code=404, detail=_fail(
            "RECIPE_NOT_FOUND", f"레시피를 찾을 수 없습니다: {req.recipeId}", trace_id,
        ).model_dump())

    scored = _recommender._score_recipe(req.recipeId, set(valid_ids))
    if scored is None:
        return _ok({
            "recipeId": req.recipeId,
            "explanation": "이 레시피와 보유 재료 사이에 일치하는 재료가 없습니다.",
            "score": 0.0,
        }, trace_id)

    explanation = _recommender.explain(scored)

    return _ok({
        "recipeId": req.recipeId,
        "name": scored["name"],
        "explanation": explanation,
        "score": scored["score"],
        "matchRate": scored["matchRate"],
        "weightedMatchRate": scored["weightedMatchRate"],
        "coreCoverage": scored["coreCoverage"],
        "feasibility": scored["feasibility"],
        "matchedIngredients": scored["matchedIngredients"],
        "missingIngredients": scored["missingIngredients"],
        "substitutions": scored["substitutions"],
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  5. 레시피 상세
# ═══════════════════════════════════════════════════════════════


@app.get("/ai/v1/recipes/{recipe_id}")
async def get_recipe(recipe_id: str):
    """레시피 상세 조회 (재료 + 조리 단계)."""
    trace_id = _gen_trace()
    recipe = RECIPES.get(recipe_id)
    if not recipe:
        raise HTTPException(status_code=404, detail=_fail(
            "RECIPE_NOT_FOUND",
            f"레시피를 찾을 수 없습니다: {recipe_id}",
            trace_id,
        ).model_dump())

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

    return _ok({
        "recipeId": recipe_id,
        "name": recipe["name"],
        "category": recipe["category"],
        "cookingMethod": recipe.get("cookingMethod", ""),
        "cookingMethodCode": recipe.get("cookingMethodCode", ""),
        "imageUrl": recipe.get("imageUrl", ""),
        "ingredients": ingredients,
        "steps": steps,
        "ingredient_count": len(ingredients),
        "step_count": len(steps),
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  6. 소비기한 계산
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/v1/expiry/calculate")
async def calculate_expiry(req: ExpiryRequest):
    """단일 품목 소비기한 계산 (GPT-4o-mini + 규칙 기반 fallback)."""
    trace_id = _gen_trace()
    result = _expiry_calc.calculate(
        item_name=req.item_name,
        purchase_date=req.purchase_date,
        storage_method=req.storage_method,
        category=req.category,
    )
    return _ok(result, trace_id)


@app.post("/ai/v1/expiry/batch")
async def calculate_expiry_batch(req: ExpiryBatchRequest):
    """여러 품목 소비기한 일괄 계산."""
    trace_id = _gen_trace()
    items = [
        {
            "item_name": it.item_name,
            "purchase_date": it.purchase_date,
            "storage_method": it.storage_method,
            "category": it.category,
        }
        for it in req.items
    ]
    results = _expiry_calc.calculate_batch(items)
    alerts = _expiry_calc.generate_alerts(results)

    return _ok({
        "results": results,
        "total_count": len(results),
        "alerts": alerts,
        "alert_count": len(alerts),
    }, trace_id)


@app.post("/ai/v1/expiry/alerts")
async def expiry_alerts(req: ExpiryBatchRequest):
    """소비기한 임박 품목 알림 트리거."""
    trace_id = _gen_trace()
    items = [
        {
            "item_name": it.item_name,
            "purchase_date": it.purchase_date,
            "storage_method": it.storage_method,
            "category": it.category,
        }
        for it in req.items
    ]
    results = _expiry_calc.calculate_batch(items)
    alerts = _expiry_calc.generate_alerts(results, threshold_days=3)

    return _ok({
        "alerts": alerts,
        "alert_count": len(alerts),
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  7. 나눔 금지 품목 필터링
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/v1/sharing/check")
async def sharing_check(req: SharingCheckRequest):
    """나눔 금지 품목 1차 필터링 — 차단/검수/허용 판별."""
    trace_id = _gen_trace()
    result = _sharing_filter.check(req.item_names)
    return _ok(result, trace_id)


# ═══════════════════════════════════════════════════════════════
#  8. 재료 검색 / 조리방법
# ═══════════════════════════════════════════════════════════════


@app.get("/ai/v1/ingredients/search")
async def search_ingredients(
    q: str = Query(..., min_length=1, description="검색 키워드"),
    category: Optional[str] = Query(None, description="카테고리 필터"),
    limit: int = Query(20, ge=1, le=100, description="최대 반환 개수"),
):
    """키워드로 재료 검색."""
    trace_id = _gen_trace()
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

    return _ok({
        "results": results,
        "total_count": len(results),
        "query": q,
    }, trace_id)


@app.get("/ai/v1/cooking-methods")
async def list_cooking_methods():
    """사용 가능한 조리방법 목록과 각 레시피 수를 반환."""
    trace_id = _gen_trace()
    method_counts: Counter = Counter()
    for recipe in _recipes_raw:
        m = recipe.get("cookingMethod", "")
        c = recipe.get("cookingMethodCode", "")
        if m:
            method_counts[(m, c)] += 1

    methods = [
        {"name": name, "code": code, "recipeCount": cnt}
        for (name, code), cnt in method_counts.most_common()
    ]

    return _ok({
        "methods": methods,
        "total_count": len(methods),
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  9. 작업(Job) 관리
# ═══════════════════════════════════════════════════════════════


@app.get("/ai/v1/jobs/{job_id}")
async def get_job(job_id: str):
    """비동기 작업 상태 조회."""
    trace_id = _gen_trace()
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=_fail(
            "JOB_NOT_FOUND", f"작업을 찾을 수 없습니다: {job_id}", trace_id,
        ).model_dump())
    return _ok(job, trace_id)


@app.get("/ai/v1/jobs")
async def list_jobs(
    status: Optional[str] = Query(None, description="상태 필터 (completed, failed, processing)"),
    limit: int = Query(20, ge=1, le=100),
):
    """작업 목록 조회."""
    trace_id = _gen_trace()
    jobs = list(_jobs.values())
    if status:
        jobs = [j for j in jobs if j.get("status") == status]
    jobs.sort(key=lambda j: j.get("created_at", ""), reverse=True)
    return _ok({
        "jobs": jobs[:limit],
        "total_count": len(jobs),
    }, trace_id)


# ═══════════════════════════════════════════════════════════════
#  10. 운영/품질 관리 API
# ═══════════════════════════════════════════════════════════════


@app.get("/ai/v1/quality/metrics")
async def quality_metrics(
    window: str = Query("1h", description="시간 윈도우 (1h, 6h, 1d, 7d)"),
):
    """품질 지표 — 요청 수, 오류율, 응답시간."""
    trace_id = _gen_trace()
    metrics = _monitor.get_metrics(window)
    return _ok(metrics, trace_id)


@app.get("/ai/v1/quality/drift")
async def quality_drift(
    window: str = Query("7d", description="모니터링 윈도우"),
):
    """품질 드리프트 감지."""
    trace_id = _gen_trace()
    drift = _monitor.get_drift(window)
    return _ok(drift, trace_id)


@app.get("/ai/v1/quality/errors")
async def quality_errors(
    limit: int = Query(50, ge=1, le=500),
):
    """최근 오류 로그."""
    trace_id = _gen_trace()
    errors = _monitor.get_recent_errors(limit)
    return _ok({"errors": errors, "total_count": len(errors)}, trace_id)


@app.get("/ai/v1/models/version")
async def model_version():
    """현재 모델 버전 정보."""
    trace_id = _gen_trace()
    return _ok(_monitor.get_model_version(), trace_id)


@app.get("/ai/v1/dictionaries/version")
async def dict_version():
    """품목 사전 버전 정보."""
    trace_id = _gen_trace()
    return _ok(_monitor.get_dict_version(), trace_id)


@app.patch("/ai/v1/dictionaries/reload")
async def dict_reload():
    """품목 사전을 다시 로드한다."""
    trace_id = _gen_trace()
    global _normalizer
    _normalizer = RuleBasedNormalizer()
    return _ok({"message": "사전이 새로 로드되었습니다."}, trace_id)


@app.get("/ai/v1/prompts/version")
async def prompt_version():
    """프롬프트 템플릿 버전 정보."""
    trace_id = _gen_trace()
    return _ok(_monitor.get_prompt_version(), trace_id)


@app.get("/ai/v1/thresholds")
async def get_thresholds():
    """현재 임계값 설정 조회."""
    trace_id = _gen_trace()
    return _ok(_monitor.get_thresholds(), trace_id)


@app.patch("/ai/v1/thresholds")
async def update_thresholds(updates: Dict[str, Any]):
    """임계값 설정 업데이트."""
    trace_id = _gen_trace()
    result = _monitor.update_thresholds(updates)
    return _ok(result, trace_id)


@app.get("/ai/v1/fallback/policies")
async def get_fallback_policies():
    """Fallback 정책 목록 조회."""
    trace_id = _gen_trace()
    return _ok(_monitor.get_fallback_policies(), trace_id)


@app.patch("/ai/v1/fallback/policies/{policy_id}")
async def update_fallback_policy(policy_id: str, updates: Dict[str, Any]):
    """특정 Fallback 정책 업데이트."""
    trace_id = _gen_trace()
    result = _monitor.update_fallback_policy(policy_id, updates)
    if result is None:
        raise HTTPException(status_code=404, detail=_fail(
            "POLICY_NOT_FOUND", f"정책을 찾을 수 없습니다: {policy_id}", trace_id,
        ).model_dump())
    return _ok(result, trace_id)


@app.delete("/ai/v1/cache/clear")
async def cache_clear():
    """AI 서버 캐시 초기화."""
    trace_id = _gen_trace()
    _cache.clear()
    return _ok({"message": "캐시가 초기화되었습니다."}, trace_id)


# ═══════════════════════════════════════════════════════════════
#  백엔드 팀 연동 API (실제 Spring Boot가 호출하는 엔드포인트)
# ═══════════════════════════════════════════════════════════════


@app.post("/ai/ocr/analyze")
async def ocr_analyze(image: UploadFile = File(...)):
    """
    영수증 OCR 분석 — PaddleOCR + 규칙 보정 + Qwen 1차 보정.
    DB 매칭 없이 식품명 리스트만 반환한다.
    """
    trace_id = _gen_trace()

    if image.content_type not in ("image/jpeg", "image/png", "image/jpg"):
        raise HTTPException(status_code=400, detail=_fail(
            "INVALID_IMAGE", "jpg, png 파일만 지원합니다.", trace_id,
        ).model_dump())

    suffix = ".jpg" if "jpeg" in (image.content_type or "") else ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await image.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        from receipt_ocr import ReceiptOCR

        ocr = ReceiptOCR()
        analysis = ocr.analyze_receipt(tmp_path)
        ocr_texts = analysis.get("all_texts", [])

        rule_result = _normalizer.process(analysis, match_db=False)
        food_items = rule_result["items"]
        model_name = rule_result["model"]

        try:
            from qwen_receipt_assistant import QwenReceiptAssistant
            assistant = QwenReceiptAssistant()
            refined = assistant.refine_analysis(analysis)
            qwen_items = refined.get("items", [])
            if qwen_items:
                food_items = _merge_rule_and_qwen(food_items, qwen_items)
                model_name = f"rule_based_v1 + {refined.get('model', 'qwen')}"
        except Exception:
            pass

        items = []
        for it in food_items:
            items.append({
                "name": it.get("product_name", it.get("product_name_raw", "")),
                "category": it.get("category_major", ""),
                "price": it.get("amount_krw"),
            })

        return _ok({
            "items": items,
            "item_count": len(items),
            "store_name": rule_result.get("store_name"),
            "purchase_date": rule_result.get("purchase_date"),
            "model": model_name,
        }, trace_id)

    except ImportError:
        raise HTTPException(status_code=503, detail=_fail(
            "SERVICE_UNAVAILABLE", "PaddleOCR가 설치되지 않았습니다.", trace_id,
        ).model_dump())
    except Exception as e:
        raise HTTPException(status_code=500, detail=_fail(
            "OCR_FAILED", str(e), trace_id,
        ).model_dump())
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@app.get("/ai/ingredient/prediction")
async def ingredient_prediction(
    name: str = Query(..., description="식재료명"),
    purchase_date: str = Query(..., description="구매일 (YYYY-MM-DD)"),
    storage: str = Query("냉장", description="보관방법 (냉장/냉동/상온)"),
):
    """
    소비기한 계산 — GPT-4o-mini + 규칙 기반 fallback.
    """
    trace_id = _gen_trace()
    result = _expiry_calc.calculate(
        item_name=name,
        purchase_date=purchase_date,
        storage_method=storage,
    )
    return _ok(result, trace_id)
