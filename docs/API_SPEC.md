# AI Server API 명세 (설계서 v1.1)

> 기본 경로: `/ai/v1`  
> 공통 응답 형식: `AiResponse { result_code, trace_id, model_version, result, error }`

---

## 공통 응답 구조

모든 엔드포인트는 아래 JSON 구조를 반환합니다.

```json
{
  "result_code": "OK",
  "trace_id": "tr-a1b2c3d4e5f6",
  "model_version": "ai-server-v1.1.0",
  "result": { ... },
  "error": null
}
```

| 필드 | 타입 | 설명 |
|------|------|------|
| `result_code` | string | `"OK"` 또는 오류 코드 |
| `trace_id` | string | 요청 추적 ID (`tr-` 접두사) |
| `model_version` | string | 서버 버전 |
| `result` | object/null | 정상 응답 데이터 |
| `error` | object/null | `{"code": str, "message": str}` |

---

## 1. 헬스체크

### `GET /ai/v1/health`

서버 상태, 서비스 가용성, 통계를 반환합니다.

**응답 (result)**
```json
{
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
    "total_recipes": 1200,
    "total_ingredients": 350,
    "total_recipe_ingredients": 8500,
    "total_recipe_steps": 6000
  }
}
```

---

## 2. OCR 파이프라인 (3단계)

### 2-1. `POST /ai/v1/ocr/preprocess`

영수증 이미지 → PaddleOCR → 원시 텍스트 추출 → 규칙 기반 정규화.

**요청**: `multipart/form-data`

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `image` | file | O | jpg/png 영수증 이미지 |
| `use_qwen` | bool | X | Qwen 보강 여부 (기본 false) |

**응답 (result)**
```json
{
  "job_id": "ocr-a1b2c3d4",
  "status": "completed",
  "ocr_texts": [ {"text": "...", "confidence": 0.95} ],
  "food_items": [ { "product_name_raw": "삼겹쌀", "product_name": "삼겹살", ... } ],
  "food_count": 5,
  "model": "rule_based_v1",
  "store_name": "이마트",
  "purchase_date": "2026-04-15"
}
```

### 2-2. `POST /ai/v1/ocr/extract-lines`

텍스트 목록 → OCR 보정 → 라인 분류.

**요청**
```json
{ "product_names": ["삼겹쌀 2,500", "합계", "..."] }
```

**응답 (result)**
```json
{
  "lines": [
    { "raw": "삼겹쌀 2,500", "corrected": "삼겹살 2,500", "line_type": "product", "ocr_changed": true }
  ],
  "line_count": 1
}
```

### 2-3. `POST /ai/v1/ocr/normalize`

상품명 → 정규화 → 카테고리 → DB 매칭.

**요청**
```json
{ "product_names": ["삼겹살", "대파", "..."] }
```

**응답 (result)**
```json
{
  "items": [
    {
      "product_name_raw": "삼겹살",
      "product_name": "삼겹살",
      "category_major": "축산물",
      "category_sub": "돼지고기",
      "ingredient_match": { "ingredientId": "ING_001", "ingredientName": "삼겹살", "category": "정육/계란", "similarity": 1.0 },
      "confidence": 1.0,
      "needs_review": false,
      "notes": ""
    }
  ],
  "item_count": 1,
  "model": "rule_based_v1"
}
```

---

## 3. 재료 매칭

### `POST /ai/v1/ingredients/match`

상품명 → DB 재료 매칭.

**요청**
```json
{ "product_names": ["삼겹살", "알수없는재료"] }
```

**응답 (result)**
```json
{
  "matched": [ { "product_name": "삼겹살", "ingredientId": "ING_001", "ingredientName": "삼겹살", "category": "정육/계란", "similarity": 1.0 } ],
  "unmatched": [ { "product_name": "알수없는재료", "reason": "DB에 일치하는 재료 없음", "suggestions": ["양배추", "양파"] } ],
  "matched_count": 1,
  "unmatched_count": 1
}
```

---

## 4. 레시피 추천

### 4-1. `POST /ai/v1/recommendations/candidates`

보유 재료 기반 추천 후보 목록.

**요청**
```json
{
  "ingredientIds": ["ING_001", "ING_002"],
  "top_k": 10,
  "category": null,
  "cookingMethod": null,
  "mode": "partial",
  "min_match_rate": 0.0
}
```

| 필드 | 설명 |
|------|------|
| `mode` | `"partial"` — 부족 재료 50%까지 허용 / `"exact"` — 보유 재료만 |
| `cookingMethod` | 한글명(`볶기`) 또는 코드(`STIRFRY`) |

**응답 (result)**
```json
{
  "recommendations": [
    {
      "recipeId": "RCP_001",
      "name": "제육볶음",
      "score": 0.85,
      "matchRate": 0.75,
      "weightedMatchRate": 0.82,
      "coreCoverage": 0.9,
      "feasibility": 0.8,
      "matchedIngredients": [...],
      "missingIngredients": [...],
      "substitutions": [...]
    }
  ],
  "total_count": 10,
  "input_ingredient_count": 2,
  "mode": "partial"
}
```

### 4-2. `POST /ai/v1/recommendations/explanations`

특정 레시피에 대한 추천 이유 상세.

**요청**
```json
{ "recipeId": "RCP_001", "ingredientIds": ["ING_001", "ING_002"] }
```

**응답 (result)**
```json
{
  "recipeId": "RCP_001",
  "name": "제육볶음",
  "explanation": "[제육볶음] 추천 점수 85% | 보유 재료: 삼겹살, 양파 | 대체 가능: 진간장→간장 | 부족: 고추장",
  "score": 0.85,
  "matchRate": 0.75,
  "matchedIngredients": [...],
  "missingIngredients": [...],
  "substitutions": [...]
}
```

---

## 5. 레시피 상세

### `GET /ai/v1/recipes/{recipe_id}`

**응답 (result)**
```json
{
  "recipeId": "RCP_001",
  "name": "제육볶음",
  "category": "한식",
  "cookingMethod": "볶기",
  "cookingMethodCode": "STIRFRY",
  "imageUrl": "...",
  "ingredients": [
    { "recipeIngredientId": "RI_001", "ingredientId": "ING_001", "ingredientName": "삼겹살", "amount": "300", "unit": "g" }
  ],
  "steps": [
    { "recipeStepId": "RS_001", "stepOrder": 1, "description": "삼겹살을 한입 크기로 자른다." }
  ]
}
```

---

## 6. 소비기한 계산

### 6-1. `POST /ai/v1/expiry/calculate`

단일 품목 소비기한 계산.

**요청**
```json
{
  "item_name": "삼겹살",
  "purchase_date": "2026-04-15",
  "storage_method": "냉장",
  "category": null
}
```

**응답 (result)**
```json
{
  "item_name": "삼겹살",
  "purchase_date": "2026-04-15",
  "storage_method": "냉장",
  "expiry_date": "2026-04-18",
  "d_day": 2,
  "risk_level": "caution",
  "confidence": 0.85,
  "method": "gpt-4o-mini",
  "reason": "돼지고기 냉장 보관 시 3일 기준"
}
```

### 6-2. `POST /ai/v1/expiry/batch`

여러 품목 일괄 계산 + 알림 포함.

### 6-3. `POST /ai/v1/expiry/alerts`

소비기한 임박 품목 알림 트리거 (D-3 이하).

---

## 7. 나눔 금지 품목 필터링

### `POST /ai/v1/sharing/check`

**요청**
```json
{ "item_names": ["삼겹살", "수제 반찬", "참치캔"] }
```

**응답 (result)**
```json
{
  "blocked": [ { "item_name": "수제 반찬", "reason": "나눔 금지 품목: 개봉 반찬/조리 음식", "category": "개봉 반찬/조리 음식" } ],
  "review_required": [],
  "allowed": [ { "item_name": "삼겹살" }, { "item_name": "참치캔" } ],
  "summary": { "blocked": 1, "review": 0, "allowed": 2 }
}
```

---

## 8. 재료 검색 / 조리방법

### `GET /ai/v1/ingredients/search?q=삼겹&limit=10`

키워드로 DB 재료 검색.

### `GET /ai/v1/cooking-methods`

조리방법 목록 + 레시피 수.

---

## 9. 작업(Job) 관리

### `GET /ai/v1/jobs/{job_id}`

비동기 OCR 작업 상태 조회.

### `GET /ai/v1/jobs?status=completed&limit=20`

작업 목록 조회.

---

## 10. 운영/품질 관리 API

### `GET /ai/v1/quality/metrics?window=1h`

품질 지표 (요청 수, 오류율, 응답시간 P95 등).

### `GET /ai/v1/quality/drift?window=7d`

품질 드리프트 감지 (`normal` / `degraded` / `critical` / `slow`).

### `GET /ai/v1/quality/errors?limit=50`

최근 오류 로그.

### `GET /ai/v1/models/version`

모델 버전 정보 (OCR, Normalizer, Recommender, Expiry).

### `GET /ai/v1/dictionaries/version`

품목 사전 버전 정보.

### `PATCH /ai/v1/dictionaries/reload`

품목 사전 다시 로드.

### `GET /ai/v1/prompts/version`

프롬프트 템플릿 버전 정보.

### `GET /ai/v1/thresholds`

현재 임계값 설정 조회.

### `PATCH /ai/v1/thresholds`

임계값 업데이트.

### `GET /ai/v1/fallback/policies`

Fallback 정책 목록.

### `PATCH /ai/v1/fallback/policies/{policy_id}`

특정 Fallback 정책 업데이트.

### `DELETE /ai/v1/cache/clear`

AI 서버 캐시 초기화.

---

## 오류 코드 목록

| 코드 | HTTP | 설명 |
|------|------|------|
| `INVALID_IMAGE` | 400 | 지원하지 않는 이미지 형식 |
| `INVALID_REQUEST` | 400 | 요청 데이터 오류 |
| `RECIPE_NOT_FOUND` | 404 | 레시피 미존재 |
| `JOB_NOT_FOUND` | 404 | 작업 미존재 |
| `POLICY_NOT_FOUND` | 404 | Fallback 정책 미존재 |
| `SERVICE_UNAVAILABLE` | 503 | PaddleOCR 미설치 등 |
| `OCR_FAILED` | 500 | OCR 처리 실패 |
