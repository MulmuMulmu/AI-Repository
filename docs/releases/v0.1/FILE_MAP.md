# v0.1 파일 변경 맵

기준:
- `origin/main @ e3e375db71a25a613ade39b6ad2039ac0bc9eb99`

목적:
- 어떤 파일이 추가/수정되었고, 각각이 어떤 책임을 갖는지 파일 단위로 빠르게 파악한다.

## 기존 파일 수정

| 경로 | 상태 | 변경 요약 | 영향 |
|------|------|-----------|------|
| `README.md` | 수정 | 실제 설치/실행 방식, 로컬 Qwen 설정, 고도화된 OCR 파이프라인 설명으로 재구성 | 레포 진입 문서가 현재 구조를 반영 |
| `docs/api/API_SPEC.md` | 수정 | 공개 API를 `/ai/ocr/analyze`, `/ai/ingredient/prediction` 두 개 기준으로 재정리 | 백엔드 연동 기준 문서 갱신 |
| `main.py` | 수정 | shared OCR backend, `ReceiptParseService` 연동, 공개 API를 `/ai/ocr/analyze`, `/ai/ingredient/prediction` 두 개로 정리 | 실제 서비스 진입점 변경 |
| `qwen_receipt_assistant.py` | 수정 | 환경변수 기반 활성화, 로컬 Qwen 보조, 실패 시 rule fallback | Qwen 실패가 API 실패로 번지지 않음 |
| `receipt_ocr.py` | 수정 | monolithic OCR 스크립트에서 호환 어댑터로 재구성 | CLI/내부 분석 도구가 새 엔진 사용 |
| `requirements.txt` | 수정 | FastAPI, Uvicorn, multipart, pytest 등 서버/검증 의존성 추가 | API 서버와 테스트 실행 가능 |

## 신규 패키지: `ocr_qwen/`

| 경로 | 상태 | 역할 |
|------|------|------|
| `ocr_qwen/__init__.py` | 추가 | 패키지 초기화 |
| `ocr_qwen/app.py` | 추가 | 독립 OCR/Qwen FastAPI 앱 진입점 |
| `ocr_qwen/env.py` | 추가 | 환경변수/런타임 설정 로딩 |
| `ocr_qwen/expiry.py` | 추가 | 유통기한 관련 보조 로직 |
| `ocr_qwen/ingredient_dictionary.py` | 추가 | ingredient alias / master dictionary 처리 |
| `ocr_qwen/preprocess.py` | 추가 | 이미지 전처리 |
| `ocr_qwen/qwen.py` | 추가 | `Noop`, local Qwen provider, 보조 추론 로직 |
| `ocr_qwen/receipts.py` | 추가 | 영수증 행 조립, 섹션 분리, 품목 파싱 핵심 |
| `ocr_qwen/recipes.json` | 추가 | OCR/Qwen 예시/보조 데이터 |
| `ocr_qwen/recommendations.py` | 추가 | 추천 보조 로직 |
| `ocr_qwen/services.py` | 추가 | `PaddleOcrBackend`, `ReceiptParseService` 등 서비스 계층 |

## 신규 테스트

| 경로 | 상태 | 역할 |
|------|------|------|
| `tests/__init__.py` | 추가 | 테스트 패키지 초기화 |
| `tests/helpers.py` | 추가 | 테스트 헬퍼 |
| `tests/test_ocr_api_contract.py` | 추가 | `/ai/ocr/analyze` 계약 유지 검증 |
| `tests/test_public_api_surface.py` | 추가 | 공개 API 표면과 기존 `/api/...` 비노출 검증 |
| `tests/test_ocr_service_adapter.py` | 추가 | `ReceiptOCR` 어댑터 검증 |
| `tests/test_receipt_quality_rules.py` | 추가 | 파서 규칙 회귀 검증 |

## 신규 데이터

| 경로 | 상태 | 역할 |
|------|------|------|
| `data/ingredient_alias.generated.json` | 추가 | OCR alias 정규화 데이터 |
| `data/ingredient_master.generated.json` | 추가 | ingredient master generated 데이터 |
| `data/recipes_recommendation_seed.generated.json` | 추가 | 추천 시드 데이터 |

## 신규 OCR 문서

| 경로 | 상태 | 역할 |
|------|------|------|
| `docs/architecture/OCR_IMPLEMENTATION.md` | 추가 | 현재 OCR 구조와 API 계약 설명 |
| `docs/datasets/OCR_QUALITY_BASELINE.md` | 추가 | 샘플 기준 품질/속도 검증 기록 |
| `docs/operations/OCR_TODO.md` | 추가 | 다음 작업 우선순위 |
| `docs/plans/2026-04-16-ocr-prototype-port-plan.md` | 추가 | 초기 이식 계획 |
| `docs/plans/2026-04-16-ocr-quality-iteration-design.md` | 추가 | 품질 고도화 설계 문서 |
| `docs/plans/2026-04-16-api-surface-doc-refresh-plan.md` | 추가 | 공개 API 축소 및 README 재정렬 계획 |

## 신규 릴리스 문서

| 경로 | 상태 | 역할 |
|------|------|------|
| `docs/releases/v0.1/README.md` | 추가 | v0.1 변경 개요 |
| `docs/releases/v0.1/FILE_MAP.md` | 추가 | 파일 단위 변경 맵 |
| `docs/releases/v0.1/VERIFICATION.md` | 추가 | 검증 명령과 결과 |

## 구조 변화 해석

### 변경 전

- `receipt_ocr.py`와 `qwen_receipt_assistant.py` 중심
- FastAPI 서버 기능이 약함
- 품질 기준과 회귀 테스트 부재

### 변경 후

- `main.py`는 서비스 게이트웨이
- `ocr_qwen/`은 실제 OCR 엔진
- `receipt_ocr.py`는 호환 어댑터
- `qwen_receipt_assistant.py`는 선택적 동기 보조기
- `tests/`와 `docs/`가 품질 기준을 잡음

## 문서 읽는 순서 추천

1. [v0.1 변경 개요](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/releases/v0.1/README.md)
2. [OCR 구현 노트](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/architecture/OCR_IMPLEMENTATION.md)
3. [검증 기록](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/releases/v0.1/VERIFICATION.md)
4. [OCR TODO](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/operations/OCR_TODO.md)
