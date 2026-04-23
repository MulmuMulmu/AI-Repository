# API Surface And README Refresh Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 공개 API를 `/ai/ocr/analyze`, `/ai/ingredient/prediction` 두 개로 축소하고, README/API 문서를 현재 실제 실행 방식과 고도화된 OCR 파이프라인 기준으로 재작성한다.

**Architecture:** `main.py`의 공개 라우트 이름을 새 표면으로 바꾸고, 기존 `/api/...` 라우트는 제거한다. 테스트는 새 라우트와 비노출 조건을 먼저 고정하고, README와 `docs/api/API_SPEC.md`는 로컬 Qwen 실행과 실제 파이프라인 구조를 기준으로 다시 쓴다.

**Tech Stack:** FastAPI, Pydantic, PaddleOCR, local Qwen runtime, pytest

---

### Task 1: 라우트 표면 테스트 고정

**Files:**
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\tests\test_ocr_api_contract.py`
- Create: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\tests\test_public_api_surface.py`

**Step 1: `/ai/ocr/analyze` 계약 테스트로 변경**

- 기존 `/api/ocr/receipt` 호출을 `/ai/ocr/analyze`로 바꾼다.

**Step 2: `/ai/ingredient/prediction` 테스트 추가**

- 입력 `product_names`를 보내면 matched/unmatched 구조가 반환되는 테스트를 쓴다.

**Step 3: 기존 `/api/...` 라우트 비노출 테스트 추가**

- `/api/ocr/receipt`, `/api/ingredients/match`, `/api/health`가 404인지 확인한다.

**Step 4: 테스트를 실행해 실패 확인**

Run: `python -m pytest C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\tests\test_ocr_api_contract.py C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\tests\test_public_api_surface.py -q`

### Task 2: `main.py` 공개 라우트 정리

**Files:**
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\main.py`

**Step 1: OCR 분석 라우트 이름 변경**

- `POST /api/ocr/receipt`를 `POST /ai/ocr/analyze`로 바꾼다.

**Step 2: 재료 예측 라우트 이름 변경**

- `POST /api/ingredients/match`를 `POST /ai/ingredient/prediction`로 바꾼다.

**Step 3: 이번 범위 밖 라우트 제거**

- health, recipes recommend, recipe detail, ingredient search를 공개 표면에서 제거한다.

**Step 4: 최소 구현으로 테스트 통과**

- 테스트가 기대하는 응답 계약만 맞춘다.

### Task 3: README/API 문서 재작성

**Files:**
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\README.md`
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\docs\API_SPEC.md`
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\docs\OCR_IMPLEMENTATION.md`
- Modify: `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh\docs\releases\v0.1\README.md`

**Step 1: README를 현재 구조 기준으로 재작성**

- 설치/실행을 현재 실제 흐름 기준으로 정리한다.
- 로컬 Qwen 실행 기준을 우선 서술한다.
- 파이프라인 고도화 내용을 자세히 설명한다.

**Step 2: API 명세를 2개 엔드포인트 기준으로 재구성**

- `/ai/ocr/analyze`
- `/ai/ingredient/prediction`

**Step 3: 구현 문서의 Qwen 설명을 로컬 기준으로 맞춘다**

- OpenAI-compatible 중심 표현을 빼고, local runtime 우선으로 설명한다.

### Task 4: 전체 검증

**Files:**
- Verify only

**Step 1: 전체 테스트 실행**

Run: `python -m pytest -q`

**Step 2: diff 확인**

Run: `git -C C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh diff -- README.md docs/api/API_SPEC.md docs/architecture/OCR_IMPLEMENTATION.md main.py tests`
