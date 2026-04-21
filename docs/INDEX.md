# Documentation Index

이 문서는 현재 저장소의 문서 진입점이다.

## 권장 읽기 순서

1. 현재 구현 상태
   - [status/OCR_PIPELINE_STATUS_2026-04-18.md](status/OCR_PIPELINE_STATUS_2026-04-18.md)
2. 오늘 세션에서 합의한 업데이트
   - [updates/2026-04-18-session-update.md](updates/2026-04-18-session-update.md)
3. 구현 개요
   - [OCR_IMPLEMENTATION.md](OCR_IMPLEMENTATION.md)
4. 남은 작업
   - [OCR_TODO.md](OCR_TODO.md)
5. 운영 가이드
   - [guides/NORMAL_INPUT_CRITERIA.md](guides/NORMAL_INPUT_CRITERIA.md)
   - [guides/RECAPTURE_GUIDELINES.md](guides/RECAPTURE_GUIDELINES.md)
6. 합성데이터 규격
   - [specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md](specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md)
7. 품질 기준/데이터셋
   - [OCR_QUALITY_BASELINE.md](OCR_QUALITY_BASELINE.md)
   - [RECEIPT_GOLDSET_BASELINE_2026-04-16.md](RECEIPT_GOLDSET_BASELINE_2026-04-16.md)
   - [RECEIPT_SILVERSET.md](RECEIPT_SILVERSET.md)
   - [RECEIPT_RULE_CANDIDATES_2026-04-16.md](RECEIPT_RULE_CANDIDATES_2026-04-16.md)
8. 릴리스 기준 문서
   - [releases/v0.1/README.md](releases/v0.1/README.md)
   - [releases/v0.1/FILE_MAP.md](releases/v0.1/FILE_MAP.md)
   - [releases/v0.1/VERIFICATION.md](releases/v0.1/VERIFICATION.md)

## 문서 카테고리

### Core

- `README.md`
  - 저장소 개요, 실행 방법, 공개 API
- `API_SPEC.md`
  - 공개 API 계약 정리
- `OCR_IMPLEMENTATION.md`
  - OCR 파이프라인 구현 개요
- `OCR_TODO.md`
  - 우선순위 기반 남은 작업
- `OCR_QUALITY_BASELINE.md`
  - 품질 검증/정량 지표 기준

### Dataset / Rules

- `RECEIPT_GOLDSET_BASELINE_2026-04-16.md`
- `RECEIPT_SILVERSET.md`
- `RECEIPT_RULE_CANDIDATES_2026-04-16.md`

### Guides

- `guides/*`
  - 정상 입력 기준, 재촬영 기준, 운영 가이드

### Specs

- `specs/*`
  - 합성데이터 생성 규격, 검증용 스키마/정책

### Release

- `releases/v0.1/*`
  - v0.1 브랜치 기준 파일 맵, 검증, 요약

### Plans

- `plans/*`
  - 개별 구현 계획 및 작업 설계 문서

### Status

- `status/*`
  - 특정 날짜 기준 현재 구현 상태와 빈칸

### Updates

- `updates/*`
  - 날짜별 세션 요약, 합의 사항, 변경 내역

## 현재 문서화 원칙

- 구현 개요와 작업 계획은 분리한다.
- 품질 기준 문서와 실제 세션 업데이트 문서는 분리한다.
- 날짜가 들어간 문서는 시점 기준 상태 기록으로 유지한다.
- 루트 `README.md`는 입문용, `docs/`는 운영/개발용 기준 문서로 유지한다.
