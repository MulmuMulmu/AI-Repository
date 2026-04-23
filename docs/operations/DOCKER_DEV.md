# Docker Development Guide

## 목적

AI 레포의 로컬 개발환경을 Docker로 통일한다. 기본 경로는 CPU 기반 FastAPI 개발 서버이고, 선택적으로 GPU 프로필을 켜서 local Qwen 실험 경로를 사용할 수 있다.

## 구성

- 기본 서비스: `ai-api`
  - `python:3.11-slim`
  - PaddleOCR + FastAPI 개발 서버
  - 포트 `8000`
- 선택 서비스: `ai-api-gpu`
  - `gpu` profile
  - CUDA runtime + local Qwen 의존성 포함
  - 포트 `8001`

중요:

- 현재 GPU 프로필은 **local transformers Qwen 실험용**이다.
- 현재 `requirements.txt`는 `paddlepaddle` CPU 패키지 기준이라서, Docker GPU 프로필을 켠다고 PaddleOCR이 자동으로 GPU로 바뀌지는 않는다.
- 즉 현재 GPU 프로필의 실질적 목적은 `ocr_qwen/qwen.py`의 local Qwen 경로를 GPU에 올리는 것이다.

## 사전 준비

### CPU 기본

- Docker Desktop

### GPU 프로필

- Docker Desktop + WSL2
- NVIDIA 드라이버
- NVIDIA Container Toolkit

## 빠른 시작

### 1. CPU 기본 개발 서버

```powershell
docker compose up --build ai-api
```

접속:

- API: `http://localhost:8000`
- OpenAPI: `http://localhost:8000/openapi.json`
- Docs: `http://localhost:8000/docs`

### 2. GPU 프로필로 local Qwen 실험

```powershell
docker compose --profile gpu up --build ai-api-gpu
```

접속:

- API: `http://localhost:8001`

기본 환경값:

- `ENABLE_LOCAL_QWEN=1`
- `ALLOW_MODEL_DOWNLOAD=1`
- `LOCAL_QWEN_DEVICE_MAP=auto`
- `LOCAL_QWEN_TORCH_DTYPE=float16`

## 환경변수

기본 예시는 [.env.example](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/.env.example)에 있다.

자주 쓰는 값:

- `ENABLE_LOCAL_QWEN`
- `ALLOW_MODEL_DOWNLOAD`
- `LOCAL_QWEN_MODEL_ID`
- `LOCAL_QWEN_DEVICE_MAP`
- `LOCAL_QWEN_TORCH_DTYPE`
- `QWEN_OPENAI_COMPATIBLE_BASE_URL`
- `QWEN_OPENAI_COMPATIBLE_API_KEY`
- `QWEN_OPENAI_COMPATIBLE_MODEL`

## 볼륨 정책

- 소스코드는 bind mount로 연결된다: `.:/app`
- Hugging Face 캐시는 named volume으로 유지한다:
  - `ai-hf-cache:/root/.cache/huggingface`

## 권장 운영 방식

- 일상 개발: `ai-api`
- Qwen rescue 검증: `ai-api-gpu`
- 더 큰 모델 또는 외부 inference server를 붙일 때는 `QWEN_OPENAI_COMPATIBLE_*` 환경변수로 OpenAI-compatible provider를 연결한다.

## 종료

```powershell
docker compose down
```

GPU 프로필까지 같이 내릴 때:

```powershell
docker compose --profile gpu down
```
