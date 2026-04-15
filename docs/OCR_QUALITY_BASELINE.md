# OCR Quality Baseline

기준 레포:
- `C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh`

기준 샘플:
- `img2.jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`

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
- 품목 수: 4
- review flag: `unresolved_items`
- 상태: 바코드형/상세숫자형 혼합 케이스는 일부 복원
- 개선 포인트:
  - `상품명 + 다음 숫자 줄` 패턴 인식 유지
  - `바코드 + 단가 + OCR 깨진 수량 + 금액` 패턴에서 수량 1 추론 유지
  - full image에서도 날짜 복원
- 남은 문제:
  - `속이면한 누룸지`가 중복 추출
  - `[(야] 7 -11,760` 같은 false positive 1건 남음
  - 이름 정규화 미흡

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

1. OCR alias/정규화 사전 확장
2. 숫자 위주 false positive row 제거 규칙 강화
3. 총액 mismatch를 줄이는 item merge / exclusion 규칙 추가
4. low-confidence item만 Qwen 보조 정규화 연결
