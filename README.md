# PaddleOCR 영수증 식품명 인식 시스템

PaddleOCR로 영수증 이미지에서 텍스트를 인식하고, Qwen LLM으로 오타 보정 및 상품명을 정리하는 파이프라인입니다.

## 구조

```
├── receipt_ocr.py              # PaddleOCR 기반 OCR + 식품 키워드 매칭
├── qwen_receipt_assistant.py   # Qwen LLM 보조 (오타 보정, 상품명 정리)
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

## 파이프라인

1. **PaddleOCR** - 영수증 이미지 → 텍스트 인식 (한국어, PP-OCRv5)
2. **키워드 매칭** - 759개 식품 사전으로 식품명 1차 추출
3. **Qwen 보정** (선택) - OCR 오타 수정, 상품명 정리, 비식품 제거
