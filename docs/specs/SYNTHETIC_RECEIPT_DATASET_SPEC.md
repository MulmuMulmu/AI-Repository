# Synthetic Receipt Dataset Specification

## 목적

이 문서는 합성 영수증 데이터셋을 어떤 구조와 기준으로 생성하고 검증할지 정의한다.

핵심 원칙:

- 합성셋은 실사셋의 대체재가 아니라 구조 회귀 테스트용이다.
- 합성셋은 파서 패턴, 노이즈 내성, 품목/날짜/합계 추출 안정화를 위한 수단이다.
- 실사셋은 최종 품질 판단용으로 별도 유지한다.

## 합성셋의 역할

합성 영수증은 아래 목적에 사용한다.

- 품목 조립 규칙 회귀 테스트
- 날짜 추출 회귀 테스트
- 합계/세액/결제금액 파싱 회귀 테스트
- false positive 제거 규칙 검증
- 약한 blur / contrast / skew / crop 내성 확인

합성셋만으로 판단하지 않는 것:

- 실제 상업적 정확도 최종 수치
- 감열지 번짐/반사/구김이 심한 실사 대응력

## 데이터셋 구성 단위

각 합성 샘플은 아래 3개를 한 세트로 가진다.

1. 이미지 파일
2. 정답 JSON
3. 메타데이터 JSON

## 정답 JSON 스키마

```json
{
  "vendor_name": "GS25",
  "purchased_at": "2023-11-24",
  "items": [
    {
      "raw_name": "허쉬쿠키앤크림",
      "normalized_name": "허쉬쿠키앤크림",
      "quantity": 1.0,
      "unit": "개",
      "amount": 1600.0
    }
  ],
  "totals": {
    "subtotal": 18726.0,
    "tax": 1874.0,
    "total": 24090.0,
    "payment_amount": 24090.0
  }
}
```

최소 필수 필드:

- `vendor_name`
- `purchased_at`
- `items`

가능하면 포함:

- `totals.total`
- `totals.payment_amount`

## 메타데이터 스키마

```json
{
  "layout_type": "convenience_pos",
  "noise_profile": {
    "blur": "low",
    "contrast": "normal",
    "skew": "small",
    "crop": "none",
    "shadow": "none"
  },
  "source_type": "synthetic",
  "version": "v1"
}
```

## 레이아웃 카테고리

최소 아래 유형을 분리해서 생성한다.

### 1. Convenience POS

- 편의점형
- 품목명 / 수량 / 금액
- 증정품 / 행사 텍스트 포함 가능

### 2. Mart Column

- 마트형
- 상품명 / 단가 / 수량 / 금액 컬럼
- 세액/과세/면세 라인 포함 가능

### 3. Barcode Detail

- 상품명 줄 다음에 숫자/바코드 상세 줄이 나오는 구조

### 4. Compact Single-Line

- 한 줄에 상품명, 수량, 금액이 같이 들어가는 구조

### 5. Mixed Noise

- 쿠폰 / 봉투 / 보증금 / 행사 / 적립 / 전표 문구가 섞인 구조

## 노이즈 프로파일

합성 노이즈는 "실사용에서 흔한 범위"까지만 넣는다.

### 지원 노이즈

- `blur`: none / low / medium
- `contrast`: normal / low
- `skew`: none / small / medium
- `crop`: none / top_small / bottom_small
- `shadow`: none / low

### 비권장 노이즈

아래는 합성셋 기본 범위에서 제외한다.

- 극단적 모션 블러
- 텍스트 식별 불가 수준의 저해상도
- 영수증 절반 이상 잘림
- 강한 난반사

이유:

- 이런 샘플은 합성셋보다는 재촬영 가이드와 실사 실패셋 관리 문제에 가깝다.

## 권장 수량

### Step 1. 구조 안정화

- 총 100장
- 레이아웃당 20장 수준

### Step 2. 레이아웃 측정

- 총 300~500장
- 레이아웃별/노이즈별 분포 확인

### Step 3. 일반화 검증

- 총 500~1000장
- 조합 다양화

## 평가 항목

합성셋에서 최소 측정 항목:

- 날짜 exact match
- 품목 precision / recall / F1
- 수량 precision / recall / F1
- totals consistency accuracy
- `review_required` rate

## 저장 위치 제안

- 이미지
  - `data/receipt_synthetic/images/`
- 정답 JSON
  - `data/receipt_synthetic/annotations/`
- 메타데이터/manifest
  - `data/receipt_synthetic/manifest.json`

## 현재 구현 경로

현재 저장소에는 템플릿 기반 합성 생성 스크립트가 추가되어 있다.

- 생성 스크립트
  - `scripts/build_synthetic_receipts.py`
- 생성 모듈
  - `ocr_qwen/synthetic_receipts.py`

예시 실행:

```powershell
python scripts/build_synthetic_receipts.py --output-dir data/receipt_synthetic/receipt-synthetic-v1
```

현재 기본 생성 수량:

- `300장`
- 분포
  - `convenience_pos`: 90
  - `mart_column`: 90
  - `barcode_detail`: 60
  - `compact_single_line`: 30
  - `mixed_noise`: 30

## 운영 규칙

- 새 파싱 규칙 추가 시 합성 회귀셋부터 통과해야 한다.
- 합성셋 통과만으로 품질 개선 주장하지 않는다.
- 실사셋과 합성셋의 지표는 분리해서 기록한다.

## 연계 문서

- [../guides/NORMAL_INPUT_CRITERIA.md](../guides/NORMAL_INPUT_CRITERIA.md)
- [../guides/RECAPTURE_GUIDELINES.md](../guides/RECAPTURE_GUIDELINES.md)
- [../status/OCR_PIPELINE_STATUS_2026-04-18.md](../status/OCR_PIPELINE_STATUS_2026-04-18.md)
