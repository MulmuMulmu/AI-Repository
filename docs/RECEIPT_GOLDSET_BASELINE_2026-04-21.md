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
  - [1652882389756.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/1652882389756.json)
  - [OIP_1.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_1.json)
  - [OIP_7.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_7.json)
  - [OIP_8.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_8.json)
  - [OIP_9.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_9.json)
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
| image_count | 14 |
| total_item_count | 108 |
| review_required_count | 4 |

포함 이미지:

- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
- `1652882389756.jpg`
- `OIP (1).webp`
- `OIP (7).webp`
- `OIP (8).webp`
- `OIP (9).webp`
- `image.png`
- `R (1).jpg`
- `R.jpg`
- `R (2).jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
- `OIP (10).webp`
- `img2.jpg`

## 실행 명령

```bash
python scripts/evaluate_receipt_silver_set.py --manifest data/receipt_gold/jevi-gold-v0/manifest.json
```

## 기준선 결과

Noop Qwen 기준 결과:

| 지표 | 값 |
|---|---:|
| image_count | 14 |
| vendor_name_accuracy | 0.9286 |
| purchased_at_accuracy | 0.8571 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.8294 |
| quantity_match_rate_avg | 0.7690 |
| amount_match_rate_avg | 0.7676 |
| review_required_accuracy | 1.0 |

이미지별:

| file | item_f1 | 메모 |
|---|---:|---|
| `2a4dd3c18f06cec1571dc9ca52dc5946.jpg` | 0.9655 | visual review로 clear item 4개 승격, dense fallback 억제로 duplicate 제거 |
| `1652882389756.jpg` | 0.9474 | grocery partial receipt. vendor는 없고 date는 육안상 보이지만 현재 OCR fallback으로는 미복구, 마지막 `깐양파`는 여전히 누락 |
| `OIP (1).webp` | 0.4000 | convenience mixed receipt. 식품 2개만 gold로 잡았고 현재 parser는 비식품 `애니파워부탄가스`를 item으로 포함해 precision이 크게 깎임 |
| `OIP (7).webp` | 0.8571 | low-res meat/healthfood receipt. item name은 대체로 잡지만 quantity/amount 구조화가 아직 약함 |
| `OIP (8).webp` | 0.0000 | low-res convenience receipt. 현재 parser는 vendor/date hallucination과 품목명 붕괴가 심해 acceptance 기준의 최약군으로 내려옴 |
| `OIP (9).webp` | 0.6316 | grocery acceptance sample. `양념등심돈까스`는 회복됐지만 `파프리카(팩)`과 cropped item miss가 남아 현재 parser 약점을 드러냄 |
| `image.png` | 1.0000 | leading marker 제거 + exact alias 회복으로 식재료/유제품 명칭 정렬 |
| `R (1).jpg` | 0.9286 | `용기면 6입` 2줄 품목 복구 후 대형마트 라면/소스류 케이스 안정화 |
| `R.jpg` | 1.0000 | visual review로 `와이멘씨라이스퍼프`, `부드러운쿠키블루베`를 gold 승격 후 정렬 완료 |
| `R (2).jpg` | 0.9286 | `R (1)`과 동일 계열, `용기면 6입` 복구 반영 |
| `img3.jpg` | 1.0000 | lower item strip fallback으로 `맥주 바이젠 미니` 회복, `(5입)` pack-count 비교 정규화 반영 |
| `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg` | 0.9524 | gift-tail item strip fallback으로 `투썸로얄밀크티` gift 복구 |
| `OIP (10).webp` | 1.0000 | 단일 고가 상품 영수증, 바코드 suffix/결제금액 회복 |
| `img2.jpg` | 1.0000 | `subtotal + tax` fallback과 tax OCR 보강 후 편의점 2품목 케이스 정렬 |

## 해석

- 기존 4장 core baseline보다 더 어려운 hard-case 4장을 넣었지만, 후속 parser 보강으로 평균을 다시 끌어올렸다.
- 이번 기준에는 grocery partial receipt [1652882389756.jpg](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/1652882389756.jpg)도 정식 gold로 편입했다.
  - 서비스는 이제 noisy preamble 뒤 item header가 나오는 grocery partial receipt를 `partial_receipt=true`로 판정한다.
  - 그 결과 이 샘플은 `review_required=false`로 내려오지만, `purchased_at`과 마지막 `깐양파`는 아직 miss로 남는다.
- 이번 기준에는 [OIP (9).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(9).webp)도 grocery acceptance gold로 편입했다.
  - parser가 이미 `양념등심돈까스`, `payment_amount`, `subtotal`, `tax`를 회복한 상태를 반영했다.
  - 반면 `파프리카(팩)`과 마지막 cropped grocery item이 아직 누락되어, baseline이 더 현실적인 acceptance 기준으로 내려왔다.
- 이번 기준에는 [OIP (7).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(7).webp)도 low-res grocery acceptance gold로 편입했다.
  - current parser는 이름은 일부 잡지만 `quantity/amount` 구조화가 약하고 `review_required=true` 상태다.
  - 이 샘플을 넣으면서 quantity/amount rate가 크게 내려가 현재 acceptance 기준의 약점이 더 명확해졌다.
- 이번 기준에는 [OIP (1).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(1).webp)도 convenience mixed acceptance gold로 편입했다.
  - 이 샘플은 식품 2개는 명확하지만, 현재 parser가 비식품 `애니파워부탄가스`를 item으로 포함한다.
  - 그래서 baseline은 더 내려갔고, non-food filtering이 acceptance 기준의 실제 병목이라는 점이 드러났다.
- 이번 기준에는 [OIP (8).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(8).webp)도 low-res convenience acceptance gold로 편입했다.
  - 이 샘플은 current parser가 vendor/date를 hallucinate하고, 품목명도 거의 맞추지 못한다.
  - 그래서 baseline이 크게 내려갔고, low-res convenience receipt 대응이 아직 acceptance 범위를 충분히 만족하지 못한다는 점이 분명해졌다.
- 이번 보강의 핵심:
  - `img3.jpg`: 가짜 vendor 제거 후 `lower item strip fallback`으로 `맥주 바이젠 미니` 회복
  - `SE-...jpg`: exact alias lookup + gift-tail item strip fallback으로 `투썸로얄밀크티` gift까지 회복
  - `OIP (10).webp`: 상품명 뒤 바코드 suffix 제거, `결제대상금` 우선 유지
  - `R (1)/(2).jpg`: `용기면` 식품명 허용 + final-item 기준 `consumed_line_ids` 재계산으로 non-food row를 totals reconciliation에 다시 반영
  - `image.png`: `×`, `* ` marker 제거와 raw alias prior lookup으로 `파프리카`, `완숙토마토 4kg/박스`, `국내산 양상추 2입`, `갈바니 리코타 치즈4` 정렬
  - `2a4dd3...jpg`: dense receipt에서는 `placeholder_barcode` item-strip fallback을 막아 duplicate hallucination 제거, `T` quantity placeholder 복구와 clear item 4개 gold 승격 반영
  - `img2.jpg`: `부 "가 세` 같은 OCR 노이즈 세액 줄도 tax로 인식하고 `subtotal + tax`를 known total 후보로 사용
- 평가 스크립트도 좁게 보정했다.
  - `(5입)`, `(2개)` 같은 parenthetical pack-count 표기는 동일 품목으로 본다.
  - `355ml`, `500ml` 같은 실제 용량 차이는 그대로 다른 품목으로 유지한다.
- 평가 스크립트는 이제 이름 F1 외에 아래도 함께 계산한다.
  - `quantity_match_rate_avg`
  - `amount_match_rate_avg`
  - `review_required_accuracy`
- 현재 실사 gold 14장 기준 review 축도 정렬됐다.
  - `review_required_accuracy = 1.0`
  - `img3.jpg`, `OIP (10).webp`는 focused receipt의 vendor 미확정 허용 정책으로 정리됐다.
  - `R (1)/(2).jpg`는 filtered-out non-food row의 `1,000원`을 reconciliation에 다시 반영하면서 `total_mismatch`가 해소됐다.
  - 현재 최약군은 `OIP (8).webp (0.0000)`이고, 다음은 `OIP (1).webp (0.4000)`이다.
  - 이건 품질 후퇴가 아니라 grocery acceptance set을 넓힌 결과다.

## 다음 우선순위

1. grocery/convenience gold를 16장 이상으로 확장
2. `OIP (9)`처럼 cropped first/last item miss가 반복되는 패턴만 일반화 규칙으로 보강
3. gold 16장 기준 baseline 재측정
4. 그 뒤에도 남는 item-name 붕괴 케이스에만 제한적 crop/Qwen rescue 검토
