"""
AI FastAPI 서버 — 영수증 OCR 분석 + 재료 예측

실행: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from __future__ import annotations

import json
import re
import tempfile
import threading
import time
import unicodedata
from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover - optional local convenience only
    load_dotenv = None

if load_dotenv is not None:
    PROJECT_DIR = Path(__file__).resolve().parent
    load_dotenv(PROJECT_DIR / ".env.local")
    load_dotenv(PROJECT_DIR / ".env")

# ═══════════════════════════════════════════════════════════════
#  데이터 로드
# ═══════════════════════════════════════════════════════════════

DATA_DIR = Path(__file__).resolve().parent / "data" / "db"

def _load_json(name: str) -> list:
    with open(DATA_DIR / name, encoding="utf-8") as f:
        return json.load(f)

_ingredients_raw: list = _load_json("ingredients.json")

INGREDIENTS: Dict[str, dict] = {i["ingredientId"]: i for i in _ingredients_raw}

INGR_NAME_INDEX: Dict[str, str] = {
    i["ingredientName"]: i["ingredientId"] for i in _ingredients_raw
}

# ═══════════════════════════════════════════════════════════════
#  FastAPI 앱
# ═══════════════════════════════════════════════════════════════

app = FastAPI(
    title="영수증 OCR / 재료 예측 AI API",
    version="1.0.0",
    description="영수증 OCR 분석과 재료 예측을 제공하는 AI API",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def notion_error_contract_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("code") or "ERROR")
        result = str(detail.get("message") or detail.get("result") or exc.status_code)
    else:
        code = "ERROR"
        result = str(detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"success": False, "code": code, "result": result},
    )

_RECEIPT_BACKEND = None
_RECEIPT_PARSER = None
_RECEIPT_SERVICE_NOOP = None
_RECEIPT_SERVICE_QWEN = None
_RECEIPT_REFINEMENT_STORE = None
_RECEIPT_RULES = None
_SHARING_FILTER = None
_INGREDIENT_PREDICTION_SERVICE = None
_QUALITY_MONITOR = None

# ═══════════════════════════════════════════════════════════════
#  Pydantic 스키마
# ═══════════════════════════════════════════════════════════════

class MatchRequest(BaseModel):
    product_names: List[str] = Field(..., min_length=1)


class SharingCheckRequest(BaseModel):
    item_names: List[str] = Field(..., min_length=1)


class ExpiryRequest(BaseModel):
    item_name: str
    purchase_date: str
    storage_method: str = "냉장"
    category: Optional[str] = None


def _extract_batch_ingredient_name(raw_ingredient: Any) -> str:
    if isinstance(raw_ingredient, str):
        return raw_ingredient
    if isinstance(raw_ingredient, dict):
        return str(raw_ingredient.get("ingredientName") or raw_ingredient.get("item_name") or "").strip()
    return ""


def _is_notion_prediction_payload(payload: dict[str, Any]) -> bool:
    return "purchaseDate" in payload and isinstance(payload.get("ingredients"), list)

class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    error: Optional[Dict[str, str]] = None


class ReceiptRefinementStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._records: dict[str, dict[str, Any]] = {}

    def clear(self) -> None:
        with self._lock:
            self._records.clear()

    def create_pending(self, trace_id: str, base_parsed: dict[str, Any]) -> None:
        now = _utc_now_isoformat()
        with self._lock:
            self._records[trace_id] = {
                "trace_id": trace_id,
                "status": "pending",
                "created_at": now,
                "updated_at": now,
                "base_parsed": dict(base_parsed),
                "refined_parsed": None,
                "error": None,
            }

    def mark_running(self, trace_id: str) -> None:
        with self._lock:
            record = self._records.get(trace_id)
            if record is None:
                return
            record["status"] = "running"
            record["updated_at"] = _utc_now_isoformat()

    def mark_completed(self, trace_id: str, refined_parsed: dict[str, Any]) -> None:
        with self._lock:
            record = self._records.get(trace_id)
            if record is None:
                return
            record["status"] = "completed"
            record["updated_at"] = _utc_now_isoformat()
            record["refined_parsed"] = dict(refined_parsed)
            record["error"] = None

    def mark_failed(self, trace_id: str, error: str) -> None:
        with self._lock:
            record = self._records.get(trace_id)
            if record is None:
                return
            record["status"] = "failed"
            record["updated_at"] = _utc_now_isoformat()
            record["error"] = error

    def get(self, trace_id: str) -> dict[str, Any] | None:
        with self._lock:
            record = self._records.get(trace_id)
            return dict(record) if record is not None else None

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


def _get_receipt_rules():
    global _RECEIPT_RULES
    if _RECEIPT_RULES is None:
        from ocr_qwen.receipt_rules import ReceiptRules

        _RECEIPT_RULES = ReceiptRules.load_default()
    return _RECEIPT_RULES


def _get_sharing_filter():
    global _SHARING_FILTER
    if _SHARING_FILTER is None:
        from sharing_filter import SharingFilter

        _SHARING_FILTER = SharingFilter()
    return _SHARING_FILTER


def _get_ingredient_prediction_service():
    global _INGREDIENT_PREDICTION_SERVICE
    if _INGREDIENT_PREDICTION_SERVICE is None:
        from ingredient_prediction_service import IngredientPredictionService

        _INGREDIENT_PREDICTION_SERVICE = IngredientPredictionService()
    return _INGREDIENT_PREDICTION_SERVICE


def _get_quality_monitor():
    global _QUALITY_MONITOR
    if _QUALITY_MONITOR is None:
        from quality_monitor import QualityMonitor

        _QUALITY_MONITOR = QualityMonitor()
    return _QUALITY_MONITOR


def _log_endpoint_request(endpoint: str, started_at: float, *, status_code: int = 200, error: str | None = None) -> None:
    try:
        elapsed_ms = (time.perf_counter() - started_at) * 1000.0
        _get_quality_monitor().log_request(
            endpoint=endpoint,
            elapsed_ms=elapsed_ms,
            status_code=status_code,
            error=error,
        )
    except Exception:
        pass


def _find_ingredient_by_name(candidate_name: str) -> dict[str, Any] | None:
    normalized_candidate = _normalize_name(candidate_name)
    for ingredient in _ingredients_raw:
        if _normalize_name(ingredient["ingredientName"]) == normalized_candidate:
            return ingredient
    return None


def _build_ingredient_match(
    *,
    original_product_name: str,
    ingredient: dict[str, Any],
    similarity: float,
    mapping_source: str,
    standard_product_name: str | None = None,
) -> Dict[str, Any]:
    return {
        "product_name": original_product_name,
        "ingredientId": ingredient["ingredientId"],
        "ingredientName": ingredient["ingredientName"],
        "category": ingredient["category"],
        "similarity": round(similarity, 4),
        "mapping_source": mapping_source,
        "standard_product_name": standard_product_name or original_product_name,
    }


def _match_product_to_ingredient(product_name: str) -> Dict[str, Any]:
    """상품명을 DB 재료와 매칭. 최고 유사도 재료를 반환."""
    rules = _get_receipt_rules()
    aliased_product_name = rules.apply_product_alias(product_name).strip() or product_name.strip()
    mapped = rules.lookup_product_to_ingredient(product_name)
    inferred_item_type = _infer_item_type(product_name, standard_product_name=aliased_product_name)

    if mapped is not None:
        mapped_ingredient = _find_ingredient_by_name(mapped["ingredient_name"])
        if mapped_ingredient is not None:
            return _build_ingredient_match(
                original_product_name=product_name,
                ingredient=mapped_ingredient,
                similarity=1.0,
                mapping_source="receipt_rule_product_mapping",
                standard_product_name=mapped["standard_product_name"],
            )

    best_score = 0.0
    best_ingr = None
    best_source = "fuzzy_similarity"
    best_standard_product_name = aliased_product_name
    candidate_names = [aliased_product_name]

    if mapped is not None:
        mapped_ingredient_name = str(mapped["ingredient_name"]).strip()
        if mapped_ingredient_name and mapped_ingredient_name not in candidate_names:
            candidate_names.insert(0, mapped_ingredient_name)
            best_standard_product_name = mapped["standard_product_name"]

    original_product_name = product_name.strip()
    if original_product_name and original_product_name not in candidate_names:
        candidate_names.append(original_product_name)

    for candidate_name in candidate_names:
        norm_product = _normalize_name(candidate_name)
        if not norm_product:
            continue

        for ingr in _ingredients_raw:
            ingr_name = ingr["ingredientName"]
            norm_ingr = _normalize_name(ingr_name)

            if norm_product == norm_ingr:
                return _build_ingredient_match(
                    original_product_name=product_name,
                    ingredient=ingr,
                    similarity=1.0,
                    mapping_source=(
                        "receipt_rule_product_mapping_fallback"
                        if mapped is not None and candidate_name == mapped.get("ingredient_name")
                        else "normalized_exact_match"
                    ),
                    standard_product_name=best_standard_product_name,
                )

            if min(len(norm_product), len(norm_ingr)) >= 2 and (
                norm_product in norm_ingr or norm_ingr in norm_product
            ):
                score = 0.9
            else:
                score = SequenceMatcher(None, norm_product, norm_ingr).ratio()

            if score > best_score:
                best_score = score
                best_ingr = ingr
                if mapped is not None and candidate_name == mapped.get("ingredient_name"):
                    best_source = "receipt_rule_product_mapping_fallback"
                elif candidate_name == aliased_product_name and aliased_product_name != original_product_name:
                    best_source = "product_alias_fuzzy_match"
                else:
                    best_source = "fuzzy_similarity"

    minimum_score = 0.8 if inferred_item_type == "SNACK" and mapped is None else 0.5
    if best_ingr and best_score >= minimum_score:
        return _build_ingredient_match(
            original_product_name=product_name,
            ingredient=best_ingr,
            similarity=best_score,
            mapping_source=best_source,
            standard_product_name=best_standard_product_name,
        )
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


SNACK_KEYWORDS = (
    "과자",
    "쿠키",
    "크래커",
    "초코",
    "빼빼로",
    "오예스",
    "붕어빵",
    "초코볼",
    "캔디",
    "사탕",
    "민트향",
    "헬씨넛",
    "로투스",
)

PROCESSED_FOOD_KEYWORDS = (
    "라면",
    "컵",
    "소스",
    "고추장",
    "요거트",
    "치즈",
    "와사비",
    "참기름",
    "양념",
    "주물럭",
    "햇반",
    "만두",
    "떡",
    "어묵",
    "캔",
)


def _resolve_standard_product_name(product_name: str) -> str:
    standard_name = _get_receipt_rules().apply_product_alias(product_name).strip()
    return standard_name or product_name.strip()


def _contains_classification_keyword(values: list[str], keywords: tuple[str, ...]) -> bool:
    return any(keyword in value for value in values for keyword in keywords)


def _infer_item_type(
    product_name: str,
    *,
    standard_product_name: str | None = None,
    matched_result: dict[str, Any] | None = None,
) -> str:
    candidate_values = [value.strip() for value in (product_name, standard_product_name or "") if value and value.strip()]
    rules = _get_receipt_rules()
    if any(rules.matches_non_item(value) for value in candidate_values):
        return "NON_FOOD"

    normalized_values = [_normalize_name(value) for value in candidate_values if value]
    if _contains_classification_keyword(normalized_values, SNACK_KEYWORDS):
        return "SNACK"
    if _contains_classification_keyword(normalized_values, PROCESSED_FOOD_KEYWORDS):
        return "PROCESSED_FOOD"

    if matched_result is not None:
        return "INGREDIENT"
    return "UNKNOWN"


def _normalize_prediction_match(product_name: str, match_result: dict[str, Any]) -> dict[str, Any]:
    result = dict(match_result)
    standard_product_name = str(result.get("standard_product_name") or _resolve_standard_product_name(product_name)).strip()
    result["product_name"] = product_name
    result["standard_product_name"] = standard_product_name
    result["mapping_status"] = "MAPPED"
    result["item_type"] = _infer_item_type(
        product_name,
        standard_product_name=standard_product_name,
        matched_result=result,
    )
    return result


def _build_unmatched_prediction(product_name: str) -> dict[str, Any]:
    standard_product_name = _resolve_standard_product_name(product_name)
    item_type = _infer_item_type(product_name, standard_product_name=standard_product_name)
    mapping_status = "EXCLUDED" if item_type == "NON_FOOD" else "UNMAPPED"
    reason = "비식품 또는 제외 대상" if mapping_status == "EXCLUDED" else "DB에 일치하는 재료 없음"

    return {
        "product_name": product_name,
        "standard_product_name": standard_product_name,
        "item_type": item_type,
        "mapping_status": mapping_status,
        "reason": reason,
        "suggestions": [] if mapping_status == "EXCLUDED" else _find_suggestions(standard_product_name),
    }


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

    category = _normalize_public_food_category(
        item.get("category"),
        product_name,
        normalized_name=str(item.get("normalized_name") or "").strip(),
    )

    return {
        "product_name": product_name,
        "category": category,
    }


def _normalize_food_items(items: list[Dict[str, Any]]) -> list[Dict[str, Any]]:
    normalized: list[Dict[str, Any]] = []
    for item in items:
        normalized_item = _normalize_food_item(item)
        if normalized_item is not None:
            normalized.append(normalized_item)
    return normalized


PUBLIC_FOOD_CATEGORY_MAP = {
    "정육/계란": "정육/계란",
    "해산물": "해산물",
    "채소/과일": "채소/과일",
    "유제품": "유제품",
    "쌀/면/빵": "쌀/면/빵",
    "소스/조미료/오일": "소스/조미료/오일",
    "가공식품": "가공식품",
    "기타": "기타",
    "meat": "정육/계란",
    "egg": "정육/계란",
    "seafood": "해산물",
    "vegetable": "채소/과일",
    "fruit": "채소/과일",
    "mushroom": "채소/과일",
    "dairy": "유제품",
    "grain": "쌀/면/빵",
    "sauce": "소스/조미료/오일",
    "tofu_bean": "가공식품",
    "frozen": "가공식품",
    "beverage": "가공식품",
    "nut": "기타",
    "other": "기타",
}

PUBLIC_FOOD_CATEGORY_KEYWORDS = (
    ("소스/조미료/오일", ("액젓", "간장", "고추장", "된장", "쌈장", "케찹", "케첩", "소스", "오일", "기름", "식초", "쯔유", "머스타드", "연겨자", "참기름", "올리고당", "물엿", "맛술", "미림", "청주")),
    ("유제품", ("우유", "치즈", "요거트", "버터", "생크림", "리코타")),
    ("정육/계란", ("소고기", "돼지고기", "닭고기", "삼겹살", "목살", "계란", "돈까스", "주물럭", "갈비")),
    ("해산물", ("새우", "오징어", "굴", "연어", "참치", "고등어", "멸치", "어묵", "맛살", "크래미")),
    ("채소/과일", ("양파", "대파", "마늘", "감자", "고구마", "당근", "오이", "김치", "깻잎", "부추", "브로콜리", "파프리카", "고추", "가지", "무", "상추", "청경채", "숙주", "콩나물", "애호박", "양배추", "시금치", "미나리", "봄동", "배추", "새싹", "토마토", "바나나", "사과", "레몬", "딸기", "아보카도")),
    ("쌀/면/빵", ("쌀", "밥", "밀가루", "빵가루", "소면", "당면", "떡", "식빵", "모닝빵", "또띠아", "우동면", "파스타면", "면", "빵")),
    ("가공식품", ("두부", "순두부", "라면", "햇반", "만두", "누룽지", "음료", "소주", "주스", "캔", "요리용", "삼각", "김밥")),
)


def _infer_public_food_category_from_text(*texts: str) -> str | None:
    normalized_texts = [_normalize_name(text) for text in texts if isinstance(text, str) and text.strip()]
    if not normalized_texts:
        return None
    for public_category, keywords in PUBLIC_FOOD_CATEGORY_KEYWORDS:
        if any(keyword in text for text in normalized_texts for keyword in keywords):
            return public_category
    return None


def _normalize_public_food_category(raw_category: Any, product_name: str, normalized_name: str = "") -> str:
    if isinstance(raw_category, str):
        normalized = PUBLIC_FOOD_CATEGORY_MAP.get(raw_category.strip())
        if normalized and normalized != "기타":
            return normalized

    heuristic_category = _infer_public_food_category_from_text(normalized_name, product_name)
    if heuristic_category:
        return heuristic_category

    for candidate_name in (normalized_name, product_name):
        if not candidate_name:
            continue
        matched = _match_product_to_ingredient(candidate_name)
        if isinstance(matched, dict):
            heuristic_category = _infer_public_food_category_from_text(
                str(matched.get("standard_product_name") or ""),
                str(matched.get("ingredientName") or ""),
                candidate_name,
            )
            if heuristic_category:
                return heuristic_category
            normalized = PUBLIC_FOOD_CATEGORY_MAP.get(str(matched.get("category") or "").strip())
            if normalized:
                return normalized

    try:
        from ocr_qwen.ingredient_dictionary import classify_ingredient_name

        inferred = classify_ingredient_name(normalized_name or product_name).get("category")
    except Exception:
        inferred = None

    if isinstance(inferred, str):
        normalized = PUBLIC_FOOD_CATEGORY_MAP.get(inferred.strip())
        if normalized:
            return normalized

    return "기타"


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
                "normalized_name": item.get("normalized_name"),
                "category": item.get("category"),
            }
        )
    return _normalize_food_items(legacy_items)


def _legacy_model_name_from_parsed(parsed: Dict[str, Any]) -> str:
    engine_version = str(parsed.get("engine_version") or "receipt-engine-v2")
    diagnostics = parsed.get("diagnostics", {})
    if isinstance(diagnostics, dict) and diagnostics.get("qwen_used"):
        return f"{engine_version}+qwen"
    return engine_version


def _legacy_ocr_response_data_from_parsed(parsed: Dict[str, Any]) -> Dict[str, Any]:
    ocr_texts = parsed.get("ocr_texts", [])
    food_items = _legacy_food_items_from_parsed(parsed)
    model_name = _legacy_model_name_from_parsed(parsed)
    return {
        "trace_id": parsed.get("trace_id"),
        "ocr_texts": ocr_texts,
        "food_items": food_items,
        "food_count": len(food_items),
        "model": model_name,
        "vendor_name": parsed.get("vendor_name"),
        "purchased_at": parsed.get("purchased_at"),
        "totals": parsed.get("totals", {}),
        "review_required": parsed.get("review_required"),
        "review_reasons": parsed.get("review_reasons", []),
        "diagnostics": parsed.get("diagnostics", {}),
    }


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _get_receipt_refinement_store() -> ReceiptRefinementStore:
    global _RECEIPT_REFINEMENT_STORE
    if _RECEIPT_REFINEMENT_STORE is None:
        _RECEIPT_REFINEMENT_STORE = ReceiptRefinementStore()
    return _RECEIPT_REFINEMENT_STORE


def _run_receipt_refinement(trace_id: str, temp_path: str) -> None:
    store = _get_receipt_refinement_store()
    try:
        store.mark_running(trace_id)
        parsed = _get_receipt_service(use_qwen=True).parse({"receipt_image_url": temp_path})
        parsed["trace_id"] = trace_id
        store.mark_completed(trace_id, parsed)
    except Exception as exc:
        store.mark_failed(trace_id, str(exc))
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _schedule_receipt_refinement(*, trace_id: str, image_bytes: bytes, suffix: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(image_bytes)
        temp_path = tmp.name

    thread = threading.Thread(
        target=_run_receipt_refinement,
        args=(trace_id, temp_path),
        daemon=True,
    )
    thread.start()


@app.on_event("startup")
def _warm_up_receipt_services() -> None:
    try:
        _get_receipt_backend().warm_up()
    except Exception as exc:
        print(f"[startup] receipt ocr warm-up skipped: {exc}")

# ═══════════════════════════════════════════════════════════════
#  API 엔드포인트
# ═══════════════════════════════════════════════════════════════

@app.post("/ai/ocr/analyze")
async def ocr_receipt(
    image: UploadFile = File(...),
    use_qwen: bool = Query(
        default=True,
        description=(
            "로컬 Qwen 보정 사용 여부. "
            "true여도 로컬 Qwen 런타임이 비활성화되어 있으면 OCR-only로 fallback하며, "
            "응답 계약(ocr_texts, food_items, food_count, model)은 유지됩니다."
        ),
    ),
    async_refinement: bool = Query(
        default=False,
        description="true면 rule-based 결과를 즉시 반환하고 Qwen 보정은 백그라운드에서 수행합니다.",
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
        should_enqueue_refinement = use_qwen and async_refinement
        service = _get_receipt_service(use_qwen=False if should_enqueue_refinement else use_qwen)
        parsed = service.parse({"receipt_image_url": tmp_path})
        data = _legacy_ocr_response_data_from_parsed(parsed)

        if should_enqueue_refinement:
            trace_id = str(parsed.get("trace_id") or "")
            if trace_id:
                _get_receipt_refinement_store().create_pending(trace_id, parsed)
                _schedule_receipt_refinement(trace_id=trace_id, image_bytes=content, suffix=suffix)
                data["refinement_status"] = "pending"
                data["refinement_poll_url"] = f"/ai/ocr/refinement/{trace_id}"

        return ApiResponse(
            success=True,
            data=data,
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


@app.get("/ai/ocr/refinement/{trace_id}")
async def get_ocr_refinement(trace_id: str):
    record = _get_receipt_refinement_store().get(trace_id)
    if record is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "REFINEMENT_NOT_FOUND", "message": f"refinement trace not found: {trace_id}"},
        )

    base_parsed = record.get("base_parsed")
    refined_parsed = record.get("refined_parsed")
    return ApiResponse(
        success=True,
        data={
            "trace_id": trace_id,
            "status": record.get("status"),
            "created_at": record.get("created_at"),
            "updated_at": record.get("updated_at"),
            "error": record.get("error"),
            "rule_based_result": _legacy_ocr_response_data_from_parsed(base_parsed) if isinstance(base_parsed, dict) else None,
            "refined_result": _legacy_ocr_response_data_from_parsed(refined_parsed) if isinstance(refined_parsed, dict) else None,
        },
    )


@app.post("/ai/ingredient/match")
async def match_ingredients(req: MatchRequest):
    """OCR 추출 상품명 → DB Ingredient 매칭."""
    started_at = time.perf_counter()
    matched = []
    unmatched = []

    for name in req.product_names:
        result = _match_product_to_ingredient(name)
        if result:
            matched.append(_normalize_prediction_match(name, result))
        else:
            unmatched.append(_build_unmatched_prediction(name))

    response = ApiResponse(
        success=True,
        data={
            "matched": matched,
            "unmatched": unmatched,
            "matched_count": len(matched),
            "unmatched_count": len(unmatched),
        },
    )
    _log_endpoint_request("/ai/ingredient/match", started_at, status_code=200)
    return response


@app.post("/ai/sharing/check")
async def check_sharing_items(req: SharingCheckRequest):
    """나눔 금지/검수/허용 품목을 1차 분류한다."""
    started_at = time.perf_counter()
    result = _get_sharing_filter().check(req.item_names)
    response = ApiResponse(success=True, data=result)
    _log_endpoint_request("/ai/sharing/check", started_at, status_code=200)
    return response


@app.api_route("/ai/ingredient/prediction", methods=["GET", "POST"])
async def calculate_expiry(request: Request):
    """소비기한을 계산한다.

    노션 명세의 배치 계약을 우선 지원하고, 기존 단건 POST 계약은 하위 호환으로 유지한다.
    """
    started_at = time.perf_counter()
    try:
        payload = await request.json()
    except Exception:
        payload = {}

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail={"code": "INVALID_REQUEST", "message": "JSON 객체 요청만 지원합니다."},
        )

    if _is_notion_prediction_payload(payload):
        purchase_date = str(payload.get("purchaseDate") or "").strip()
        if not purchase_date:
            raise HTTPException(
                status_code=400,
                detail={"code": "INVALID_REQUEST", "message": "purchaseDate는 필수입니다."},
            )

        predicted_ingredients = []
        for raw_ingredient in payload.get("ingredients", []):
            ingredient_name = _extract_batch_ingredient_name(raw_ingredient)
            if not ingredient_name:
                continue

            category = raw_ingredient.get("category") if isinstance(raw_ingredient, dict) else None
            storage_method = raw_ingredient.get("storageMethod") if isinstance(raw_ingredient, dict) else None
            result = _get_ingredient_prediction_service().calculate(
                item_name=ingredient_name,
                purchase_date=purchase_date,
                storage_method=str(storage_method or "냉장"),
                category=category,
            )
            predicted_ingredients.append(
                {
                    "ingredientName": ingredient_name,
                    "expirationDate": result.get("expiry_date"),
                }
            )

        response = {
            "success": True,
            "result": {
                "purchaseDate": purchase_date,
                "ingredients": predicted_ingredients,
            },
        }
        _log_endpoint_request("/ai/ingredient/prediction", started_at, status_code=200)
        return response

    req = ExpiryRequest(**payload)
    result = _get_ingredient_prediction_service().calculate(
        item_name=req.item_name,
        purchase_date=req.purchase_date,
        storage_method=req.storage_method,
        category=req.category,
    )
    response = ApiResponse(success=True, data=result)
    _log_endpoint_request("/ai/ingredient/prediction", started_at, status_code=200)
    return response


@app.get("/ai/quality/metrics")
async def get_quality_metrics(window: str = Query("1h", description="조회 윈도우. 예: 1h, 24h, 7d")):
    """현재 AI 서버 품질 지표 스냅샷을 반환한다."""
    started_at = time.perf_counter()
    result = _get_quality_monitor().get_metrics(window=window)
    response = ApiResponse(success=True, data=result)
    _log_endpoint_request("/ai/quality/metrics", started_at, status_code=200)
    return response
