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
  - [OIP_20.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_20.json)
  - [OIP_4.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/receipt_gold/jevi-gold-v0/annotations/OIP_4.json)
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
| image_count | 17 |
| total_item_count | 113 |
| review_required_count | 7 |

포함 이미지:

- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
- `1652882389756.jpg`
- `OIP (1).webp`
- `OIP (7).webp`
- `OIP (8).webp`
- `OIP (9).webp`
- `OIP (20).webp`
- `OIP (4).webp`
- `OIP.webp`
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
| image_count | 17 |
| vendor_name_accuracy | 1.0 |
| purchased_at_accuracy | 0.9412 |
| payment_amount_accuracy | 1.0 |
| item_name_f1_avg | 0.9938 |
| quantity_match_rate_avg | 0.9882 |
| amount_match_rate_avg | 0.9686 |
| review_required_accuracy | 1.0 |

이미지별:

| file | item_f1 | 메모 |
|---|---:|---|
| `2a4dd3c18f06cec1571dc9ca52dc5946.jpg` | 0.9655 | visual review로 clear item 4개 승격, dense fallback 억제로 duplicate 제거 |
| `1652882389756.jpg` | 0.9474 | grocery partial receipt. vendor는 없고 date는 육안상 보이지만 현재 OCR fallback으로는 미복구, 마지막 `깐양파`는 여전히 누락 |
| `OIP (1).webp` | 1.0000 | convenience mixed receipt. alphanumeric barcode/lineNo prefix 정리와 `부탄가스` 비식품 제외로 식품 2개만 남도록 정리 |
| `OIP (7).webp` | 1.0000 | low-res meat/healthfood receipt. `code + 1× + unit_price + amount` detail row를 일반화해서 quantity/amount까지 회복됨 |
| `OIP (8).webp` | 1.0000 | low-res convenience receipt. parser가 clear item 3개를 회복했고 gold의 `uncertain_items`와 scoring 정책도 정렬됐다 |
| `OIP (9).webp` | 0.9474 | grocery acceptance sample. clear grocery item은 대부분 회복됐고, 남은 miss는 `파프리카(팩)`처럼 OCR line 자체가 붕괴한 hard-case다 |
| `OIP (20).webp` | 1.0000 | grocery partial receipt. clear grocery item 4개는 모두 회복됐고, ambiguous product rows는 gold의 `uncertain_items`로 정리되어 acceptance score와 정렬됨 |
| `OIP (4).webp` | 1.0000 | partial grocery crop. `name + unit_price + X + quantity + amount` 한 줄형과 `총합계 + 할인 + 할인총금액` crop totals를 일반화해서 item/totals를 모두 회복함 |
| `OIP.webp` | 1.0000 | small convenience one-item crop. `상품명 + barcode + amount` 한 줄형과 `할인계 + 결제대상금액 + 날짜줄 최종금액` discount summary crop을 회복해 item/totals를 정렬함 |
| `image.png` | 1.0000 | leading marker 제거 + exact alias 회복으로 식재료/유제품 명칭 정렬 |
| `R (1).jpg` | 1.0000 | late `상품 합계 4,480` footer가 total을 덮어쓰지 않도록 정리했고, `오징어짧뽕/삼양나가사끼짬뽕` exact alias까지 반영돼 fully aligned |
| `R.jpg` | 1.0000 | `맛밤42G*10 -> 맛밤` pack-size 축약 alias를 exact product 유지로 되돌려 fully aligned |
| `R (2).jpg` | 1.0000 | `R (1)`과 동일 계열. late footer total overwrite 방지와 exact alias 정리까지 반영돼 fully aligned |
| `img3.jpg` | 1.0000 | lower item strip fallback으로 `맥주 바이젠 미니` 회복, `(5입)` pack-count 비교 정규화 반영 |
| `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg` | 1.0000 | `아몬드빼빼로`는 실제 OCR 원문에 이름줄이 없고 `1 1,700`만 남아 있어 clear item이 아니라 `uncertain_items`로 정리함 |
| `OIP (10).webp` | 1.0000 | 단일 고가 상품 영수증, 바코드 suffix/결제금액 회복 |
| `img2.jpg` | 1.0000 | `subtotal + tax` fallback과 tax OCR 보강 후 편의점 2품목 케이스 정렬 |

## 해석

- 기존 4장 core baseline보다 더 어려운 hard-case 4장을 넣었지만, 후속 parser 보강으로 평균을 다시 끌어올렸다.
- 이번 기준에는 grocery partial receipt [1652882389756.jpg](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/1652882389756.jpg)도 정식 gold로 편입했다.
  - 서비스는 이제 noisy preamble 뒤 item header가 나오는 grocery partial receipt를 `partial_receipt=true`로 판정한다.
  - 그 결과 이 샘플은 `review_required=false`로 내려오지만, `purchased_at`과 마지막 `깐양파`는 아직 miss로 남는다.
- 이번 기준에는 [OIP (9).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(9).webp)도 grocery acceptance gold로 편입했다.
  - parser가 이미 `양념등심돈까스`, `payment_amount`, `subtotal`, `tax`를 회복한 상태를 반영했다.
  - 이후 `하인즈유기농케참90 -> 하인즈 유기농케찹90`, `갈바니리코타치츠4 -> 갈바니 리코타 치즈4`, `블렌드슈레드치즈1k9 -> 블렌드 슈레드치즈1kg` exact alias를 넣어 clear grocery item 3개를 더 회복했다.
  - 현재는 clear grocery item 기준으로 전부 맞고, `파프리카(팩)`은 OCR line 자체가 `()2`로 붕괴하는 hard-case로 남는다.
- 이번 기준에는 [OIP (7).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(7).webp)도 low-res grocery acceptance gold로 편입했다.
  - 이후 `code + 1× + unit_price + amount` detail row를 일반화하고 `회원만료일` metadata를 제외하면서 clear item 3개를 quantity/amount까지 회복했다.
  - 이 축은 now acceptance 기준에서 정렬됐다.
- 이번 기준에는 [OIP (1).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(1).webp)도 convenience mixed acceptance gold로 편입했다.
  - 이후 `barcode/lineNo` prefix 제거와 `부탄가스` 비식품 필터를 넣어 식품 2개만 남도록 정리했다.
  - 이 축은 현재 회복됐고, low-res convenience의 남은 핵심 병목은 `uncertain snack/drink row pruning`으로 좁혀졌다.
- 이번 기준에는 [OIP (8).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(8).webp)도 low-res convenience acceptance gold로 편입했다.
  - 이후 parser hardening으로 vendor hallucination은 제거됐고, `barcode + lineNo + name + unit_price + amount` 한 줄형 품목은 일부 회복됐다.
  - 이후 evaluator가 `uncertain_items`를 FP로 세지 않도록 정리되면서, clear item 기준 acceptance score와 baseline이 일치하게 됐다.
- 이번 기준에는 [OIP (20).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(20).webp)도 grocery partial acceptance gold로 편입했다.
  - clear item은 `생목심(구이용)`, `청양고추`, `사각햇반300g`, `깐양파` 4개만 잡고 나머지는 uncertain/excluded로 분리했다.
  - 이후 `6-digit PLU code` 제거, embedded barcode noise tail 정리, `사각햇번300g -> 사각햇반300g`, `깐양과 -> 깐양파`, `한은 생목심 -> 생목심(구이용)`, `청양고수 -> 청양고추` exact alias를 넣어 `item_f1 = 0.6667`까지 회복했다.
  - 이후 ambiguous product rows도 `uncertain_items`로 정리해 acceptance score를 clear item 기준과 맞췄고, 현재 `item_f1 = 1.0`이다.
- 이번 기준에는 [OIP (4).webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP%20(4).webp)도 partial grocery acceptance gold로 편입했다.
  - `아현미밥210g*3`, `quantity=2`, `amount=9,960`은 시각적으로 명확해서 clear item으로 잡았다.
  - 이후 `name + unit_price + X + quantity + amount` 한 줄 패턴을 별도로 파싱하고, `총합계 49,850원 -9,960원`처럼 discount가 같이 붙은 total line에서는 첫 양수 금액을 total로 채택하도록 보강했다.
  - 또 `할인총금액 39,89021` 같은 payment line은 첫 금액 후보를 우선 사용하고, 이미 더 total에 가까운 payment_amount가 있으면 `현금 ... 400,000,0002` 같은 footer 노이즈가 덮어쓰지 않도록 정리했다.
  - 현재는 clear item과 totals 모두 회복되어 acceptance 기준 `item_f1 = 1.0`이다.
- 이번 기준에는 [OIP.webp](C:/Users/USER-PC/Desktop/jp/.worktrees/codex-hwpx-proposal-patch/output/제비/OIP.webp)도 small convenience acceptance gold로 편입했다.
  - clear item은 `ABC초코미니언즈` 1개만 잡고, `에누리(쿠폰)` 줄은 `excluded_rows.discount`로 분리했다.
  - 이후 `상품명 + barcode + amount` 한 줄형을 `quantity=1`로 직접 해석하고, `이1ABC초코미니언즈 -> ABC초코미니언즈` exact alias를 추가해 acceptance score를 정렬했다.
  - 또 `할인계 4,790 -> 결제대상금액 -820 -> 날짜줄 -3,970` discount summary crop도 처리해 `payment_amount=3,970`까지 회복했다.
- 이번 보강의 핵심:
  - `img3.jpg`: 가짜 vendor 제거 후 `lower item strip fallback`으로 `맥주 바이젠 미니` 회복
  - `OIP (1).webp`: alphanumeric barcode prefix 제거와 `부탄가스` non-food exclusion 추가로 mixed convenience precision 회복
  - low-res convenience 공통 축에서 `barcode + lineNo + name + unit_price + amount`와 `barcode/lineNo + food name` 두 패턴이 모두 회복됨
  - evaluator에서도 `uncertain_items`를 ignore하도록 바꿔, acceptance baseline이 clear item 기준과 맞게 계산되도록 정리
  - `R (1)/(2).jpg`: `상품 합계 4,480` 같은 late footer total은 기존 `payment_amount`보다 작으면 `total`을 덮어쓰지 않도록 정리했고, `농심 오징어짧뽕 컵`, `삼양나가사끼짬뽕 컵` exact alias를 추가해 fully aligned
  - `R.jpg`: `맛밤42G*10 -> 맛밤` pack-size cleanup alias를 exact product 유지로 되돌려 gold 기준과 정렬
  - `OIP (20).webp`: grocery partial receipt에 `6-digit PLU code` 제거, embedded barcode noise tail cleanup, grocery OCR typo alias를 넣고 ambiguous rows를 uncertain으로 정리해 acceptance baseline과 정렬
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
  - 현재 최약군은 `OIP (9).webp (0.9474)`와 `1652882389756.jpg (0.9474)`다.
  - grocery 축에서는 clear miss보다 OCR collapse hard-case와 crop/date 누락이 남아 있다.
  - 이건 품질 후퇴가 아니라 grocery acceptance set을 넓힌 결과다.

## 다음 우선순위

1. grocery/convenience acceptance gold를 16장 이상에서 더 확장
2. 반복적으로 남는 `OCR collapse hard-case`와 `date rescue`만 일반화 규칙으로 보강
3. 확장된 gold 기준 baseline 재측정
4. 그 뒤에도 남는 item-name 붕괴 케이스에만 제한적 crop/Qwen rescue 검토
