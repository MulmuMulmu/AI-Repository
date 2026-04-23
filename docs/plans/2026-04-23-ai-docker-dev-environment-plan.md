# AI Docker Dev Environment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** AI 레포를 Docker로 통일해서 CPU 기본 개발환경과 선택적 GPU 로컬 Qwen 실험 환경을 같은 저장소 안에서 재현 가능하게 만든다.

**Architecture:** 기본 개발은 `python:3.11-slim` 기반 단일 FastAPI 컨테이너로 통일한다. 선택적 GPU 실험은 별도 Docker target과 compose profile로 분리하고, `ocr_qwen/qwen.py`가 `device_map`과 `torch_dtype` 환경변수를 받아 실제 GPU 로딩이 가능하도록 보강한다.

**Tech Stack:** Docker, Docker Compose, FastAPI, PaddleOCR, Hugging Face Transformers, PyTorch, pytest

---

### Task 1: Docker 런타임 설계 고정

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `requirements.local-qwen.txt`

**Step 1: CPU 기본 이미지 정의**

- Python 3.11 slim
- OpenCV/PaddleOCR 실행에 필요한 시스템 패키지 설치
- `requirements.txt` 설치

**Step 2: GPU 실험 이미지 정의**

- CUDA runtime 기반 이미지
- `requirements.txt` + `requirements.local-qwen.txt` 설치
- `LOCAL_QWEN_DEVICE_MAP=auto`, `LOCAL_QWEN_TORCH_DTYPE=float16` 기본값 제공

**Step 3: compose 서비스 정의**

- `ai-api`: CPU 기본 개발 서비스
- `ai-api-gpu`: `gpu` profile 기반 선택 서비스
- healthcheck, bind mount, huggingface cache volume 포함

### Task 2: Qwen GPU 로딩 경로 보강

**Files:**
- Modify: `ocr_qwen/qwen.py`
- Test: `tests/test_qwen_runtime_config.py`

**Step 1: failing test 추가**

- `LOCAL_QWEN_DEVICE_MAP`
- `LOCAL_QWEN_TORCH_DTYPE`
- GPU 입력 디바이스 해석

**Step 2: 최소 구현**

- 환경변수 기반 model load kwargs 지원
- 입력 tensor/device 이동 helper 추가

### Task 3: 문서와 예시 환경 파일 정리

**Files:**
- Create: `.env.example`
- Create: `docs/operations/DOCKER_DEV.md`
- Modify: `README.md`
- Modify: `docs/INDEX.md`

**Step 1: 실행 문서 작성**

- CPU 기본 실행
- GPU 프로필 실행
- 현재 GPU 프로필이 local Qwen 실험용이라는 제약 명시

**Step 2: README 반영**

- Docker quick start
- 현재 API surface 설명 정리

### Task 4: 검증

**Files:**
- Test: `tests/test_qwen_runtime_config.py`

**Step 1: targeted test**

- `pytest tests/test_qwen_runtime_config.py -q`

**Step 2: 관련 회귀**

- `pytest tests/test_receipt_qwen_item_normalization.py -q`

**Step 3: 전체 확인**

- `pytest -q`
