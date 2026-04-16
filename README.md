# AI-Repository

영수증 이미지를 분석해 식품 품목을 추출하고, 그 품목을 재료 단위로 예측하는 FastAPI 서버입니다.

현재 공개 API는 두 개만 사용합니다.

- `POST /ai/ocr/analyze`
- `POST /ai/ingredient/prediction`

이 저장소의 핵심은 단순 OCR이 아니라, 영수증 파싱 파이프라인을 실제 영수증 구조에 맞게 고도화한 점입니다.

## 1. 현재 시스템이 하는 일

### `POST /ai/ocr/analyze`

영수증 이미지를 받아 다음을 수행합니다.

1. 이미지 전처리
2. PaddleOCR 기반 텍스트 추출
3. bbox 유지한 row 정렬
4. header / items / totals / payment 구간 분리
5. 품목 행 조립
6. 날짜, 합계, 품목 구조 검증
7. 필요 시 로컬 Qwen 보조
8. 구조화된 JSON 응답 반환

### `POST /ai/ingredient/prediction`

OCR에서 나온 상품명을 입력받아 재료 테이블 기준으로 가장 가까운 재료를 예측합니다.

## 2. 파이프라인 고도화 내용

이 레포는 단순히 `이미지 -> OCR 텍스트`까지만 하지 않습니다. 현재 기준으로 아래 단계가 들어가 있습니다.

### 2-1. 전처리

- grayscale / contrast 보정
- OCR에 불리한 노이즈 완화
- full image 기준에서도 품목 블록을 최대한 복원하도록 전처리 경로 유지

관련 파일:
- `ocr_qwen/preprocess.py`
- `receipt_ocr.py`

### 2-2. OCR 라인 계약 고도화

- 텍스트만 유지하지 않고 bbox, center, page order를 같이 유지
- 후속 파서가 줄 순서와 공간 배치를 이용할 수 있게 설계

관련 파일:
- `ocr_qwen/services.py`
- `ocr_qwen/receipts.py`

### 2-3. 영수증 섹션 분리

- header
- items
- totals
- payment
- ignored

구간을 나눈 뒤 품목 파싱을 수행합니다.

이 단계가 필요한 이유:
- 안내문, 카드결제 문구, 세금/합계 줄이 품목으로 잘못 들어가는 문제를 줄이기 위해서입니다.

### 2-4. 품목 행 조립

현재 파서는 아래 유형을 처리하도록 고도화되어 있습니다.

- 컬럼형 `상품명 / 수량 / 금액`
- POS 한 줄형 `상품명 1 1,600`
- 바코드 다음 줄 상세형
- gift row `상품명 1 증정품`
- `상품명` 다음 줄에 숫자만 오는 2줄형

관련 파일:
- `ocr_qwen/receipts.py`
- `tests/test_receipt_quality_rules.py`

### 2-5. 검증 단계

추출 결과에 대해 다음을 다시 확인합니다.

- 날짜가 잡혔는지
- 합계와 품목 금액이 크게 어긋나는지
- 품목명이 지나치게 깨졌는지
- 숫자 줄이나 쿠폰 줄이 품목으로 섞였는지

결과는 응답의 아래 필드로 노출됩니다.

- `review_required`
- `review_reasons`
- `diagnostics`

### 2-6. 로컬 Qwen 보조

기본 동작은 OCR-only입니다.

로컬 Qwen이 켜져 있으면 품목명/구조 보정을 보조적으로 사용할 수 있습니다.

현재 방향:
- OCR이 메인
- Qwen은 보조
- Qwen 실패 시 전체 API가 죽지 않고 fallback

관련 파일:
- `ocr_qwen/qwen.py`
- `qwen_receipt_assistant.py`

## 3. 디렉터리 구조

```text
.
├── main.py
├── receipt_ocr.py
├── qwen_receipt_assistant.py
├── ocr_qwen/
│   ├── preprocess.py
│   ├── services.py
│   ├── receipts.py
│   ├── qwen.py
│   ├── ingredient_dictionary.py
│   └── ...
├── data/
│   ├── db/
│   ├── ingredient_alias.generated.json
│   ├── ingredient_master.generated.json
│   └── recipes_recommendation_seed.generated.json
├── tests/
└── docs/
```

## 4. 설치

현재 이 레포 기준으로 가장 직접적인 설치 방식은 아래입니다.

### 필수 패키지 설치

```powershell
pip install -r requirements.txt
```

선택적으로 가상환경을 써도 되지만, 이 레포 문서에서는 가상환경을 필수 전제로 두지 않습니다.

### 로컬 Qwen까지 사용할 경우

현재 코드 기준으로 local runtime을 쓰려면 `transformers`, `torch`가 필요합니다.

예시:

```powershell
pip install torch transformers accelerate safetensors sentencepiece
```

## 5. 실행

### FastAPI 서버 실행

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 단일 이미지 OCR 분석

```powershell
python receipt_ocr.py <영수증_이미지_경로>
```

### 결과 시각화

```powershell
python receipt_ocr.py <영수증_이미지_경로> --visualize
```

## 6. 로컬 Qwen 설정

기본값은 비활성입니다.

로컬 Qwen을 쓰려면 아래 환경변수를 설정합니다.

```env
ENABLE_LOCAL_QWEN=1
LOCAL_QWEN_MODEL_ID=Qwen/Qwen2.5-1.5B-Instruct
ALLOW_MODEL_DOWNLOAD=1
ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1
QWEN_MODEL=qwen2.5:latest
QWEN_TIMEOUT_SECONDS=8
QWEN_RECEIPT_MAX_TOKENS=256
```

설명:

- `ENABLE_LOCAL_QWEN=1`
  - `ocr_qwen/qwen.py`의 로컬 transformers 경로 활성화
- `LOCAL_QWEN_MODEL_ID`
  - 허깅페이스 모델 ID 또는 로컬 모델 경로
- `ALLOW_MODEL_DOWNLOAD=1`
  - 현재 구현의 local runtime gate
- `ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1`
  - `qwen_receipt_assistant.py` 경로 활성화

## 7. 공개 API

### `POST /ai/ocr/analyze`

입력:
- `multipart/form-data`
- `image`
- 선택 쿼리: `use_qwen=true|false`

응답 핵심 필드:
- `ocr_texts`
- `food_items`
- `food_count`
- `model`
- `vendor_name`
- `purchased_at`
- `totals`
- `diagnostics`

### `POST /ai/ingredient/prediction`

입력:

```json
{
  "product_names": ["국산콩 두부", "깻잎", "삼겹살"]
}
```

응답 핵심 필드:
- `matched`
- `unmatched`
- `matched_count`
- `unmatched_count`

매칭 순서:
- 상품 alias 정규화
- `data/receipt_rules/product_to_ingredient.json` 규칙 사전 확인
- DB exact match
- DB fuzzy match

open-set 처리:
- 사전에 없는 식품은 버리지 않고 `mapping_status=UNMAPPED`로 반환
- 비식품/제외 대상은 `mapping_status=EXCLUDED`로 반환
- 모든 항목에 `standard_product_name`, `item_type`를 포함

`matched` 항목에는 `mapping_source`, `standard_product_name`, `mapping_status`, `item_type`가 포함됩니다.

## 8. 검증

전체 테스트:

```powershell
python -m pytest -q
```

현재 테스트 범위:

- `/ai/ocr/analyze` 계약
- `/ai/ingredient/prediction` 계약
- 기존 `/api/...` 비노출
- `ReceiptOCR` 어댑터
- 영수증 파싱 규칙 회귀

## 9. 현재 상태 요약

샘플 기준:

- `img2.jpg`: 품목 2개 복원
- `img3.jpg`: 품목 4개, false positive 1건 남음
- `SE-...jpg`: 품목 9개 복원, totals mismatch 남음

warm path 처리 시간:

- `img2.jpg`: 약 4.17초
- `img3.jpg`: 약 2.37초
- `SE-...jpg`: 약 3.72초

## 10. 관련 문서

- `docs/API_SPEC.md`
- `docs/OCR_IMPLEMENTATION.md`
- `docs/OCR_QUALITY_BASELINE.md`
- `docs/OCR_TODO.md`
- `docs/releases/v0.1/README.md`
