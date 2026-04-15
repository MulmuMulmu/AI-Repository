# AI-Repository

영수증 OCR, 재료 매칭, 레시피 추천을 제공하는 FastAPI 서버입니다.

현재 기준 동작은 다음과 같습니다.

- 기본 경로: `PaddleOCR + rule-based parser`
- 선택 경로: `Qwen 보조`
- 운영 기본값: `Qwen 비활성`
- 핵심 엔드포인트: `/api/ocr/receipt`, `/api/ingredients/match`, `/api/recipes/recommend`

중요:
- 이 저장소는 현재 `Ollama 전용 구조`가 아닙니다.
- 기본 동작에 LLM이 필요하지 않습니다.
- Qwen은 명시적으로 활성화했을 때만 동작하는 선택 기능입니다.

## 1. 현재 구조

```text
.
├── main.py                          # FastAPI 진입점
├── receipt_ocr.py                   # legacy 호환 래퍼 / CLI 분석 도구
├── qwen_receipt_assistant.py        # 선택적 동기 Qwen 보조 유틸
├── ocr_qwen/
│   ├── preprocess.py                # 이미지 전처리
│   ├── services.py                  # OCR backend / parse service
│   ├── receipts.py                  # 영수증 row/section/item 파서
│   ├── qwen.py                      # Noop / OpenAI-compatible Qwen provider
│   ├── ingredient_dictionary.py     # alias / ingredient dictionary
│   └── ...
├── data/
│   ├── db/                          # recipes / ingredients / recipe_steps 등
│   ├── ingredient_alias.generated.json
│   ├── ingredient_master.generated.json
│   └── recipes_recommendation_seed.generated.json
├── tests/                           # OCR/API 회귀 테스트
└── docs/                            # 구현 / 품질 / 릴리스 문서
```

## 2. 현재 동작 방식

### OCR 경로

1. 이미지 업로드
2. 전처리
3. PaddleOCR 추출
4. row merge / section split / item parse
5. 결과 검증
6. 필요 시 선택적으로 Qwen 보조

### Qwen 정책

- 기본값은 `Noop`
- `use_qwen=true`여도 런타임이 없으면 OCR-only로 fallback
- Qwen 실패가 API 실패로 이어지지 않음

즉, 현재 시스템의 기준 엔진은 `PaddleOCR + 규칙 기반 파서`입니다.

## 3. 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Windows PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## 4. 실행

### FastAPI 서버

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 단일 이미지 OCR 분석

```bash
python receipt_ocr.py <영수증_이미지_경로>
```

### 결과 시각화

```bash
python receipt_ocr.py <영수증_이미지_경로> --visualize
```

## 5. 환경변수

### 기본 실행

아무 설정 없이도 OCR-only 경로는 동작합니다.

필수 환경변수:
- 없음

### 선택적 Qwen 보조 활성화

Qwen을 붙이고 싶을 때만 설정합니다.

```env
ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1
QWEN_BASE_URL=http://<openai-compatible-server>/v1
QWEN_API_KEY=<api-key>
QWEN_MODEL=qwen2.5:latest
QWEN_TIMEOUT_SECONDS=8
QWEN_RECEIPT_MAX_TOKENS=256
```

주의:
- `QWEN_BASE_URL`은 OpenAI-compatible endpoint 기준입니다.
- 특정 런타임이나 특정 배포 방식에 종속되지 않습니다.
- 현재 README에서는 더 이상 Ollama를 기본 전제로 설명하지 않습니다.

## 6. 주요 API

### `POST /api/ocr/receipt`

영수증 이미지를 받아 OCR 결과와 품목 추출 결과를 반환합니다.

요약:
- 입력: `multipart/form-data`, `image`
- 선택 파라미터: `use_qwen=true|false`
- 기본값: `true`
- 실제 동작: Qwen 런타임이 없으면 OCR-only fallback

응답 핵심 필드:

- `ocr_texts`
- `food_items`
- `food_count`
- `model`
- `vendor_name`
- `purchased_at`
- `totals`
- `diagnostics`

### `POST /api/ingredients/match`

OCR에서 추출한 상품명을 재료 테이블과 매칭합니다.

### `POST /api/recipes/recommend`

보유 재료 ID를 기반으로 레시피를 추천합니다.

### `GET /api/recipes/{recipeId}`

레시피 상세를 반환합니다.

### `GET /api/ingredients/search`

키워드로 재료를 검색합니다.

### `GET /api/health`

OCR, preprocess, bbox contract, qwen runtime 상태를 반환합니다.

## 7. 계약 주의사항

같은 품목 데이터라도 노출 기준이 다릅니다.

- `/api/ocr/receipt`
  - `food_items[].product_name`은 `normalized_name` 우선
  - 백엔드 연계용 legacy 계약 유지 목적

- `receipt_ocr.py`
  - `food_items[].product_name`은 `raw_name` 우선
  - OCR 품질 확인과 디버그 목적

## 8. 검증

전체 테스트:

```bash
python -m pytest -q
```

현재 기준 테스트 범위:

- OCR API 계약
- health 응답 형식
- `ReceiptOCR` 어댑터
- 영수증 파싱 규칙 회귀

## 9. 현재 한계

- 저해상도 실사 영수증에서는 OCR 오독이 남습니다.
- alias / 정규화 사전이 아직 충분하지 않습니다.
- 일부 영수증은 `total_mismatch`, `unresolved_items`가 발생합니다.
- CPU 환경에서 Qwen을 동기 경로에 붙이면 응답 지연이 커질 수 있습니다.

## 10. 관련 문서

- `docs/API_SPEC.md`
- `docs/OCR_IMPLEMENTATION.md`
- `docs/OCR_QUALITY_BASELINE.md`
- `docs/OCR_TODO.md`
- `docs/releases/v0.1/README.md`
