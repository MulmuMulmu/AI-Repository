# PaddleOCR 영수증 식품명 인식 시스템

PaddleOCR로 영수증 이미지에서 텍스트를 인식하고, Qwen LLM으로 오타 보정 및 상품명을 정리하는 파이프라인입니다.
FastAPI 서버(`main.py`)는 이 결과를 `/api/ocr/receipt`로 노출합니다.

## 구조

```
├── receipt_ocr.py              # PaddleOCR 기반 OCR + 식품 키워드 매칭
├── qwen_receipt_assistant.py   # Qwen LLM 보조 (오타 보정, 상품명 정리)
├── main.py                     # FastAPI API 서버
├── requirements.txt            # Python 의존성
├── data/
│   ├── receipt_images/         # 영수증 이미지
│   └── labels/                 # 라벨링 데이터
└── models/                     # 학습된 모델 저장
```

## 설치

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 실행

```bash
# PaddleOCR만 (기본)
python receipt_ocr.py <영수증_이미지>

# PaddleOCR + Qwen 보정
python receipt_ocr.py <영수증_이미지> --qwen

# 결과 시각화
python receipt_ocr.py <영수증_이미지> --visualize

# FastAPI 서버
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

## 환경변수 (.env)

Qwen 보정 사용 시 아래 설정이 필요합니다.

```env
# Ollama 로컬
QWEN_BASE_URL=http://localhost:11434/v1
QWEN_API_KEY=ollama
QWEN_MODEL=qwen3:latest
```

Ollama가 로컬에서 실행 중이면 `.env` 없이도 자동 감지됩니다.

`use_qwen=true`는 **best-effort** 옵션입니다. 로컬 OpenAI-compatible Qwen 환경이 없거나 비활성화된 경우, API는 OCR-only 결과로 정상 응답합니다.

`use_qwen=false`면 Qwen 호출을 시도하지 않고 OCR-only 결과만 반환합니다.

## 파이프라인

1. **PaddleOCR** - 영수증 이미지 → 텍스트 인식 (한국어, PP-OCRv5)
2. **키워드 매칭** - 759개 식품 사전으로 식품명 1차 추출
3. **Qwen 보정** (선택) - OCR 오타 수정, 상품명 정리, 비식품 제거

## API 응답 계약

`POST /api/ocr/receipt`는 아래 필드를 유지합니다.

- `ocr_texts`
- `food_items`
- `food_count`
- `model`

`food_items`는 최종 정리된 상품 목록이며, Qwen이 비활성화되면 OCR-only 기반 결과가 반환됩니다.
