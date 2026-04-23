# OCR Quality Baseline

기준 레포:
- `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`

기준 샘플:
- `img2.jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

추가 평가셋:
- `data/receipt_silver/jevi-silver-v0`
- 설명 문서: `docs/datasets/RECEIPT_SILVERSET.md`

## 최근 검증 결과

### direct OCR

`img2.jpg`
- 날짜 추출: 성공 (`2020-06-09`)
- 품목 수: 2
- review flag: `unresolved_items`
- 상태: 품목 2개는 안정적으로 복원
- 대표 출력:
  - `라라스윗)바널라파인트474 행상` / `6,900`
  - `라라스윗)초코파인트474m1` / `6,900`
- 남은 문제:
  - OCR 오독이 그대로 품목명에 남음
  - alias 정규화가 아직 약함

`img3.jpg`
- 날짜 추출: 성공 (`2015-01-20`)
- 품목 수: 3
- review flag: `unresolved_items`
- 상태: 바코드형/상세숫자형 혼합 케이스는 일부 복원
- 개선 포인트:
  - `상품명 + 다음 숫자 줄` 패턴 인식 유지
  - `바코드 + 단가 + OCR 깨진 수량 + 금액` 패턴에서 수량 1 추론 유지
  - full image에서도 날짜 복원
- 남은 문제:
  - `속이면한 누룸지`가 중복 추출
  - 이름 정규화 미흡

`1652882389756.jpg`
- 날짜 추출: 실패
- 품목 수: 10
- review flag: `missing_purchased_at`, `unresolved_items`
- 상태: 정육/채소 상세행 복원이 개선됨
- 개선 포인트:
  - `code + unit_price + - + amount` 형태에서 수량 1 추론
  - `—` 같은 유니코드 대시도 상세행으로 인식
  - `*적상추`가 단일행 fallback이 아니라 2줄 상세행으로 복원
  - `Ra` 같은 짧은 OCR 조각을 vendor로 채택하지 않도록 보수화
  - 서비스 레벨에서 `top-strip date fallback` 추가
  - 품목명 OCR 오독 정리
    - `큰사각했반300g` -> `큰사각햇반300g`
    - `코카)코카콜라350m]350m1` -> `코카콜라350ml`
    - `^진로)(뉴트로)소주(병)360m]` -> `진로 소주 360ml`
- 남은 문제:
  - 상단 crop + sharpen/upscale fallback을 넣어도 날짜 문자열이 OCR 결과에 들어오지 않음
  - 즉 `purchased_at` 누락 원인은 parser가 아니라 OCR 단계의 blind spot임
  - 품목명 raw text 오독이 남음 (`큰사각했반300g`, `코카)코카콜라350m]350m1`)

### date fallback

- 서비스는 이제 본문 OCR에서 `purchased_at`이 비면 상단 strip을 따로 crop해서 한 번 더 OCR한다.
- 진단 필드:
  - `diagnostics.date_fallback_used`
  - `diagnostics.date_fallback_source`
- 현재 확인 결과:
  - `1652882389756.jpg`는 fallback을 써도 날짜가 복구되지 않는다.
  - 따라서 이 케이스는 추가 규칙보다 더 강한 전처리 또는 다른 OCR/VLM 경로가 필요하다.

### Qwen header rescue

- 서비스는 이제 `vendor_name` 또는 `purchased_at`이 비면 Qwen `extract_receipt` 경로로 header rescue를 시도한다.
- 이 경로는 품목/금액을 다시 해석하지 않는다.
  - 목적은 `vendor_name`, `purchased_at`만 보정하는 것이다.
- 진단 필드:
  - `diagnostics.qwen_header_attempted`
  - `diagnostics.qwen_header_used`
  - `diagnostics.qwen_header_fallback_reason`
- 현재 실사 `1652882389756.jpg` 결과:
  - local Qwen provider 연결은 완료됐다.
  - 다만 CPU 동기 추론은 너무 느려서 기본값은 비활성이다.
  - 진단값은 `qwen_header_fallback_reason=disabled_sync_local_qwen_header`로 남는다.
  - 즉, 코드 경로는 준비됐고 실제 운영 사용은 `ENABLE_SYNC_LOCAL_QWEN_HEADER_RESCUE=1`로 명시적으로 켜야 한다.

`SE-...jpg`
- 날짜 추출: 성공 (`2023-11-25`)
- 품목 수: 9
- review flag: `total_mismatch`, `unresolved_items`
- 상태: full image 기준으로 품목 블록은 다시 안정적으로 잡힘
- 개선 포인트:
  - `상품명 1 1,600` 형태를 `상품명 + 수량 + 금액`으로 분리
  - `상품명 1 증정품` 형태를 gift row로 분리
  - notice/payment 블록이 item section에 섞이던 문제를 줄임
- 남은 문제:
  - 일부 품목 오독(`투썸딸기피지`, `어쉬밀크클릿 [`, `초코빼빼로지암 L`, `이에`) 정규화 부족
  - 총액 검증 mismatch 남음

### API speed

`ReceiptOCR` warm path 기준

- warm-up: 약 11.1초
- `img2.jpg`: 약 4.17초
- `img3.jpg`: 약 2.37초
- `SE-...jpg`: 약 3.72초
- 해석:
  - CPU + PP-OCRv5 기준으로 Qwen 없이도 2~4초대 응답은 가능
  - 현재 병목은 OCR 자체와 full-image 파싱이며, Qwen을 동기 경로에 상시 붙이면 사용자 체감이 급격히 나빠질 가능성이 높음

### silver set self-check

`jevi-silver-v0` 11장으로 자기 비교 평가를 돌렸을 때:

- vendor_name_accuracy: `1.0`
- purchased_at_accuracy: `1.0`
- payment_amount_accuracy: `1.0`
- item_name_f1_avg: `1.0`

해석:
- silver set를 현재 파서 결과로 다시 생성한 뒤 순차 평가를 돌렸기 때문에 self-check가 전부 `1.0`으로 맞는다.
- 이 값은 "현재 baseline과 현재 엔진이 일치한다"는 뜻이지, 절대 품질이 1.0이라는 뜻은 아니다.
- 따라서 앞으로는 이 refreshed silver set를 회귀 기준으로 쓰고, 절대 품질 판단은 실사 샘플 직접 점검과 golden set로 분리해야 한다.
- 따라서 silver set는 회귀 감지용으로 유효하다.

## 실패 유형 분류

### 1. 구조 노이즈

- 쿠폰
- 매출/상품 코드
- 봉투/보증금
- 세금/합계 줄

### 2. 금액 오인식

- `(5입)`의 `5`를 가격으로 해석
- `1` 같은 수량 숫자를 가격으로 해석
- `4.800` 형식을 `4800`으로 정규화하지 못하는 경우

### 3. 품목 줄 조립 실패

- `상품명` 다음 줄에 `가격 수량 금액`
- `상품명` 다음 줄에 `바코드 수량 금액`
- 할인/행사 줄이 중간에 끼는 경우

### 4. alias / 정규화 부족

- OCR이 읽은 raw 품목명이 실제 상품명과 조금씩 다른 경우
- 상품명은 읽었지만 표준 재료명 또는 카테고리로 정규화되지 않는 경우

## 다음 우선순위

1. 날짜 OCR 약한 케이스용 후보 확장 또는 crop 보강
2. OCR alias/정규화 사전 확장
3. 총액 mismatch를 줄이는 item merge / exclusion 규칙 추가
4. low-confidence item만 Qwen 보조 정규화 연결
