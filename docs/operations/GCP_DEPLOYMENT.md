# GCP Deployment Guide

## 목적

이 문서는 현재 AI 레포를 GCP에 **충돌 없이** 올리는 기준 경로를 정리한다.

현재 권장 배포 구조:

- **OCR/Qwen API**: Cloud Run
- **추천 API**: Cloud Run
- **GPU Qwen 추론 서버**: Compute Engine GPU VM

이 구조를 권장하는 이유:

- OCR/재료예측/추천 API는 CPU 기본 경로로도 운영 가능하다.
- Qwen은 현재 메인 파서가 아니라 hard-case rescue용 선택 기능이다.
- GPU 리소스는 상시 API 전체에 붙이기보다, 별도 추론 서버로 분리하는 편이 비용과 운영 복잡도 측면에서 낫다.

공식 참고:

- [Cloud Run container deploy](https://cloud.google.com/run/docs/deploying)
- [Artifact Registry -> Cloud Run](https://cloud.google.com/artifact-registry/docs/integrate-cloud-run)
- [Create VM with GPUs](https://cloud.google.com/compute/docs/gpus/create-vm-with-gpus)
- [Choose a Deep Learning VM image](https://docs.cloud.google.com/deep-learning-vm/docs/images)

---

## 1. 배포 원칙

GCP 배포 순서는 아래다.

1. 소스코드를 Docker image로 빌드
2. 이미지를 Artifact Registry에 push
3. OCR/Qwen API는 Cloud Run에 배포
4. 추천 API는 별도 Cloud Run에 배포
5. GPU 추론은 별도 GPU VM에서 컨테이너로 실행
6. OCR/Qwen API는 `.env` 기준으로 GPU 추론 서버를 OpenAI-compatible provider로 호출

즉, **컨테이너를 먼저 만드는 게 아니라 이미지가 먼저**다.

---

## 2. 현재 저장소에서 제공하는 배포 파일

- [cloudbuild.cpu.yaml](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/cloudbuild.cpu.yaml)
- [cloudbuild.recommend.yaml](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/cloudbuild.recommend.yaml)
- [cloudbuild.gpu.yaml](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/cloudbuild.gpu.yaml)
- [create-artifact-registry.ps1](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/scripts/gcp/create-artifact-registry.ps1)
- [build-image.ps1](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/scripts/gcp/build-image.ps1)
- [deploy-cloud-run.ps1](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/scripts/gcp/deploy-cloud-run.ps1)
- [create-gpu-vm.ps1](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/scripts/gcp/create-gpu-vm.ps1)

핵심 포인트:

- 로컬 Docker daemon이 없어도 `gcloud builds submit`으로 **원격 빌드**가 가능하다.
- 즉, 배포를 위해 반드시 로컬 Docker를 직접 돌릴 필요는 없다.

---

## 3. OCR/Qwen API 배포

### 3-1. Artifact Registry 생성

```powershell
pwsh ./scripts/gcp/create-artifact-registry.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Region "asia-northeast3" `
  -Repository "mulmumu-ai"
```

### 3-2. Cloud Build로 CPU 이미지 빌드/푸시

```powershell
pwsh ./scripts/gcp/build-image.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Profile "cpu" `
  -Region "asia-northeast3" `
  -Repository "mulmumu-ai" `
  -ImageName "ocr-api" `
  -Tag "v0.2"
```

### 3-3. Cloud Run 배포

```powershell
pwsh ./scripts/gcp/deploy-cloud-run.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Region "asia-northeast3" `
  -ServiceName "mulmumu-ocr-api" `
  -Repository "mulmumu-ai" `
  -ImageName "ocr-api" `
  -Tag "v0.2" `
  -AllowUnauthenticated
```

기본 정책:

- `ENABLE_LOCAL_QWEN=0`
- `ALLOW_MODEL_DOWNLOAD=0`

즉 Cloud Run은 **OCR/Qwen API 서버**로 사용한다.

---

## 4. 추천 API 배포

```powershell
pwsh ./scripts/gcp/build-image.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Profile "recommend" `
  -Region "asia-northeast3" `
  -Repository "mulmumu-ai" `
  -ImageName "recommend-api" `
  -Tag "v0.2"
```

추천 API는 별도 Cloud Run 서비스로 배포한다.

---

## 5. GPU Qwen 서버 배포

### 4-1. GPU용 이미지 빌드/푸시

```powershell
pwsh ./scripts/gcp/build-image.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Profile "gpu" `
  -Region "asia-northeast3" `
  -Repository "mulmumu-ai" `
  -ImageName "ocr-api-gpu" `
  -Tag "v0.2"
```

### 4-2. GPU VM 생성

```powershell
pwsh ./scripts/gcp/create-gpu-vm.ps1 `
  -ProjectId "<PROJECT_ID>" `
  -Zone "asia-northeast3-b" `
  -InstanceName "mulmumu-qwen-gpu"
```

현재 기본값:

- machine type: `g2-standard-8`
- GPU: `nvidia-l4 x1`
- image family: `common-cu128-ubuntu-2204-nvidia-570`

### 4-3. VM 안에서 컨테이너 실행

현재 스크립트는 **VM 생성까지만 자동화**한다.

이후 VM 안에서 해야 할 일:

1. Docker 설치 또는 확인
2. Artifact Registry 인증
3. GPU용 컨테이너 실행
4. OpenAI-compatible endpoint 노출

이 부분은 실제 네트워크, 방화벽, TLS, reverse proxy 정책에 따라 달라질 수 있어서 현재는 문서와 수동 단계로 분리했다.

---

## 6. OCR/Qwen API와 GPU Qwen 연결

Cloud Run의 OCR/Qwen API는 Qwen provider를 직접 내장하지 않고,  
환경변수로 외부 inference endpoint를 바라보게 하는 것이 현재 구조와 맞다.

예시:

```env
ENABLE_LOCAL_QWEN=0
ALLOW_MODEL_DOWNLOAD=0

QWEN_OPENAI_COMPATIBLE_BASE_URL=http://<GPU_VM_IP>:<PORT>/v1
QWEN_OPENAI_COMPATIBLE_API_KEY=<API_KEY>
QWEN_OPENAI_COMPATIBLE_MODEL=<MODEL_NAME>
QWEN_OPENAI_COMPATIBLE_TIMEOUT_SECONDS=30
```

이 구조의 장점:

- OCR/Qwen Cloud Run은 가볍고 안정적인 기본 API만 담당
- GPU 서버는 실험/교체가 쉬움
- Qwen provider를 바꿔도 API 서버 이미지를 다시 설계할 필요가 적음

---

## 7. 현재 추천 운영 방식

현재 프로젝트 기준 추천은 별도 컨테이너로 분리한다.

- OCR/재료예측은 OCR/Qwen 서비스 유지
- 추천은 별도 추천 서비스에서 처리
- Qwen은 hard-case rescue 전용
- small local Qwen은 운영 메인 경로로 쓰지 않음
- 더 큰 provider가 준비되면 GPU VM에 붙여 실험

즉, GPU는 “전체 서비스 필수 요건”이 아니라  
**hard-case rescue 품질을 올리기 위한 선택 리소스**다.

---

## 8. 현재 환경 제약

이 저장소에 스크립트와 설정은 추가했지만, 아래 조건이 충족돼야 실제 배포를 실행할 수 있다.

- `gcloud auth login`
- `gcloud config set project <PROJECT_ID>`
- 필요한 API 활성화
  - Cloud Build
  - Artifact Registry
  - Cloud Run
  - Compute Engine
- GPU quota 확보

로컬 Docker daemon이 꺼져 있어도 **Cloud Build 원격 빌드**로 진행 가능하다.

---

## 9. 권장 순서

1. Artifact Registry 생성
2. OCR 이미지 원격 빌드
3. 추천 이미지 원격 빌드
4. Cloud Run OCR API 배포
5. Cloud Run 추천 API 배포
6. GPU VM 생성
7. GPU VM에 Qwen 컨테이너 기동
8. Cloud Run OCR API에 `QWEN_OPENAI_COMPATIBLE_*` 연결
9. hard-case 샘플로 rescue 성능 검증
