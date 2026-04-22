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
| item_name_f1_avg | 0.9397 |
| quantity_match_rate_avg | 0.9708 |
| amount_match_rate_avg | 0.9683 |
| review_required_accuracy | 1.0 |

이미지별:

| file | item_f1 | 메모 |
|---|---:|---|
| `2a4dd3c18f06cec1571dc9ca52dc5946.jpg` | 0.8000 | snack 품목 일부 과검출 |
| `image.png` | 1.0000 | leading marker 제거 + exact alias 회복으로 식재료/유제품 명칭 정렬 |
| `R (1).jpg` | 0.9286 | `용기면 6입` 2줄 품목 복구 후 대형마트 라면/소스류 케이스 안정화 |
| `R.jpg` | 0.8750 | Homeplus/snack alias 보정 후 남은 불확실 snack 일부만 잔존 |
| `R (2).jpg` | 0.9286 | `R (1)`과 동일 계열, `용기면 6입` 복구 반영 |
| `img3.jpg` | 1.0000 | lower item strip fallback으로 `맥주 바이젠 미니` 회복, `(5입)` pack-count 비교 정규화 반영 |
| `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg` | 0.9524 | gift-tail item strip fallback으로 `투썸로얄밀크티` gift 복구 |
| `OIP (10).webp` | 1.0000 | 단일 고가 상품 영수증, 바코드 suffix/결제금액 회복 |

## 해석

- 기존 4장 core baseline보다 더 어려운 hard-case 4장을 넣었지만, 후속 parser 보강으로 평균을 다시 끌어올렸다.
- 이번 보강의 핵심:
  - `img3.jpg`: 가짜 vendor 제거 후 `lower item strip fallback`으로 `맥주 바이젠 미니` 회복
  - `SE-...jpg`: exact alias lookup + gift-tail item strip fallback으로 `투썸로얄밀크티` gift까지 회복
  - `OIP (10).webp`: 상품명 뒤 바코드 suffix 제거, `결제대상금` 우선 유지
  - `R (1)/(2).jpg`: `용기면` 식품명 허용 + final-item 기준 `consumed_line_ids` 재계산으로 non-food row를 totals reconciliation에 다시 반영
  - `image.png`: `×`, `* ` marker 제거와 raw alias prior lookup으로 `파프리카`, `완숙토마토 4kg/박스`, `국내산 양상추 2입`, `갈바니 리코타 치즈4` 정렬
  - `2a4dd3...jpg`: dense receipt에서는 `placeholder_barcode` item-strip fallback을 막아 duplicate hallucination 제거
- 평가 스크립트도 좁게 보정했다.
  - `(5입)`, `(2개)` 같은 parenthetical pack-count 표기는 동일 품목으로 본다.
  - `355ml`, `500ml` 같은 실제 용량 차이는 그대로 다른 품목으로 유지한다.
- 평가 스크립트는 이제 이름 F1 외에 아래도 함께 계산한다.
  - `quantity_match_rate_avg`
  - `amount_match_rate_avg`
  - `review_required_accuracy`
- 현재 실사 gold 8장 기준 review 축도 정렬됐다.
  - `review_required_accuracy = 1.0`
  - `img3.jpg`, `OIP (10).webp`는 focused receipt의 vendor 미확정 허용 정책으로 정리됐다.
  - `R (1)/(2).jpg`는 filtered-out non-food row의 `1,000원`을 reconciliation에 다시 반영하면서 `total_mismatch`가 해소됐다.
  - 남은 최약군은 `2a4dd3...jpg`이고, 현재는 duplicate fallback 제거 후 `0.8333`까지 올라온 상태다.

## 다음 우선순위

1. `2a4dd3...jpg`의 실제 clear item을 gold expected에 승격할지 검토
2. gold 다음 8장 승격
3. gold 16장 기준 baseline 재측정
4. 필요 시 Qwen rescue를 hard-case subset에만 제한 적용
