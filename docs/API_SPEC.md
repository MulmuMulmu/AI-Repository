# AI API 명세서

> 프로젝트: 영수증 기반 식재료 인식 및 재료 예측
> 서버: FastAPI
> Base URL: `http://{AI_SERVER_HOST}:8000`

현재 공개 API는 아래 두 개만 사용합니다.

- `POST /ai/ocr/analyze`
- `POST /ai/ingredient/prediction`

---

## 1. 시스템 개요

이 서버는 영수증 OCR 결과를 구조화하고, 구조화된 상품명을 재료 테이블 기준으로 예측하는 역할을 담당합니다.

동작 순서:

1. 영수증 이미지 입력
2. 전처리
3. PaddleOCR 추출
4. bbox 유지한 row merge
5. section split
6. item assembly
7. totals / 날짜 / 품목 구조 검증
8. 필요 시 로컬 Qwen 보조
9. 품목명 기반 재료 예측

---

## 2. API 목록

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/ai/ocr/analyze` | 영수증 OCR 분석 |
| `POST` | `/ai/ingredient/prediction` | 상품명 기반 재료 예측 |

---

## 3. `POST /ai/ocr/analyze`

영수증 이미지를 받아 구조화된 OCR 분석 결과를 반환합니다.

### Request

| 항목 | 값 |
|---|---|
| Content-Type | `multipart/form-data` |

| 파라미터 | 타입 | 필수 | 설명 |
|---|---|---|---|
| `image` | file | O | 영수증 이미지 |
| `use_qwen` | boolean | X | 로컬 Qwen 보조 사용 여부. 기본값 `true` |

### Response 예시

```json
{
  "success": true,
  "data": {
    "ocr_texts": [
      {
        "line_id": 0,
        "text": "허쉬쿠키앤크림 1 1,600",
        "confidence": 0.91,
        "bbox": [[0, 0], [100, 0], [100, 20], [0, 20]],
        "center": [50, 10],
        "page_order": 0
      }
    ],
    "food_items": [
      {
        "product_name": "허쉬쿠키앤크림",
        "amount_krw": 1600,
        "notes": ""
      }
    ],
    "food_count": 1,
    "model": "receipt-engine-v2",
    "vendor_name": "GS25",
    "purchased_at": "2023-11-25",
    "totals": {
      "payment_amount": 24090.0
    },
    "diagnostics": {
      "quality_score": 0.95,
      "section_confidence": 0.91,
      "qwen_used": false,
      "unresolved_groups": 0
    }
  }
}
```

### Response 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `ocr_texts` | array | OCR 원문 라인 |
| `food_items` | array | 정리된 식품 품목 |
| `food_count` | int | 추출 품목 수 |
| `model` | string | 사용 엔진 또는 보조 모델 정보 |
| `vendor_name` | string \| null | 매장명 |
| `purchased_at` | string \| null | 구매일 |
| `totals` | object | subtotal / tax / total / payment_amount |
| `diagnostics` | object | 품질/구간/보조 사용 정보 |

### 파이프라인 상세

이 API는 단순 OCR API가 아닙니다. 현재 기준으로 아래 단계를 거칩니다.

1. `preprocess.py`
   - 이미지 대비 보정
   - OCR에 불리한 노이즈 완화

2. `services.py`
   - PaddleOCR backend 호출
   - bbox 포함 라인 추출

3. `receipts.py`
   - row merge
   - section split
   - item block detection
   - single-line / barcode-detail / gift row / two-line 패턴 파싱

4. validation
   - 날짜 존재 여부
   - 품목 구조 완결성
   - total mismatch
   - unresolved item 검출

5. 선택적 로컬 Qwen 보조
   - low-confidence / unresolved 케이스를 보조 정리
   - 실패 시 OCR-only fallback

---

## 4. `POST /ai/ingredient/prediction`

 OCR에서 정리된 상품명을 받아 다음 순서로 재료를 예측합니다.

1. 상품 alias 정규화
2. `product_to_ingredient` 규칙 사전 매핑
3. DB 재료명 exact match
4. DB 재료명 fuzzy match

매칭되지 않은 항목도 버리지 않습니다.

- 식품이지만 사전에 없는 경우: `mapping_status=UNMAPPED`
- 비식품/제외 대상인 경우: `mapping_status=EXCLUDED`
- 모든 항목은 `product_name`, `standard_product_name`, `item_type`를 함께 반환합니다.

### Request

```json
{
  "product_names": ["국산콩 두부", "깻잎", "삼겹살", "CJ 햇반"]
}
```

### Response 예시

```json
{
  "success": true,
  "data": {
    "matched": [
      {
        "product_name": "국산콩 두부",
        "ingredientId": "ingredient-1",
        "ingredientName": "두부",
        "category": "가공식품",
        "similarity": 0.92,
        "mapping_source": "fuzzy_similarity",
        "standard_product_name": "국산콩 두부",
        "mapping_status": "MAPPED",
        "item_type": "INGREDIENT"
      }
    ],
    "unmatched": [
      {
        "product_name": "CJ 햇반",
        "standard_product_name": "CJ 햇반",
        "item_type": "PROCESSED_FOOD",
        "mapping_status": "UNMAPPED",
        "reason": "DB에 일치하는 재료 없음",
        "suggestions": ["밥", "쌀"]
      }
    ],
    "matched_count": 1,
    "unmatched_count": 1
  }
}
```

### Response 필드

| 필드 | 타입 | 설명 |
|---|---|---|
| `matched` | array | 예측 성공한 재료 |
| `unmatched` | array | 예측 실패 상품 |
| `matched_count` | int | 성공 개수 |
| `unmatched_count` | int | 실패 개수 |

`matched` 내부 추가 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `mapping_source` | string | `receipt_rule_product_mapping`, `receipt_rule_product_mapping_fallback`, `normalized_exact_match`, `product_alias_fuzzy_match`, `fuzzy_similarity` 중 하나 |
| `standard_product_name` | string | alias 정규화 이후 내부 비교에 사용된 표준 상품명 |
| `mapping_status` | string | 항상 `MAPPED` |
| `item_type` | string | `INGREDIENT`, `PROCESSED_FOOD`, `SNACK`, `NON_FOOD`, `UNKNOWN` 중 하나 |

`unmatched` 내부 추가 필드:

| 필드 | 타입 | 설명 |
|---|---|---|
| `standard_product_name` | string | alias 정규화 이후 비교에 사용된 표준 상품명 |
| `mapping_status` | string | `UNMAPPED` 또는 `EXCLUDED` |
| `item_type` | string | `PROCESSED_FOOD`, `SNACK`, `NON_FOOD`, `UNKNOWN` 등 추정 분류 |

---

## 5. 에러 응답 형식

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 메시지"
  }
}
```

대표 코드:

| HTTP | code | 설명 |
|---|---|---|
| `400` | `INVALID_IMAGE` | 이미지 형식 오류 |
| `400` | `INVALID_REQUEST` | 요청 형식 오류 |
| `500` | `OCR_FAILED` | OCR 분석 실패 |
| `503` | `SERVICE_UNAVAILABLE` | OCR 런타임 사용 불가 |
