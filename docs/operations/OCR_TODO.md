# OCR TODO

기준 레포:
- `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`

목적:
- 현재 PP-OCRv5 + rule-based parser 이식본을 기준으로, 실제 운영 가능한 수준까지 품질과 응답 속도를 단계적으로 끌어올린다.

## 우선순위 1. 품질

### 1-1. OCR alias / 품목 정규화 사전 확장

- 대상 파일:
  - `ocr_qwen/ingredient_dictionary.py`
  - `data/ingredient_alias.generated.json`
  - `ocr_qwen/receipts.py`
- 작업:
  - 실사 샘플에서 반복적으로 깨지는 품목명 alias를 누적한다.
  - raw 상품명과 표준 재료명/상품명을 분리해 관리한다.
  - `unknown_item`으로 남는 품목에 대해 alias fallback을 추가한다.
- 현재 대표 문제:
  - `투썸딸기피지`
  - `어쉬밀크클릿 [`
  - `초코빼빼로지암 L`
  - `속이면한 누룸지`

### 1-2. false positive row 제거 강화

- 대상 파일:
  - `ocr_qwen/receipts.py`
- 작업:
  - 숫자 위주 줄, 바코드 꼬리 줄, 카드/승인/광고성 줄을 더 엄격히 제거한다.
  - item window 밖 줄이 품목으로 들어오지 않도록 exclusion 규칙을 추가한다.
- 현재 대표 문제:
  - `img3.jpg`의 `[(야] 7 -11,760`

### 1-3. totals mismatch 감소

- 대상 파일:
  - `ocr_qwen/receipts.py`
  - `ocr_qwen/services.py`
- 작업:
  - gift row, discount row, subtotal row를 품목 합산에서 제외하는 규칙을 보강한다.
  - 품목 합계와 `payment_amount` 비교 시 허용 오차와 제외 규칙을 명확히 분리한다.
- 현재 대표 문제:
  - `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

## 우선순위 2. 속도

### 2-1. OCR warm path 최적화

- 대상 파일:
  - `main.py`
  - `ocr_qwen/services.py`
- 작업:
  - startup warm-up 경로를 유지하되, 재초기화가 없는지 확인한다.
  - 이미지 크기 기반 resize 정책을 정리해 과도한 full-resolution OCR을 줄인다.
  - full image와 crop path를 선택적으로 나누는지 검토한다.
- 현재 기준:
  - warm-up 약 11.1초
  - warm parse 약 2.3~4.2초

### 2-2. Qwen 호출을 저신뢰 케이스로 한정

- 대상 파일:
  - `ocr_qwen/services.py`
  - `ocr_qwen/qwen.py`
  - `qwen_receipt_assistant.py`
- 작업:
  - 기본 경로는 OCR-only 유지
  - `low_confidence`, `unknown_item`, `missing_quantity_or_unit`에만 선택적으로 Qwen 보정 적용
  - timeout, max tokens, fallback 조건을 더 엄격히 둔다

## 우선순위 3. 데이터셋

### 3-1. 실사 골든셋 1차 구축

- 대상 파일:
  - `tests/test_receipt_quality_rules.py`
  - `docs/datasets/OCR_QUALITY_BASELINE.md`
- 작업:
  - 최소 100장 목표로 영수증 샘플을 업종별로 분류한다.
  - 대형마트, 편의점, 동네마트, 카페, 베이커리, 배달/포장, 키오스크, 비식품 혼합 영수증으로 나눈다.
  - 각 샘플에 정답 JSON을 붙인다.

### 3-2. 실패 샘플 누적 규칙 수립

- 대상 파일:
  - `docs/datasets/OCR_QUALITY_BASELINE.md`
  - `docs/operations/OCR_TODO.md`
- 작업:
  - 운영/테스트 중 실패 케이스를 즉시 편입하는 규칙을 만든다.
  - 샘플 추가 시 raw image, expected JSON, failure note를 같이 보관한다.

## 우선순위 4. 검증

### 4-1. 회귀 테스트 확대

- 대상 파일:
  - `tests/test_ocr_api_contract.py`
  - `tests/test_public_api_surface.py`
  - `tests/test_ocr_service_adapter.py`
  - `tests/test_receipt_quality_rules.py`
- 작업:
  - 현재 계약 테스트 외에 실사 기반 parser 회귀 테스트를 더 추가한다.
  - single-line, gift, barcode-detail, totals mismatch, false positive 제거 케이스를 각각 fixture로 고정한다.

### 4-2. 정량 지표 문서화

- 대상 파일:
  - `docs/datasets/OCR_QUALITY_BASELINE.md`
- 작업:
  - 날짜 정확도
  - item precision / recall
  - total consistency accuracy
  - review flag rate
  - warm latency

## 우선순위 5. 운영 연계

### 5-1. API 계약 명확화

- 대상 파일:
  - `main.py`
  - `docs/architecture/OCR_IMPLEMENTATION.md`
- 작업:
  - `/ai/ocr/analyze`는 `normalized_name` 우선임을 유지
  - `receipt_ocr.py`는 raw 품목명 우선임을 문서와 코드 주석으로 고정
  - `diagnostics`, `review_required`, `review_reasons` 활용 규칙을 백엔드와 합의한다.

### 5-2. fallback 정책 정리

- 대상 파일:
  - `ocr_qwen/app.py`
  - `ocr_qwen/qwen.py`
- 작업:
  - qwen runtime 사용 가능 여부
  - fallback 시 응답 보장 범위

## 바로 다음 액션

1. `ocr_qwen/receipts.py`에서 숫자형 false positive 제거 규칙을 먼저 추가한다.
2. 실사 샘플 기준 alias 사전을 확장한다.
3. `SE` 케이스 totals mismatch 원인을 고정 테스트로 만든다.
4. Qwen은 low-confidence item에만 제한적으로 연결한다.
