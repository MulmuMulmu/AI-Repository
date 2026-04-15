# v0.1 변경 개요

기준 비교 브랜치:
- `origin/main`

기준 커밋:
- `e3e375db71a25a613ade39b6ad2039ac0bc9eb99`

문서 목적:
- 기존 `AI-Repository`에서 현재 작업본이 무엇을 어떻게 바꿨는지 한 번에 파악할 수 있게 정리한다.
- 코드 리뷰, 인수인계, 백엔드 연동, 추후 브랜치 정리에 바로 사용할 수 있는 기준 문서로 사용한다.

## 변경 규모

기준 시점에서 `origin/main` 대비 변경은 아래 두 축으로 나뉜다.

- 기존 파일 수정: 6개
- 신규 파일 추가: 28개

세부 분류:

| 구분 | 개수 | 설명 |
|------|------|------|
| 기존 런타임 파일 수정 | 6 | README, API 명세, FastAPI 엔트리, OCR/Qwen 호환 레이어, 의존성 |
| 신규 OCR 패키지 | 11 | `ocr_qwen/` 패키지 이식 |
| 신규 테스트 | 6 | 계약/헬스/어댑터/품질 회귀 테스트 |
| 신규 생성 데이터 | 3 | ingredient alias, ingredient master, recommendation seed |
| 신규 OCR 문서 | 5 | 구현 노트, 품질 기준, TODO, 설계/이식 계획 |
| 신규 릴리스 문서 | 3 | 이 문서 묶음 |

## 가장 큰 변화

### 1. 단일 스크립트 기반 OCR에서 패키지 기반 OCR 엔진으로 변경

기존:
- `receipt_ocr.py` 중심의 단일 흐름
- Qwen 보조가 강하게 결합된 구조

현재:
- `ocr_qwen/` 패키지로 전처리, OCR 백엔드, 레이아웃 파서, Qwen provider, 추천/유통기한 보조 로직을 분리
- `receipt_ocr.py`는 호환 어댑터 역할만 수행

영향:
- 테스트 가능성이 높아졌다.
- `FastAPI`와 CLI가 같은 OCR 서비스 계층을 공유한다.
- 추후 Qwen 교체나 비활성화가 쉬워졌다.

### 2. `/api/ocr/receipt`가 legacy 계약을 유지하면서도 더 많은 메타데이터를 반환

유지:
- `ocr_texts`
- `food_items`
- `food_count`
- `model`

추가:
- `vendor_name`
- `purchased_at`
- `totals`
- `diagnostics`

영향:
- 기존 연동 지점을 깨지 않으면서 디버깅/품질 판단용 정보를 백엔드가 활용할 수 있게 됐다.

### 3. Qwen 사용 전략이 “항상 사용”에서 “best-effort 보조”로 변경

기존 방향:
- Qwen이 있으면 적극 사용

현재 방향:
- 기본값은 OCR-only
- `use_qwen=true`여도 로컬 OpenAI-compatible Qwen 환경이 준비되지 않았으면 fallback
- `qwen_receipt_assistant.py`는 환경변수 `ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1`일 때만 동기 호출

영향:
- CPU 환경에서 응답이 멈추는 문제를 줄였다.
- 운영 안정성을 우선하는 구조로 바뀌었다.

### 4. 품질 검증 기준이 문서와 테스트로 명시됨

추가된 기준:
- 계약 테스트
- health 응답 테스트
- `ReceiptOCR` 어댑터 테스트
- 영수증 파싱 규칙 회귀 테스트
- 샘플 영수증 품질 기준 문서

영향:
- “좋아 보인다”가 아니라 재현 가능한 기준으로 품질을 판단할 수 있다.

## 변경 영역 요약

### 런타임

- `main.py`
- `receipt_ocr.py`
- `qwen_receipt_assistant.py`
- `ocr_qwen/`

핵심:
- FastAPI 진입점에서 shared OCR backend warm-up
- health endpoint 확장
- parse API가 `ReceiptParseService`를 직접 사용

### 데이터

- `data/ingredient_alias.generated.json`
- `data/ingredient_master.generated.json`
- `data/recipes_recommendation_seed.generated.json`

핵심:
- OCR 정규화와 추천 seed를 위한 generated 데이터가 추가됐다.

### 테스트

- `tests/test_ocr_api_contract.py`
- `tests/test_ocr_health.py`
- `tests/test_ocr_service_adapter.py`
- `tests/test_receipt_quality_rules.py`

핵심:
- 기존 레포에는 없던 OCR 회귀 테스트 층이 생겼다.

### 문서

- `docs/OCR_IMPLEMENTATION.md`
- `docs/OCR_QUALITY_BASELINE.md`
- `docs/OCR_TODO.md`
- `docs/plans/2026-04-16-ocr-prototype-port-plan.md`
- `docs/plans/2026-04-16-ocr-quality-iteration-design.md`

핵심:
- 구현 배경, 현재 품질, 다음 우선순위를 따로 추적할 수 있게 됐다.

## 이 브랜치에서 바로 확인할 문서

1. [파일 변경 맵](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/releases/v0.1/FILE_MAP.md)
2. [검증 기록](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/releases/v0.1/VERIFICATION.md)
3. [OCR 구현 노트](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/OCR_IMPLEMENTATION.md)
4. [OCR 품질 기준](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/OCR_QUALITY_BASELINE.md)
5. [OCR TODO](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/OCR_TODO.md)
