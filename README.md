# AI-Repository

영수증 이미지를 분석해 식품 품목, 구매일자, 카테고리, 수량을 추출하고, 식재료 소비기한과 레시피 추천을 보조하는 FastAPI 서버입니다.

현재 저장소는 두 서비스로 나뉩니다.

### OCR/Qwen 서비스

- `POST /ai/ocr/analyze`
- `POST /ai/ingredient/prediction`

### 추천 서비스

- `POST /recommend`

이 저장소의 핵심은 단순 OCR이 아니라, 영수증 파싱 파이프라인을 실제 영수증 구조에 맞게 고도화한 점입니다.

문서 진입점:

- [docs/INDEX.md](docs/INDEX.md)
- [docs/operations/NORMAL_INPUT_CRITERIA.md](docs/operations/NORMAL_INPUT_CRITERIA.md)
- [docs/operations/RECAPTURE_GUIDELINES.md](docs/operations/RECAPTURE_GUIDELINES.md)
- [docs/specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md](docs/specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md)

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

식품 1건에 대해 구매일과 보관 방법을 받아 소비기한을 계산합니다.

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

### Docker 기준 빠른 시작

OCR/Qwen 기본 개발환경:

```powershell
docker compose up --build ocr-api
```

추천 서비스:

```powershell
docker compose up --build recommend-api
```

두 서비스를 같이 띄울 때:

```powershell
docker compose up --build ocr-api recommend-api
```

GPU/Qwen 실험은 로컬 compose 서비스가 아니라 GCP GPU 서버 기준으로 운영한다.

자세한 내용:

- [docs/operations/DOCKER_DEV.md](docs/operations/DOCKER_DEV.md)
- [docs/operations/GCP_DEPLOYMENT.md](docs/operations/GCP_DEPLOYMENT.md)

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

### OCR/Qwen FastAPI 서버 실행

```powershell
uvicorn app_ocr:app --host 0.0.0.0 --port 8000 --reload
```

### 추천 FastAPI 서버 실행

```powershell
uvicorn app_recommend:app --host 0.0.0.0 --port 8002 --reload
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
LOCAL_QWEN_DEVICE_MAP=auto
LOCAL_QWEN_TORCH_DTYPE=float16
LOCAL_QWEN_RECEIPT_EXTRACT_MAX_NEW_TOKENS=160
LOCAL_QWEN_RECEIPT_ITEM_MAX_NEW_TOKENS=64
LOCAL_QWEN_RECIPE_EXPLANATION_MAX_NEW_TOKENS=160

QWEN_OPENAI_COMPATIBLE_BASE_URL=
QWEN_OPENAI_COMPATIBLE_API_KEY=
QWEN_OPENAI_COMPATIBLE_MODEL=
QWEN_OPENAI_COMPATIBLE_TIMEOUT_SECONDS=30
```

설명:

- `ENABLE_LOCAL_QWEN=1`
  - `ocr_qwen/qwen.py`의 로컬 transformers 경로 활성화
- `LOCAL_QWEN_MODEL_ID`
  - 허깅페이스 모델 ID 또는 로컬 모델 경로
- `ALLOW_MODEL_DOWNLOAD=1`
  - 현재 구현의 local runtime gate
- `LOCAL_QWEN_DEVICE_MAP`
  - 로컬 transformers Qwen 로딩 시 `device_map` 옵션
- `LOCAL_QWEN_TORCH_DTYPE`
  - 로컬 transformers Qwen 로딩 시 `torch_dtype` 옵션
- `QWEN_OPENAI_COMPATIBLE_*`
  - OpenAI-compatible inference server를 provider로 붙일 때 사용

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

### 상품명 정규화와 재료 매핑

OCR/Qwen 서비스는 상품명, 카테고리, 수량을 반환하는 데 집중합니다.
상품명을 백엔드 재료 DB의 `ingredientId`로 확정하는 정규화/매핑은 백엔드 내부 흐름에서 처리합니다.
따라서 별도 공개 매칭 API는 제공하지 않습니다.

### `POST /ai/ingredient/prediction`

입력:

```json
{
  "item_name": "양파",
  "purchase_date": "2026-04-10",
  "storage_method": "냉장",
  "category": "채소/과일"
}
```

응답 핵심 필드:
- `expiry_date`
- `d_day`
- `risk_level`
- `confidence`
- `method`
- `reason`

## 8. 검증

전체 테스트:

```powershell
python -m pytest -q
```

현재 테스트 범위:

- `/ai/ocr/analyze` 계약
- 매칭 API 비노출 계약
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

- `docs/api/API_SPEC.md`
- `docs/api/RECOMMEND_API_SPEC.md`
- `docs/architecture/OCR_IMPLEMENTATION.md`
- `docs/architecture/PROJECT_PROCESS_AND_RATIONALE.md`
- `docs/datasets/OCR_QUALITY_BASELINE.md`
- `docs/operations/OCR_TODO.md`
- `docs/releases/v0.1/README.md`
