# AI Server API 명세서 (설계서 v1.1)

> **Base URL**: `http://{host}:8000`  
> **API Prefix**: `/ai/v1`  
> **총 엔드포인트**: 28개

---

## 공통 응답 구조

모든 엔드포인트는 아래 JSON 구조로 응답합니다.

**성공 시:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": { ... },
  "error": null
}
```

**실패 시:**
```json
{
  "result_code": "INVALID_REQUEST",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": null,
  "error": {
    "code": "INVALID_REQUEST",
    "message": "유효한 ingredientId가 없습니다."
  }
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `result_code` | string | `"OK"` 또는 오류 코드 |
| `trace_id` | string | 요청 추적 ID (`tr-` 접두사) |
| `model_version` | string | AI 서버 버전 |
| `result` | object \| null | 정상 응답 데이터 |
| `error` | object \| null | `{code, message}` |

---

## 1. 헬스체크

### `GET /ai/v1/health`

서버 상태, 서비스 가용성, DB 통계를 반환합니다.

**요청**: 파라미터 없음

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "status": "healthy",
    "version": "ai-server-v1.1.0",
    "uptime": "2h 30m 15s",
    "services": {
      "paddleocr": "available",
      "rule_based_normalizer": "active (v1)",
      "recipe_recommender": "active (weighted_scoring_v1)",
      "expiry_calculator": "active (gpt4omini + rule_fallback)",
      "sharing_filter": "active (v1)",
      "qwen_llm": "optional"
    },
    "stats": {
      "total_recipes": 2054,
      "total_ingredients": 3408,
      "total_recipe_ingredients": 17885,
      "total_recipe_steps": 12540
    }
  },
  "error": null
}
```

---

## 2. OCR 파이프라인

### 2-1. `POST /ai/v1/ocr/preprocess`

영수증 이미지를 PaddleOCR로 텍스트 추출 후 규칙 기반 정규화를 수행합니다.

**요청**: `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `image` | file | O | jpg/png 영수증 이미지 |
| `use_qwen` | bool | X | Qwen LLM 보강 여부 (기본 false) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "job_id": "ocr-a1b2c3d4",
    "status": "completed",
    "ocr_texts": [
      { "text": "삼겹쌀 1,500", "confidence": 0.93 },
      { "text": "대퍄 2,000", "confidence": 0.89 },
      { "text": "합계 3,500", "confidence": 0.97 }
    ],
    "food_items": [
      {
        "product_name_raw": "삼겹쌀",
        "product_name": "삼겹살",
        "category_major": "축산물",
        "category_sub": "돼지고기",
        "amount_krw": 1500,
        "ingredient_match": {
          "ingredientId": "ING_0042",
          "ingredientName": "삼겹살",
          "category": "정육/계란",
          "similarity": 1.0
        },
        "notes": "OCR 보정: 삼겹쌀 → 삼겹살"
      },
      {
        "product_name_raw": "대퍄",
        "product_name": "대파",
        "category_major": "농산물",
        "category_sub": "채소",
        "amount_krw": 2000,
        "ingredient_match": {
          "ingredientId": "ING_0105",
          "ingredientName": "대파",
          "category": "채소/과일",
          "similarity": 1.0
        },
        "notes": "OCR 보정: 대퍄 → 대파"
      }
    ],
    "food_count": 2,
    "model": "rule_based_v1",
    "store_name": "이마트",
    "purchase_date": "2026-04-15"
  },
  "error": null
}
```

---

### 2-2. `POST /ai/v1/ocr/extract-lines`

텍스트 목록을 OCR 보정하고 라인 유형을 분류합니다.

**요청:**
```json
{
  "product_names": ["삼겹쌀 1,500", "합계", "2026-04-15", "========"]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-b2c3d4e5f6a1",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "lines": [
      {
        "raw": "삼겹쌀 1,500",
        "corrected": "삼겹살 1,500",
        "line_type": "product",
        "ocr_changed": true
      },
      {
        "raw": "합계",
        "corrected": "합계",
        "line_type": "header",
        "ocr_changed": false
      },
      {
        "raw": "2026-04-15",
        "corrected": "2026-04-15",
        "line_type": "date",
        "ocr_changed": false
      },
      {
        "raw": "========",
        "corrected": "========",
        "line_type": "separator",
        "ocr_changed": false
      }
    ],
    "line_count": 4
  },
  "error": null
}
```

---

### 2-3. `POST /ai/v1/ocr/normalize`

상품명을 정규화하고 카테고리 분류 및 DB 재료 매칭을 수행합니다.

**요청:**
```json
{
  "product_names": ["삼겹쌀", "대퍄", "깨잎"]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-c3d4e5f6a1b2",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "items": [
      {
        "product_name_raw": "삼겹쌀",
        "product_name": "삼겹살",
        "category_major": "축산물",
        "category_sub": "돼지고기",
        "ingredient_match": {
          "ingredientId": "ING_0042",
          "ingredientName": "삼겹살",
          "category": "정육/계란",
          "similarity": 1.0
        },
        "confidence": 1.0,
        "needs_review": false,
        "notes": "OCR 보정: 삼겹쌀 → 삼겹살"
      },
      {
        "product_name_raw": "대퍄",
        "product_name": "대파",
        "category_major": "농산물",
        "category_sub": "채소",
        "ingredient_match": {
          "ingredientId": "ING_0105",
          "ingredientName": "대파",
          "category": "채소/과일",
          "similarity": 1.0
        },
        "confidence": 1.0,
        "needs_review": false,
        "notes": "OCR 보정: 대퍄 → 대파"
      },
      {
        "product_name_raw": "깨잎",
        "product_name": "깻잎",
        "category_major": "농산물",
        "category_sub": "채소",
        "ingredient_match": {
          "ingredientId": "ING_0112",
          "ingredientName": "깻잎",
          "category": "채소/과일",
          "similarity": 1.0
        },
        "confidence": 1.0,
        "needs_review": false,
        "notes": "OCR 보정: 깨잎 → 깻잎"
      }
    ],
    "item_count": 3,
    "model": "rule_based_v1"
  },
  "error": null
}
```

---

## 3. 재료 매칭

### `POST /ai/v1/ingredients/match`

상품명을 DB 재료와 매칭합니다. 매칭 실패 시 유사 재료를 추천합니다.

**요청:**
```json
{
  "product_names": ["삼겹살", "알수없는재료"]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-d4e5f6a1b2c3",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "matched": [
      {
        "product_name": "삼겹살",
        "ingredientId": "ING_0042",
        "ingredientName": "삼겹살",
        "category": "정육/계란",
        "similarity": 1.0
      }
    ],
    "unmatched": [
      {
        "product_name": "알수없는재료",
        "reason": "DB에 일치하는 재료 없음",
        "suggestions": ["양배추", "양파", "양송이버섯"]
      }
    ],
    "matched_count": 1,
    "unmatched_count": 1
  },
  "error": null
}
```

---

## 4. 레시피 추천

### 4-1. `POST /ai/v1/recommendations/candidates`

보유 재료 기반 레시피 추천 후보 목록을 반환합니다.

**요청:**
```json
{
  "ingredientIds": ["ING_0042", "ING_0105", "ING_0003"],
  "top_k": 5,
  "category": null,
  "cookingMethod": null,
  "mode": "partial",
  "min_match_rate": 0.0
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `ingredientIds` | string[] | O | 보유 재료 ID 목록 |
| `top_k` | int | X | 반환할 최대 레시피 수 (기본 10, 최대 100) |
| `category` | string | X | 카테고리 필터 (한식, 양식 등) |
| `cookingMethod` | string | X | 조리방법 필터 — 한글명(`볶기`) 또는 코드(`STIRFRY`) |
| `mode` | string | X | `"partial"`: 부족 재료 50%까지 허용 / `"exact"`: 보유 재료만 |
| `min_match_rate` | float | X | 최소 단순 일치율 (0.0~1.0) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-e5f6a1b2c3d4",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "recommendations": [
      {
        "recipeId": "RCP_0158",
        "name": "제육볶음",
        "category": "한식",
        "cookingMethod": "볶기",
        "cookingMethodCode": "STIRFRY",
        "imageUrl": "https://...",
        "score": 0.8523,
        "matchRate": 0.75,
        "weightedMatchRate": 0.8214,
        "coreCoverage": 0.9,
        "feasibility": 0.8,
        "matchedIngredients": [
          { "ingredientId": "ING_0042", "ingredientName": "삼겹살", "category": "정육/계란" },
          { "ingredientId": "ING_0105", "ingredientName": "대파", "category": "채소/과일" }
        ],
        "missingIngredients": [
          { "ingredientId": "ING_0201", "ingredientName": "고추장", "category": "소스/조미료/오일" }
        ],
        "substitutions": [
          { "missing": "진간장", "substitutedBy": "간장" }
        ],
        "totalIngredientCount": 8,
        "missingCount": 1
      }
    ],
    "total_count": 5,
    "input_ingredient_count": 3,
    "mode": "partial"
  },
  "error": null
}
```

---

### 4-2. `POST /ai/v1/recommendations/explanations`

특정 레시피에 대한 추천 이유를 상세히 설명합니다.

**요청:**
```json
{
  "recipeId": "RCP_0158",
  "ingredientIds": ["ING_0042", "ING_0105", "ING_0003"]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-f6a1b2c3d4e5",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "recipeId": "RCP_0158",
    "name": "제육볶음",
    "explanation": "[제육볶음] 추천 점수 85% | 보유 재료: 삼겹살, 대파 외 1개 | 대체 가능: 진간장→간장 | 부족: 고추장",
    "score": 0.8523,
    "matchRate": 0.75,
    "weightedMatchRate": 0.8214,
    "coreCoverage": 0.9,
    "feasibility": 0.8,
    "matchedIngredients": [
      { "ingredientId": "ING_0042", "ingredientName": "삼겹살", "category": "정육/계란" },
      { "ingredientId": "ING_0105", "ingredientName": "대파", "category": "채소/과일" }
    ],
    "missingIngredients": [
      { "ingredientId": "ING_0201", "ingredientName": "고추장", "category": "소스/조미료/오일" }
    ],
    "substitutions": [
      { "missing": "진간장", "substitutedBy": "간장" }
    ]
  },
  "error": null
}
```

---

## 5. 레시피 상세

### `GET /ai/v1/recipes/{recipe_id}`

레시피 상세 정보 (재료 목록 + 조리 단계)를 반환합니다.

**요청**: `GET /ai/v1/recipes/RCP_0158`

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-1a2b3c4d5e6f",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "recipeId": "RCP_0158",
    "name": "제육볶음",
    "category": "한식",
    "cookingMethod": "볶기",
    "cookingMethodCode": "STIRFRY",
    "imageUrl": "https://...",
    "ingredients": [
      {
        "recipeIngredientId": "RI_001",
        "ingredientId": "ING_0042",
        "ingredientName": "삼겹살",
        "category": "정육/계란",
        "amount": "300",
        "unit": "g"
      },
      {
        "recipeIngredientId": "RI_002",
        "ingredientId": "ING_0105",
        "ingredientName": "대파",
        "category": "채소/과일",
        "amount": "1",
        "unit": "대"
      }
    ],
    "steps": [
      {
        "recipeStepId": "RS_001",
        "stepOrder": 1,
        "description": "삼겹살을 한입 크기로 자른다."
      },
      {
        "recipeStepId": "RS_002",
        "stepOrder": 2,
        "description": "양념장에 30분간 재운다."
      }
    ],
    "ingredient_count": 2,
    "step_count": 2
  },
  "error": null
}
```

---

## 6. 소비기한 계산

### 6-1. `POST /ai/v1/expiry/calculate`

단일 품목의 소비기한을 계산합니다. GPT-4o-mini 우선 시도, 실패 시 규칙 기반 fallback.

**요청:**
```json
{
  "item_name": "삼겹살",
  "purchase_date": "2026-04-15",
  "storage_method": "냉장",
  "category": null
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `item_name` | string | O | 식재료명 |
| `purchase_date` | string | O | 구매일 (YYYY-MM-DD) |
| `storage_method` | string | X | `"냉장"` / `"냉동"` / `"상온"` (기본 냉장) |
| `category` | string | X | 카테고리 힌트 |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-2b3c4d5e6f1a",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "item_name": "삼겹살",
    "purchase_date": "2026-04-15",
    "storage_method": "냉장",
    "expiry_date": "2026-04-18",
    "d_day": 2,
    "risk_level": "caution",
    "confidence": 0.85,
    "method": "gpt-4o-mini",
    "reason": "냉장 보관 시 삼겹살은 일반적으로 3일 정도의 소비기한을 가집니다."
  },
  "error": null
}
```

| risk_level | D-Day | 의미 |
|------------|-------|------|
| `safe` | 4일 이상 | 안전 |
| `caution` | 2~3일 | 곧 만료 |
| `danger` | 0~1일 | 즉시 소비 필요 |
| `expired` | 음수 | 만료됨 |

---

### 6-2. `POST /ai/v1/expiry/batch`

여러 품목의 소비기한을 일괄 계산하고, 임박 알림도 함께 반환합니다.

**요청:**
```json
{
  "items": [
    { "item_name": "삼겹살", "purchase_date": "2026-04-15", "storage_method": "냉장" },
    { "item_name": "우유", "purchase_date": "2026-04-10", "storage_method": "냉장" },
    { "item_name": "양파", "purchase_date": "2026-04-01", "storage_method": "상온" }
  ]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-3c4d5e6f1a2b",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "results": [
      {
        "item_name": "삼겹살",
        "purchase_date": "2026-04-15",
        "storage_method": "냉장",
        "expiry_date": "2026-04-18",
        "d_day": 2,
        "risk_level": "caution",
        "confidence": 0.85,
        "method": "gpt-4o-mini",
        "reason": "냉장 보관 시 3일 기준"
      },
      {
        "item_name": "우유",
        "purchase_date": "2026-04-10",
        "storage_method": "냉장",
        "expiry_date": "2026-04-17",
        "d_day": 0,
        "risk_level": "danger",
        "confidence": 0.85,
        "method": "gpt-4o-mini",
        "reason": "우유는 냉장 보관 시 7일 이내 소비 권장"
      },
      {
        "item_name": "양파",
        "purchase_date": "2026-04-01",
        "storage_method": "상온",
        "expiry_date": "2026-04-15",
        "d_day": -2,
        "risk_level": "expired",
        "confidence": 0.85,
        "method": "gpt-4o-mini",
        "reason": "양파는 상온에서 약 14일 보관 가능"
      }
    ],
    "total_count": 3,
    "alerts": [
      {
        "item_name": "삼겹살",
        "expiry_date": "2026-04-18",
        "d_day": 2,
        "risk_level": "caution",
        "alert_type": "expiry_imminent",
        "message": "'삼겹살'의 소비기한이 2일 남았습니다."
      },
      {
        "item_name": "우유",
        "expiry_date": "2026-04-17",
        "d_day": 0,
        "risk_level": "danger",
        "alert_type": "expiry_imminent",
        "message": "'우유'의 소비기한이 0일 남았습니다."
      },
      {
        "item_name": "양파",
        "expiry_date": "2026-04-15",
        "d_day": -2,
        "risk_level": "expired",
        "alert_type": "expiry_imminent",
        "message": "'양파'의 소비기한이 지났습니다."
      }
    ],
    "alert_count": 3
  },
  "error": null
}
```

---

### 6-3. `POST /ai/v1/expiry/alerts`

소비기한 임박 품목(D-3 이하)만 필터링하여 알림 트리거를 반환합니다.

**요청:** (6-2와 동일)
```json
{
  "items": [
    { "item_name": "삼겹살", "purchase_date": "2026-04-15", "storage_method": "냉장" },
    { "item_name": "사과", "purchase_date": "2026-04-10", "storage_method": "냉장" }
  ]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-4d5e6f1a2b3c",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "alerts": [
      {
        "item_name": "삼겹살",
        "expiry_date": "2026-04-18",
        "d_day": 2,
        "risk_level": "caution",
        "alert_type": "expiry_imminent",
        "message": "'삼겹살'의 소비기한이 2일 남았습니다."
      }
    ],
    "alert_count": 1
  },
  "error": null
}
```

---

## 7. 나눔 금지 품목 필터링

### `POST /ai/v1/sharing/check`

나눔 게시글 작성 시 금지 품목을 1차 필터링합니다.

**요청:**
```json
{
  "item_names": ["삼겹살", "수제 반찬", "참치캔", "개봉우유", "라면"]
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-5e6f1a2b3c4d",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "blocked": [
      {
        "item_name": "수제 반찬",
        "status": "blocked",
        "reason": "나눔 금지 품목: 개봉 반찬/조리 음식",
        "category": "개봉 반찬/조리 음식"
      },
      {
        "item_name": "개봉우유",
        "status": "blocked",
        "reason": "나눔 금지 품목: 유제품(개봉)",
        "category": "유제품(개봉)"
      }
    ],
    "review_required": [],
    "allowed": [
      { "item_name": "삼겹살" },
      { "item_name": "참치캔" },
      { "item_name": "라면" }
    ],
    "summary": {
      "blocked": 2,
      "review": 0,
      "allowed": 3
    }
  },
  "error": null
}
```

---

## 8. 재료 검색

### `GET /ai/v1/ingredients/search`

키워드로 DB 재료를 검색합니다.

**요청**: `GET /ai/v1/ingredients/search?q=삼겹&category=정육/계란&limit=10`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `q` | string | O | 검색 키워드 |
| `category` | string | X | 카테고리 필터 |
| `limit` | int | X | 최대 반환 개수 (기본 20, 최대 100) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-6f1a2b3c4d5e",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "results": [
      { "ingredientId": "ING_0042", "ingredientName": "삼겹살", "category": "정육/계란" },
      { "ingredientId": "ING_0043", "ingredientName": "대패삼겹", "category": "정육/계란" }
    ],
    "total_count": 2,
    "query": "삼겹"
  },
  "error": null
}
```

---

## 9. 조리방법 목록

### `GET /ai/v1/cooking-methods`

사용 가능한 조리방법 목록과 각 레시피 수를 반환합니다.

**요청**: 파라미터 없음

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-7a1b2c3d4e5f",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "methods": [
      { "name": "볶기", "code": "STIRFRY", "recipeCount": 320 },
      { "name": "끓이기", "code": "BOIL", "recipeCount": 285 },
      { "name": "굽기", "code": "GRILL", "recipeCount": 210 },
      { "name": "찌기", "code": "STEAM", "recipeCount": 95 },
      { "name": "튀기기", "code": "FRY", "recipeCount": 78 }
    ],
    "total_count": 5
  },
  "error": null
}
```

---

## 10. 작업(Job) 관리

### 10-1. `GET /ai/v1/jobs/{job_id}`

비동기 OCR 작업 상태를 조회합니다.

**요청**: `GET /ai/v1/jobs/ocr-a1b2c3d4`

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-8b2c3d4e5f6a",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "job_id": "ocr-a1b2c3d4",
    "status": "completed",
    "created_at": "2026-04-16T14:30:00",
    "completed_at": "2026-04-16T14:30:03",
    "result": {
      "ocr_texts": [ "..." ],
      "food_items": [ "..." ],
      "food_count": 5,
      "model": "rule_based_v1",
      "store_name": "이마트",
      "purchase_date": "2026-04-15"
    }
  },
  "error": null
}
```

---

### 10-2. `GET /ai/v1/jobs`

작업 목록을 조회합니다.

**요청**: `GET /ai/v1/jobs?status=completed&limit=5`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `status` | string | X | 상태 필터 (`completed`, `failed`, `processing`) |
| `limit` | int | X | 최대 반환 개수 (기본 20) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-9c3d4e5f6a1b",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "jobs": [
      {
        "job_id": "ocr-a1b2c3d4",
        "status": "completed",
        "created_at": "2026-04-16T14:30:00",
        "completed_at": "2026-04-16T14:30:03"
      },
      {
        "job_id": "ocr-e5f6a1b2",
        "status": "completed",
        "created_at": "2026-04-16T13:15:00",
        "completed_at": "2026-04-16T13:15:02"
      }
    ],
    "total_count": 2
  },
  "error": null
}
```

---

## 11. 품질 모니터링

### 11-1. `GET /ai/v1/quality/metrics`

품질 지표 (요청 수, 오류율, 응답시간)를 반환합니다.

**요청**: `GET /ai/v1/quality/metrics?window=1h`

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `window` | string | X | 시간 윈도우 (`1h`, `6h`, `1d`, `7d`) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-ad4e5f6a1b2c",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "window": "1h",
    "total_requests": 156,
    "error_count": 3,
    "error_rate": 0.0192,
    "avg_response_ms": 45.23,
    "p95_response_ms": 210.50,
    "endpoints": {
      "/ai/v1/ocr/preprocess": { "count": 20, "errors": 1, "avg_ms": 2500.0 },
      "/ai/v1/recommendations/candidates": { "count": 85, "errors": 0, "avg_ms": 12.3 },
      "/ai/v1/expiry/calculate": { "count": 30, "errors": 2, "avg_ms": 1800.5 },
      "/ai/v1/health": { "count": 21, "errors": 0, "avg_ms": 1.2 }
    }
  },
  "error": null
}
```

---

### 11-2. `GET /ai/v1/quality/drift`

품질 드리프트(성능 저하)를 감지합니다.

**요청**: `GET /ai/v1/quality/drift?window=7d`

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-be5f6a1b2c3d",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "status": "normal",
    "window": "7d",
    "error_rate": 0.019,
    "p95_response_ms": 210.5,
    "total_requests": 1523
  },
  "error": null
}
```

| status | 조건 | 의미 |
|--------|------|------|
| `normal` | 오류율 < 10% | 정상 |
| `degraded` | 오류율 10~30% | 성능 저하 |
| `critical` | 오류율 > 30% | 심각 |
| `slow` | P95 > 5000ms | 응답 지연 |

---

### 11-3. `GET /ai/v1/quality/errors`

최근 오류 로그를 반환합니다.

**요청**: `GET /ai/v1/quality/errors?limit=3`

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-cf6a1b2c3d4e",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "errors": [
      {
        "timestamp": "2026-04-16T14:30:05",
        "endpoint": "/ai/v1/ocr/preprocess",
        "elapsed_ms": 30012.5,
        "status_code": 500,
        "trace_id": "tr-xxx",
        "error": "OCR timeout"
      }
    ],
    "total_count": 1
  },
  "error": null
}
```

---

## 12. 버전 관리

### 12-1. `GET /ai/v1/models/version`

현재 모델 버전 정보를 반환합니다.

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-d1a2b3c4d5e6",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "version": "paddleocr_2.7+rule_v1",
    "components": {
      "ocr": "PaddleOCR 2.7",
      "normalizer": "rule_based_v1",
      "recommender": "weighted_scoring_v1",
      "expiry": "gpt-4o-mini + rule_fallback"
    }
  },
  "error": null
}
```

---

### 12-2. `GET /ai/v1/dictionaries/version`

품목 사전 버전 정보를 반환합니다.

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-e2b3c4d5e6f1",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "version": "dict_v1_20260415_3408items",
    "path": "/app/data/labels/unified_ingredients.json",
    "updated_at": "2026-04-16T14:30:00"
  },
  "error": null
}
```

---

### 12-3. `PATCH /ai/v1/dictionaries/reload`

품목 사전을 다시 로드합니다.

**요청**: Body 없음

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-f3c4d5e6f1a2",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "message": "사전이 새로 로드되었습니다."
  },
  "error": null
}
```

---

### 12-4. `GET /ai/v1/prompts/version`

프롬프트 템플릿 버전 정보를 반환합니다.

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-14d5e6f1a2b3",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "version": "qwen_prompt_v1",
    "templates": {
      "ocr_refinement": "qwen_receipt_v1",
      "expiry_calculation": "gpt4omini_expiry_v1",
      "recommendation_explanation": "qwen_explain_v1"
    }
  },
  "error": null
}
```

---

## 13. 임계값 / Fallback 정책

### 13-1. `GET /ai/v1/thresholds`

현재 임계값 설정을 조회합니다.

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-25e6f1a2b3c4",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "ocr_confidence_min": 0.80,
    "match_similarity_min": 0.50,
    "expiry_alert_days": 3
  },
  "error": null
}
```

---

### 13-2. `PATCH /ai/v1/thresholds`

임계값을 업데이트합니다.

**요청:**
```json
{
  "ocr_confidence_min": 0.85,
  "expiry_alert_days": 5
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-36f1a2b3c4d5",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "ocr_confidence_min": 0.85,
    "match_similarity_min": 0.50,
    "expiry_alert_days": 5
  },
  "error": null
}
```

---

### 13-3. `GET /ai/v1/fallback/policies`

Fallback 정책 목록을 조회합니다.

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-47a1b2c3d4e5",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "ocr_timeout": {
      "action": "manual_input",
      "timeout_sec": 30
    },
    "gpt_unavailable": {
      "action": "rule_based_fallback"
    },
    "low_confidence": {
      "action": "review_queue",
      "threshold": 0.60
    }
  },
  "error": null
}
```

---

### 13-4. `PATCH /ai/v1/fallback/policies/{policy_id}`

특정 Fallback 정책을 업데이트합니다.

**요청**: `PATCH /ai/v1/fallback/policies/ocr_timeout`
```json
{
  "timeout_sec": 45
}
```

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-58b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "ocr_timeout": {
      "action": "manual_input",
      "timeout_sec": 45
    }
  },
  "error": null
}
```

---

## 14. 캐시 관리

### `DELETE /ai/v1/cache/clear`

AI 서버 인메모리 캐시를 초기화합니다.

**요청**: Body 없음

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-69c3d4e5f6a1",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "message": "캐시가 초기화되었습니다."
  },
  "error": null
}
```

---

## 15. 백엔드 연동 API

> 아래 2개는 Spring Boot 백엔드가 직접 호출하는 엔드포인트입니다.

### 15-1. `POST /ai/ocr/analyze`

영수증 이미지를 받아 OCR + 규칙 보정 + Qwen 1차 보정 후 식품명 리스트를 반환합니다.  
DB 매칭 없이 식품명만 넘기므로, DB 저장은 백엔드에서 처리합니다.

**요청**: `Content-Type: multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `image` | File | O | 영수증 이미지 (jpg/png) |

**응답:**
```json
{
  "result_code": "OK",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": {
    "items": [
      { "name": "삼겹살", "category": "축산물", "price": 15000 },
      { "name": "대파", "category": "농산물", "price": 2000 },
      { "name": "깻잎", "category": "농산물", "price": 1500 }
    ],
    "item_count": 3,
    "store_name": "이마트",
    "purchase_date": "2026-04-15",
    "model": "rule_based_v1 + qwen"
  },
  "error": null
}
```

| 응답 필드 | 타입 | 설명 |
|-----------|------|------|
| `items` | Array | 추출된 식품 목록 |
| `items[].name` | String | 식품명 (OCR 보정 완료) |
| `items[].category` | String | 카테고리 (축산물, 농산물, 유제품 등) |
| `items[].price` | Int \| null | 가격 (원) |
| `item_count` | Int | 추출된 식품 수 |
| `store_name` | String \| null | 매장명 (인식 실패 시 null) |
| `purchase_date` | String \| null | 구매일 YYYY-MM-DD (인식 실패 시 null) |
| `model` | String | 사용된 모델명 |

---

### 15-2. `POST /ai/ingredient/prediction`

식재료 배열의 소비기한을 GPT-4o-mini로 계산합니다. GPT 실패 시 규칙 기반으로 자동 전환됩니다.

**요청**: `Content-Type: multipart/form-data`

```json
{
  "purchaseDate": "2026-04-09",
  "ingredients": ["우유", "당근", "상추"]
}
```

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `purchaseDate` | String | O | 구매일 (YYYY-MM-DD) |
| `ingredients` | Array[String] | O | 식재료명 배열 |

**응답 (200):**
```json
{
  "success": true,
  "result": {
    "purchaseDate": "2026-04-09",
    "ingredients": [
      { "ingredientName": "우유", "expirationDate": "2026-06-16" },
      { "ingredientName": "당근", "expirationDate": "2026-06-16" },
      { "ingredientName": "상추", "expirationDate": "2026-06-16" }
    ]
  }
}
```

**응답 (500):**
```json
{
  "success": false,
  "code": "AI500",
  "result": "소비기한을 예측할 수 없습니다."
}
```

| 응답 필드 | 타입 | 설명 |
|-----------|------|------|
| `success` | Boolean | 성공 여부 |
| `result.purchaseDate` | String | 구매일 |
| `result.ingredients` | Array | 소비기한 결과 배열 |
| `result.ingredients[].ingredientName` | String | 식재료명 |
| `result.ingredients[].expirationDate` | String | 소비기한 (YYYY-MM-DD) |

---

## 오류 코드 목록

| 코드 | HTTP | 설명 |
|------|------|------|
| `INVALID_IMAGE` | 400 | 지원하지 않는 이미지 형식 (jpg/png만 허용) |
| `INVALID_REQUEST` | 400 | 요청 데이터 오류 (필수 필드 누락 등) |
| `RECIPE_NOT_FOUND` | 404 | 레시피 ID에 해당하는 레시피 없음 |
| `JOB_NOT_FOUND` | 404 | 작업 ID에 해당하는 작업 없음 |
| `POLICY_NOT_FOUND` | 404 | Fallback 정책 ID에 해당하는 정책 없음 |
| `SERVICE_UNAVAILABLE` | 503 | PaddleOCR 미설치 등 외부 서비스 불가 |
| `OCR_FAILED` | 500 | OCR 처리 중 내부 오류 |
