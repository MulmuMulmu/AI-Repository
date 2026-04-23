# OCR Implementation Notes

## 목적

- 기준 레포의 데이터/API 구조는 유지한다.
- 현재 공개 OCR API는 `/ai/ocr/analyze` 하나로 둔다.
- 내부 OCR 엔진은 prototype의 `ocr_qwen` 패키지를 그대로 이식해 사용한다.
- Qwen은 기본 비활성 상태의 보조 기능으로 둔다.

## 구현 위치

- `main.py`
  - 현재 공개 흐름 기준 핵심 API는 `/ai/ocr/analyze`, `/ai/ingredient/match`, `/ai/ingredient/prediction`, `/ai/recommend`, `/ai/recipes/{recipe_id}`, `/ai/ingredients/search`
  - prototype `ReceiptParseService`를 adapter 형태로 사용
  - 앱 startup 시 shared PaddleOCR backend warm-up
  - 응답에 `vendor_name`, `purchased_at`, `totals`, `diagnostics` 추가
  - OCR 응답에서는 `food_items[].product_name`을 `normalized_name` 우선으로 노출

- `ocr_qwen/`
  - prototype OCR 런타임 패키지
  - `preprocess.py`: 이미지 전처리
  - `services.py`: PaddleOCR backend, parse service, Qwen item refinement
  - `receipts.py`: row parser, section/totals/item assembly
  - `qwen.py`: Noop/local Qwen provider 중심
  - `ingredient_dictionary.py`: generated ingredient alias lookup

- `receipt_ocr.py`
  - 기존 공개 클래스 `ReceiptOCR` 유지
  - 내부 구현은 `ocr_qwen.services.ReceiptParseService`로 위임
  - CLI 실행과 시각화 함수 유지
  - 디버그/품질검증 용도라서 `food_items[].product_name`은 `raw_name` 우선으로 노출

- `qwen_receipt_assistant.py`
  - 현재는 호환용 보조 유틸리티
  - `ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1`일 때만 동기 Qwen 보조 실행
  - Qwen 실패 시 예외를 던지지 않고 fallback 유지

## 현재 응답 계약

`POST /ai/ocr/analyze`

- 유지 필드
  - `ocr_texts`
  - `food_items`
  - `food_count`
  - `model`

- 추가 필드
  - `vendor_name`
  - `purchased_at`
  - `totals`
  - `diagnostics`

`food_items`는 최종적으로 아래 형태로 정규화된다.

```json
{
  "product_name": "라라스윗 바닐라 파인트",
  "amount_krw": 6900,
  "notes": ""
}
```

주의:
- `/ai/ocr/analyze`는 정규화된 품목명을 우선 노출한다.
- `receipt_ocr.py`의 `ReceiptOCR.analyze_receipt()`는 OCR 품질 검증용이라 원문 품목명을 우선 노출한다.

## 운영 기본값

- OCR: 활성
- Qwen: 비활성
- Warm-up: 활성
- 목적: prototype 수준의 파싱 품질 유지 + 첫 요청 이후 응답 속도 안정화

현재 CPU 기준 샘플 성능:
- warm-up: 약 11.1초
- warm parse: 이미지 1장당 약 2.3~4.2초

## Qwen 활성화 환경변수

```env
ENABLE_LOCAL_QWEN=1
LOCAL_QWEN_MODEL_ID=Qwen/Qwen2.5-1.5B-Instruct
ALLOW_MODEL_DOWNLOAD=1
ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT=1
QWEN_MODEL=qwen2.5:latest
QWEN_TIMEOUT_SECONDS=8
QWEN_RECEIPT_MAX_TOKENS=256
```

## 현재 한계

- 저해상도 실사 영수증에서는 OCR 원문 오독이 남을 수 있다.
- prototype parser를 이식했지만, 실사 골든셋 없이 완전한 일반화는 아직 보장되지 않는다.
- 로컬 CPU Qwen을 동기 호출하면 응답 시간이 급격히 느려질 수 있어서 기본 비활성으로 둔다.

## 최소 검증 테스트

이식 작업의 회귀 방지는 아래 3개 테스트를 기준으로 한다.

- `tests/test_ocr_api_contract.py`
  - `/ai/ocr/analyze` 응답 계약
  - `ocr_texts`, `food_items`, `food_count`, `model` 유지
  - `vendor_name`, `purchased_at`, `totals`, `diagnostics` 포함 여부 확인

- `tests/test_public_api_surface.py`
  - `/ai/ingredient/match`, `/ai/ingredient/prediction` 응답 계약
  - 기존 `/api/...` 라우트 비노출 확인

- `tests/test_ocr_service_adapter.py`
  - `ReceiptOCR` 결과를 legacy contract로 어댑트하는지 확인
  - `QwenReceiptAssistant` fallback이 JSON shape를 유지하는지 확인

- `tests/test_receipt_quality_rules.py`
  - 영수증 품목 조립/노이즈 제거 회귀 확인
  - 최근 추가한 single-line, gift, barcode-detail 패턴 회귀 방지

권장 실행:

```powershell
pytest tests/test_ocr_api_contract.py tests/test_public_api_surface.py tests/test_ocr_service_adapter.py -q
```
