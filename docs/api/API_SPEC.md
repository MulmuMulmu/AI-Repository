# AI API Specification

> 프로젝트: 영수증 기반 식재료 인식 및 개인화 레시피 추천  
> 서버: FastAPI  
> Base URL: `http://{AI_SERVER_HOST}:8000`

이 문서는 **현재 코드 기준으로 실제 노출되는 API surface**를 정리한다.

기준 구현:

- [main.py](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/main.py)

---

## 1. 역할

현재 AI 서버는 아래 역할을 가진다.

1. 영수증 OCR 분석
2. 상품명 -> 재료 예측
3. 나눔 가능 여부 분류
4. 소비기한 계산
5. 품질 지표 노출
6. 보유 재료 기반 개인화 추천
7. 레시피 상세 조회
8. 재료 검색

즉 이 서버는 단순 OCR 서버가 아니라,  
**영수증 분석부터 재료 매핑, 추천 계산까지 담당하는 AI 보조 서버**다.

---

## 2. API 목록

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/ai/ocr/analyze` | 영수증 OCR 분석 |
| `GET` | `/ai/ocr/refinement/{trace_id}` | OCR refinement 상태 조회 |
| `POST` | `/ai/ingredient/prediction` | 상품명 기반 재료 예측 |
| `POST` | `/ai/sharing/check` | 나눔 금지/검수/허용 품목 분류 |
| `POST` | `/ai/expiry/calculate` | 소비기한 계산 |
| `GET` | `/ai/quality/metrics` | 품질 지표 조회 |
| `POST` | `/ai/recommend` | 보유 재료 기반 개인화 추천 |
| `GET` | `/ai/recipes/{recipe_id}` | 레시피 상세 조회 |
| `GET` | `/ai/ingredients/search` | 재료 검색 |

---

## 3. 핵심 API

### `POST /ai/ocr/analyze`

영수증 이미지를 받아 구조화된 분석 결과를 반환한다.

핵심 처리 단계:

1. 전처리
2. PaddleOCR
3. bbox 유지 row merge
4. section split
5. item assembly
6. totals / 날짜 / 품목 검증
7. `review_required`, `review_reasons`, `scope_classification` 계산
8. 필요 시 제한적 Qwen rescue

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
  - 자동 등록 후보로 사용 가능
- `review_required=true`
  - 프론트에서 수동 수정 화면으로 연결

### `GET /ai/ocr/refinement/{trace_id}`

OCR refinement 비동기 상태를 조회한다.

의미:

- refinement 추적
- fallback/보정 경로 상태 확인

### `POST /ai/ingredient/prediction`

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

### `POST /ai/recommend`

보유 재료와 사용자 선호 조건을 기반으로 레시피를 추천한다.

입력:

- `ingredientIds`
- `preferredIngredientIds`
- `dislikedIngredientIds`
- `allergyIngredientIds`
- `preferredCategories`
- `excludedCategories`
- `preferredKeywords`
- `excludedKeywords`

현재 구현 방식:

- 학습 모델이 아니라 규칙 기반 ranking engine
- hard filter + soft boost 구조

### `GET /ai/recipes/{recipe_id}`

레시피 상세, 재료 목록, 조리 단계를 조회한다.

### `GET /ai/ingredients/search`

재료 검색 UI에서 사용할 검색 API다.

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

## 5. 운영 정책 요약

### 제품 범위

- 우선 지원: 마트, 편의점, 식자재 중심 영수증
- 보조 지원: 식품 + 비식품 혼합 영수증
- 범위 밖: 약국, 전자제품, 일반 생활잡화 중심 영수증

### review 정책

- 안정적 결과는 자동 등록
- 애매한 결과는 `review_required=true`
- 프론트는 이를 수동 수정 UX로 처리

### Qwen 정책

- 메인 파서는 PaddleOCR + rule parser
- Qwen은 보조 rescue
- 현재 small local Qwen은 운영 메인 경로로 두지 않음

---

## 6. 연계 문서

- [../architecture/PROJECT_PROCESS_AND_RATIONALE.md](../architecture/PROJECT_PROCESS_AND_RATIONALE.md)
- [../architecture/OCR_IMPLEMENTATION.md](../architecture/OCR_IMPLEMENTATION.md)
- [../operations/NORMAL_INPUT_CRITERIA.md](../operations/NORMAL_INPUT_CRITERIA.md)
- [../operations/RECAPTURE_GUIDELINES.md](../operations/RECAPTURE_GUIDELINES.md)
- [../history/status/OCR_PIPELINE_STATUS_2026-04-18.md](../history/status/OCR_PIPELINE_STATUS_2026-04-18.md)
