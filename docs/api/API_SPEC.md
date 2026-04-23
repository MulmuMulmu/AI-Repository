# AI API Specification

> 프로젝트: 영수증 기반 식재료 인식 및 개인화 레시피 추천  
> 서버: FastAPI  
> Base URL: `http://{AI_SERVER_HOST}:8000`

이 문서는 **현재 제품 흐름에서 실제로 사용하는 공개 API만** 정리한다.

기준 구현:

- [main.py](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/main.py)

문서 제외 대상:

- `/ai/ocr/refinement/{trace_id}`
- `/ai/sharing/check`
- `/ai/quality/metrics`

위 라우트들은 코드에 존재할 수 있지만, 현재 사용자 흐름 기준 핵심 공개 계약에서는 제외한다.

---

## 1. 현재 공개 API

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/ai/ocr/analyze` | 영수증 OCR 분석 |
| `POST` | `/ai/ingredient/match` | 상품명 기반 재료 예측 |
| `POST` | `/ai/ingredient/prediction` | 식품 1건 소비기한 계산 |
| `POST` | `/ai/recommend` | 보유 재료 기반 개인화 추천 |
| `GET` | `/ai/recipes/{recipe_id}` | 레시피 상세 조회 |
| `GET` | `/ai/ingredients/search` | 재료 검색 |

---

## 2. 사용자 흐름 기준 역할

현재 AI 서버는 아래 순서의 제품 흐름을 담당한다.

1. 영수증 분석
2. 상품명 -> 재료 매핑
3. 식품 1건의 소비기한 계산
4. 보유 재료 + 사용자 제약 기반 추천
5. 추천된 레시피 상세 조회
6. 수동 수정 화면용 재료 검색

즉, 이 문서 기준 AI 서버는  
**영수증 등록과 레시피 추천에 직접 연결되는 API만** 공개 대상으로 본다.

---

## 3. API 상세

### `POST /ai/ocr/analyze`

영수증 이미지를 받아 구조화된 분석 결과를 반환한다.

핵심 처리 단계:

1. 전처리
2. PaddleOCR
3. bbox 유지 row merge
4. rule-based receipt parser
5. 날짜 / 합계 / 품목 검증
6. `review_required`, `review_reasons`, `scope_classification` 계산
7. 필요 시 제한적 Qwen rescue

주요 응답 필드:

- `ocr_texts`
- `food_items`
- `food_count`
- `model`
- `vendor_name`
- `purchased_at`
- `totals`
- `review_required`
- `review_reasons`
- `diagnostics`

운영 의미:

- `review_required=false`
  - 자동 등록 후보
- `review_required=true`
  - 프론트에서 수동 수정 화면으로 연결

### `POST /ai/ingredient/match`

OCR에서 나온 상품명을 재료 단위로 예측한다.

매핑 순서:

1. alias 정규화
2. 규칙 사전 매핑
3. DB exact match
4. DB fuzzy match

응답 분류:

- `MAPPED`
- `UNMAPPED`
- `EXCLUDED`

### `POST /ai/ingredient/prediction`

식품 1건의 소비기한을 계산한다.

입력 핵심:

- `item_name`
- `purchase_date`
- `storage_method`
- `category`

즉 현재 외부 계약 기준에서 `/ai/ingredient/prediction`은
**상품명→재료 매핑이 아니라 유통기한/소비기한 계산 API**다.

### `POST /ai/recommend`

보유 재료와 사용자 제약을 기반으로 개인화 추천을 계산한다.

입력 핵심:

- `ingredientIds`
- `preferredIngredientIds`
- `dislikedIngredientIds`
- `allergyIngredientIds`
- `preferredCategories`
- `excludedCategories`
- `preferredKeywords`
- `excludedKeywords`

현재 구현 방식:

- 학습형 추천 모델이 아니라 규칙 기반 ranking engine
- hard filter + soft boost 구조

### `GET /ai/recipes/{recipe_id}`

레시피 상세, 재료 목록, 조리 단계를 조회한다.

### `GET /ai/ingredients/search`

수동 수정 화면이나 재료 선택 UI에서 사용하는 검색 API다.

---

## 4. 응답 정책

기본 응답 형식:

```json
{
  "success": true,
  "data": {},
  "error": null
}
```

에러 응답 형식:

```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 메시지"
  }
}
```

대표 오류 코드:

| HTTP | code | 설명 |
|---|---|---|
| `400` | `INVALID_IMAGE` | 이미지 형식 오류 |
| `400` | `INVALID_REQUEST` | 요청 형식 오류 |
| `404` | `NOT_FOUND` | 대상 없음 |
| `500` | `OCR_FAILED` | OCR 분석 실패 |
| `503` | `SERVICE_UNAVAILABLE` | 런타임 사용 불가 |

---

## 5. 제품 정책 요약

### 제품 범위

- 우선 지원: 마트, 편의점, 식자재 중심 영수증
- 보조 지원: 식품 + 비식품 혼합 영수증
- 범위 밖: 약국, 전자제품, 일반 생활잡화 중심 영수증

### review 정책

- 안정적 결과는 자동 등록
- 애매한 결과는 `review_required=true`
- 프론트는 이를 수동 수정 UX로 처리

### 추천 정책

- 보유 재료가 중심
- 선호/비선호/알레르기/카테고리/키워드를 함께 반영
- 현재는 학습형 모델이 아니라 규칙 기반 추천 엔진

---

## 6. 연계 문서

- [../architecture/PROJECT_PROCESS_AND_RATIONALE.md](../architecture/PROJECT_PROCESS_AND_RATIONALE.md)
- [../architecture/OCR_IMPLEMENTATION.md](../architecture/OCR_IMPLEMENTATION.md)
- [../operations/NORMAL_INPUT_CRITERIA.md](../operations/NORMAL_INPUT_CRITERIA.md)
- [../operations/RECAPTURE_GUIDELINES.md](../operations/RECAPTURE_GUIDELINES.md)
- [../history/status/OCR_PIPELINE_STATUS_2026-04-18.md](../history/status/OCR_PIPELINE_STATUS_2026-04-18.md)
