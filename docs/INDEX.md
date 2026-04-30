# Documentation Index

이 문서는 현재 AI 레포의 canonical 문서 진입점이다.

## 권장 읽기 순서

1. 구조와 제품 방향
   - [architecture/AI_PIPELINE_QA_GUIDE.md](architecture/AI_PIPELINE_QA_GUIDE.md)
   - [architecture/PROJECT_PROCESS_AND_RATIONALE.md](architecture/PROJECT_PROCESS_AND_RATIONALE.md)
   - [architecture/BACKEND_AI_ADAPTER_HANDOFF.md](architecture/BACKEND_AI_ADAPTER_HANDOFF.md)
   - [architecture/OCR_IMPLEMENTATION.md](architecture/OCR_IMPLEMENTATION.md)
2. 현재 API 계약
   - [api/API_SPEC.md](api/API_SPEC.md)
   - [api/RECOMMEND_API_SPEC.md](api/RECOMMEND_API_SPEC.md)
3. 운영 기준
   - [operations/NORMAL_INPUT_CRITERIA.md](operations/NORMAL_INPUT_CRITERIA.md)
   - [operations/RECAPTURE_GUIDELINES.md](operations/RECAPTURE_GUIDELINES.md)
   - [operations/DOCKER_DEV.md](operations/DOCKER_DEV.md)
   - [operations/GCP_DEPLOYMENT.md](operations/GCP_DEPLOYMENT.md)
   - [operations/APPS_IN_TOSS_RELEASE_POLICY_CHECK.md](operations/APPS_IN_TOSS_RELEASE_POLICY_CHECK.md)
   - [operations/OCR_TODO.md](operations/OCR_TODO.md)
4. 통합테스트
   - [integration/LOCAL_INTEGRATION_TEST_PLAN.md](integration/LOCAL_INTEGRATION_TEST_PLAN.md)
   - [integration/LOCAL_INTEGRATION_TEST_REPORT_2026-04-30.md](integration/LOCAL_INTEGRATION_TEST_REPORT_2026-04-30.md)
   - [integration/SYSTEM_FLOW_TEST_REPORT_2026-04-30.md](integration/SYSTEM_FLOW_TEST_REPORT_2026-04-30.md)
5. 품질/데이터셋
   - [datasets/OCR_QUALITY_BASELINE.md](datasets/OCR_QUALITY_BASELINE.md)
   - [datasets/RECEIPT_SILVERSET.md](datasets/RECEIPT_SILVERSET.md)
   - [specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md](specs/SYNTHETIC_RECEIPT_DATASET_SPEC.md)
6. 날짜별 기록
   - [history/status/OCR_PIPELINE_STATUS_2026-04-18.md](history/status/OCR_PIPELINE_STATUS_2026-04-18.md)
   - [history/updates/2026-04-18-session-update.md](history/updates/2026-04-18-session-update.md)
   - [history/baselines/RECEIPT_GOLDSET_BASELINE_2026-04-21.md](history/baselines/RECEIPT_GOLDSET_BASELINE_2026-04-21.md)

## 문서 구조

### `api/`

- 현재 살아있는 API 계약

### `architecture/`

- 시스템 구조
- 프로세스 흐름
- 기술 선택 이유
- 질문 답변용 AI 파이프라인 요약

### `operations/`

- 운영 기준
- 입력/재촬영 정책
- Docker 개발환경
- 남은 작업

### `integration/`

- 백엔드, 프론트, AI 로컬 통합테스트 절차
- Docker 포트 표
- smoke 시나리오와 통과 기준

### `datasets/`

- 품질 기준
- silver/gold 데이터셋 운영 방식

### `specs/`

- 합성데이터 생성 규격

### `history/`

- 날짜별 상태 기록
- 세션 업데이트
- 과거 baseline

### `plans/`

- 구현 계획 문서

### `releases/`

- 버전별 릴리스 문서
