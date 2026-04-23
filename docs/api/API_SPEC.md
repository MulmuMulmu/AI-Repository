# OCR/Qwen API Specification

> 프로젝트: 영수증 기반 식재료 인식 및 소비기한 계산  
> 서버: FastAPI  
> Base URL: `http://{OCR_SERVER_HOST}:8000`

이 문서는 **OCR/Qwen 컨테이너에서 실제로 사용하는 공개 API만** 정리한다.

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
| `POST` | `/ai/ingredient/match` | 상품명 기반 재료 매핑 |
| `POST` | `/ai/ingredient/prediction` | 식품 1건 소비기한 계산 |

---

## 2. 사용자 흐름 기준 역할

현재 OCR/Qwen 컨테이너는 아래 흐름을 담당한다.

1. 영수증 분석
2. 상품명 -> 재료 매핑
3. 식품 1건 소비기한 계산
4. 백엔드로 전달할 등록 후보 생성

즉 이 컨테이너는 **영수증 등록 전처리와 해석**에 집중한다.

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

- `purchased_at`
- `food_items`
- `review_required`
- `review_reasons`
- `diagnostics`

`food_items` 항목 형식:

- `product_name`
- `category`

허용 카테고리:

1. `정육/계란`
2. `해산물`
3. `채소/과일`
4. `유제품`
5. `쌀/면/빵`
6. `소스/조미료/오일`
7. `가공식품`
8. `기타`

응답 예시:

```json
{
  "success": true,
  "data": {
    "purchased_at": "2026-03-11",
    "food_items": [
      {"product_name": "우유", "category": "유제품"},
      {"product_name": "삼겹살", "category": "정육/계란"},
      {"product_name": "양파", "category": "채소/과일"}
    ]
  },
  "error": null
}
```

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

## 5. 연계 문서

- [RECOMMEND_API_SPEC.md](RECOMMEND_API_SPEC.md)
- [../architecture/PROJECT_PROCESS_AND_RATIONALE.md](../architecture/PROJECT_PROCESS_AND_RATIONALE.md)
- [../architecture/OCR_IMPLEMENTATION.md](../architecture/OCR_IMPLEMENTATION.md)
- [../operations/NORMAL_INPUT_CRITERIA.md](../operations/NORMAL_INPUT_CRITERIA.md)
- [../operations/RECAPTURE_GUIDELINES.md](../operations/RECAPTURE_GUIDELINES.md)
