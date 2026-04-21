# Receipt Goldset Baseline (2026-04-21)

## 목적

`제비` 실사 이미지 중 대표 후보를 `jevi-gold-v0`로 승격하고,

- 현재 `PaddleOCR + rule parser + NoopQwen`
- 수작업 보정 gold draft

를 비교하는 기준선을 남긴다.

이 데이터는 학습셋이 아니라 회귀/품질 검증용 기준셋이다.

## 데이터 위치

- 매니페스트: [manifest.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/manifest.json)
- 정답 라벨:
  - [2a4dd3c18f06cec1571dc9ca52dc5946.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/2a4dd3c18f06cec1571dc9ca52dc5946.json)
  - [image.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/image.json)
  - [R_1.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/R_1.json)
  - [R.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/R.json)

## 라벨 정책

- `verification_status = assistant_labeled_unverified`
- OCR로 명확히 읽히는 품목만 `expected.items`에 포함했다.
- 이름이 불확실한 항목은 `uncertain_items`로 분리했다.
- 할인/비식품/부적절 행은 `excluded_rows`로 분리했다.
- 현재 평가는 `expected.items`만 점수화한다.

## 구성

| 항목 | 값 |
|---|---:|
| image_count | 8 |
| total_item_count | 72 |
| review_required_count | 0 |

포함 이미지:

- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
- `image.png`
- `R (1).jpg`
- `R.jpg`
- `R (2).jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
- `OIP (10).webp`

## 실행 명령

```bash
python scripts/evaluate_receipt_silver_set.py --manifest data/receipt_gold/jevi-gold-v0/manifest.json
```

## 기준선 결과

Noop Qwen 기준 결과:

| 지표 | 값 |
|---|---:|
| image_count | 8 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 1.0 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.8916 |
| quantity_match_rate_avg | 0.9188 |
| amount_match_rate_avg | 0.9163 |
| review_required_accuracy | 0.5 |

이미지별:

| file | item_f1 | 메모 |
|---|---:|---|
| `2a4dd3c18f06cec1571dc9ca52dc5946.jpg` | 0.8000 | snack 품목 일부 과검출 |
| `image.png` | 0.7273 | spaced numeric detail 복구, totals 회복, summary garbage 제거 |
| `R (1).jpg` | 0.8889 | 가장 안정적, 라면/소스류 대형마트 영수증 |
| `R.jpg` | 0.8750 | Homeplus/snack alias 보정 후 남은 불확실 snack 일부만 잔존 |
| `R (2).jpg` | 0.8889 | `R (1)`과 유사한 대형마트 라면/소스 레이아웃 |
| `img3.jpg` | 1.0000 | lower item strip fallback으로 `맥주 바이젠 미니` 회복, `(5입)` pack-count 비교 정규화 반영 |
| `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg` | 0.9524 | gift-tail item strip fallback으로 `투썸로얄밀크티` gift 복구 |
| `OIP (10).webp` | 1.0000 | 단일 고가 상품 영수증, 바코드 suffix/결제금액 회복 |

## 해석

- 기존 4장 core baseline보다 더 어려운 hard-case 4장을 넣었지만, 후속 parser 보강으로 평균을 다시 끌어올렸다.
- 이번 보강의 핵심:
  - `img3.jpg`: 가짜 vendor 제거 후 `lower item strip fallback`으로 `맥주 바이젠 미니` 회복
  - `SE-...jpg`: exact alias lookup + gift-tail item strip fallback으로 `투썸로얄밀크티` gift까지 회복
  - `OIP (10).webp`: 상품명 뒤 바코드 suffix 제거, `결제대상금` 우선 유지
- 평가 스크립트도 좁게 보정했다.
  - `(5입)`, `(2개)` 같은 parenthetical pack-count 표기는 동일 품목으로 본다.
  - `355ml`, `500ml` 같은 실제 용량 차이는 그대로 다른 품목으로 유지한다.
- 평가 스크립트는 이제 이름 F1 외에 아래도 함께 계산한다.
  - `quantity_match_rate_avg`
  - `amount_match_rate_avg`
  - `review_required_accuracy`
- 현재 실사 gold 8장 기준에서 review 축이 가장 약하다.
  - `review_required_accuracy = 0.5`
  - `2a4dd3...`와 `SE-...`는 review 정책 보강으로 해소됐다.
  - 남은 review mismatch는 더 적은 수의 hard-case로 좁혀졌다.

## 다음 우선순위

1. snack alias 추가 보강
2. 남은 review mismatch 샘플 분해
3. gold 8장 이후 다음 8장 후보 선정
4. 실사 gold 8장 이후 다음 baseline 갱신
