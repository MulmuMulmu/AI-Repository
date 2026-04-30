# Docker Development Guide

## 목적

AI 레포의 로컬 개발환경을 Docker로 통일한다. 현재 구조는 OCR/Qwen 서비스와 추천 서비스를 분리한 2컨테이너 구성을 기준으로 한다.

## 구성

- `ocr-api`
  - `python:3.11-slim`
  - PaddleOCR + Qwen 보조 로직이 포함된 FastAPI 서버
  - 포트 `8000`
- `recommend-api`
  - 벡터 기반 추천 전용 FastAPI 서버
  - 포트 `8002`

중요:

- 로컬 Docker 기준 runtime 컨테이너는 **두 개만** 유지한다.
- GPU/Qwen 실험은 로컬 compose 서비스로 띄우지 않고, GCP에서 별도 이미지/VM으로 다룬다.
- `Dockerfile`의 `gpu-dev` target과 `cloudbuild.gpu.yaml`은 GCP 배포 자산으로만 유지한다.

## 사전 준비

### CPU 기본

- Docker Desktop

### GPU 실험

- 로컬 compose 기준으로는 쓰지 않는다.
- GPU/Qwen 실험은 GCP GPU 서버를 기준으로 한다.

## 빠른 시작

### 1. OCR/Qwen 기본 개발 서버

```powershell
docker compose up --build ocr-api
```

접속:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/openapi.json`
- Docs: `http://localhost:8000/docs`

### 2. 추천 서버

```powershell
docker compose up --build recommend-api
```

접속:

- API: `http://localhost:8002`
- OpenAPI: `http://localhost:8002/openapi.json`

## 환경변수

기본 예시는 [.env.example](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/.env.example)에 있다.

자주 쓰는 값:

- `PREWARM_PADDLEOCR_ON_STARTUP`
- `ENABLE_LOCAL_QWEN`
- `ALLOW_MODEL_DOWNLOAD`
- `LOCAL_QWEN_MODEL_ID`
- `LOCAL_QWEN_DEVICE_MAP`
- `LOCAL_QWEN_TORCH_DTYPE`
- `QWEN_OPENAI_COMPATIBLE_BASE_URL`
- `QWEN_OPENAI_COMPATIBLE_API_KEY`
- `QWEN_OPENAI_COMPATIBLE_MODEL`

로컬/CPU Docker 기본값은 `PREWARM_PADDLEOCR_ON_STARTUP=0`이다. PaddleOCR는 첫 OCR 요청 시 lazy-load한다. 컨테이너 시작 시 PaddleOCR를 바로 초기화하면 일부 Docker/CPU 환경에서 PaddlePaddle native crash가 발생할 수 있으므로 기본 개발 실행에서는 prewarm을 끈다.

## 볼륨 정책

- 소스코드는 bind mount로 연결된다: `.:/app`
- Hugging Face 캐시는 named volume으로 유지한다:
  - `ai-hf-cache:/root/.cache/huggingface`

## 권장 운영 방식

- OCR 개발: `ocr-api`
- 추천 개발: `recommend-api`
- GPU/Qwen rescue 검증: GCP GPU 서버
- 더 큰 모델 또는 외부 inference server를 붙일 때는 `QWEN_OPENAI_COMPATIBLE_*` 환경변수로 OpenAI-compatible provider를 연결한다.

## 종료

```powershell
docker compose down
```
