# Receipt Goldset Baseline (2026-04-16)

## 목적

`C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비` 실사 영수증 중 대표 4장을 기준으로,

- 내가 직접 읽은 임시 정답(`assistant-visual-v0`)
- 현재 `PaddleOCR + rule parser + NoopQwen`

를 비교하는 기준선을 남긴다.

이 데이터는 학습셋이 아니라 회귀/품질 검증용 기준셋이다.

## 데이터 위치

- 매니페스트: [manifest.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/assistant-visual-v0/manifest.json)
- 정답 라벨:
  - [1652882389756.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/assistant-visual-v0/annotations/1652882389756.json)
  - [img2.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/assistant-visual-v0/annotations/img2.json)
  - [img3.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/assistant-visual-v0/annotations/img3.json)
  - [SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/assistant-visual-v0/annotations/SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.json)

## 라벨 정책

- `verification_status = assistant_labeled_unverified`
- 사람이 육안으로 읽기 애매한 항목은 `uncertain_items` 로 분리했다.
- 현재 F1 비교는 `expected.items` 만 점수화한다.
- `excluded_rows` 는 봉투/보증금/할인 같은 비식품 행이다.

## 오늘 반영한 엔진 고도화

### 파서 개선

- GS25 헤더에서 `재미있는 일상 플랫폼 GS25` 를 `GS25` 로 정규화
- `www7 eleven` 형태의 헤더 흔적도 vendor 후보로 복구 가능하게 정리
- 카드 안내문 `카드결제는 30일(12월24일)이내` 를 결제금액 `24` 로 오인식하던 문제 제거
- `23/ 11/24` 같이 구분자 주변에 공백이 섞인 날짜도 인식
- `신용카드 전표` 의 승인일보다 상단 판매일을 우선 선택
- `구매금액 49,060` 을 결제 총액으로 인식
- `바널라 -> 바닐라`, `속이면한 -> 속이편한`, `누룸지 -> 누룽지`, `코볼 -> 초코볼`, `ML -> ml` 정규화 추가
- `행상` 같은 행사 OCR 오염 꼬리 제거

### 평가 개선

- `raw_name` 과 `normalized_name` 이 동시에 있는 경우 이중 패널티가 생기지 않도록 비교 로직 수정
- 같은 품목이 두 번 이상 나온 경우(set 기반 붕괴)도 개수 기준으로 비교되게 수정

## 현재 기준선

실행 명령:

```bash
python scripts/evaluate_receipt_silver_set.py --manifest data/receipt_gold/assistant-visual-v0/manifest.json
```

Noop Qwen 기준 결과:

| 지표 | 값 |
|---|---:|
| image_count | 4 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 0.75 |
| payment_amount_accuracy | 0.75 |
| item_name_f1_avg | 0.8329 |

## 이미지별 해석

### 1652882389756.jpg

- 현재 강점:
  - 주요 품목 10개 중 9개 수준으로 근접
  - `구매금액` 누락은 보완됨
- 현재 약점:
  - 상단 날짜 `2022-04-30` 미추출
  - `*종량10L` 봉투가 품목으로 남음
  - 마지막 품목 `*깐양파` 를 놓침
- 판단:
  - 이 케이스는 `상단 crop 재-OCR` 과 `orphan detail row 보정` 이 필요하다.

### img2.jpg

- 현재 강점:
  - 날짜는 안정적으로 추출
  - `7-ELEVEN` vendor 복구 성공
  - 품목 2개 구조와 이름은 기준셋과 일치
- 현재 약점:
  - 합계/결제금액 미추출
- 판단:
  - 이 케이스는 `결제 총액 회복` 만 남았다.

### img3.jpg

- 현재 강점:
  - 날짜 추출 성공
  - 저화질에서도 2개 메인 품목은 정규화까지 반영됨
- 현재 약점:
  - 불확실 항목은 rule parser 만으로 회복이 어렵다
- 판단:
  - 이 케이스는 규칙만으로는 한계가 크고, `item-line crop + Qwen 구조화` 대상이다.

### SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg

- 현재 강점:
  - 매장명, 판매일, 총액, 결제금액은 복구됨
  - 일부 품목 오타는 rule cleanup 으로 정리됨
- 현재 약점:
  - 품목명 오타가 많음
  - 증정품/일반품 혼합 구간에서 일부 품목이 잘못 묶임
  - `호레오화이트`, `투썸로얄밀크티` 같은 항목을 놓침
- 판단:
  - 이 케이스는 `품목 구간 crop` 과 `Qwen item normalization` 이 필요하다.

## 다음 우선순위

1. `1652882389756.jpg` 상단 헤더 crop 재-OCR 강화
2. `img2.jpg` vendor rescue 및 총액 회복
3. `img3.jpg`, `SE...jpg` 에 대해 `item-only crop -> Qwen 구조화 -> validator` 경로 연결
4. 실사 4장 기준선이 안정화되면 `제비` 폴더 전체로 확장

## 해석 원칙

- 현재 점수는 `상업적 사용 가능` 판정이 아니라 `고도화 방향성 확인용 기준선` 이다.
- 이 기준선에서 바로 보이는 사실은 명확하다.
  - 헤더 메타데이터는 규칙으로 계속 개선 가능하다.
  - 저화질 품목명 복원은 Qwen 보조 없이는 한계가 있다.
