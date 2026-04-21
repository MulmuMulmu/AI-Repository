# OCR Pipeline Status - 2026-04-18

## 목적

이 문서는 2026-04-18 기준 현재 영수증 OCR 파이프라인이 어디까지 구현되었는지와, 무엇이 검증되었고 무엇이 아직 비어 있는지를 정리한다.

## 현재 완료 범위

### 1. 업로드부터 구조화 응답까지의 기본 흐름

현재 공개 OCR API는 `POST /ai/ocr/analyze`이며, 이미지 업로드 후 아래 순서로 처리한다.

1. 임시 파일 저장
2. 이미지 전처리
3. PaddleOCR 기반 텍스트 + bbox 추출
4. row merge
5. rule-based 영수증 파싱
6. 날짜/합계/품목 검증
7. 필요 시 선택적 Qwen 보정
8. legacy API contract로 응답 변환

관련 코드:

- `main.py`
- `ocr_qwen/preprocess.py`
- `ocr_qwen/services.py`
- `ocr_qwen/receipts.py`

### 2. 전처리

현재 전처리에서 수행하는 것:

- grayscale
- autocontrast
- contrast boost
- rotation hint 반영
- quality score 계산
- `small_image`, `low_contrast`, `blurry`, `low_quality` 판정

현재 전처리의 한계:

- 자동 deskew는 제한적이다.
- perspective correction은 아직 미구현이다.
- 심한 그림자/반사/원근 왜곡에 대한 보정은 약하다.

### 3. PaddleOCR 결과 계약

현재 OCR 결과는 텍스트만 쓰지 않고 아래 정보를 유지한다.

- `text`
- `confidence`
- `line_id`
- `bbox`
- `center`
- `page_order`

이 정보는 row merge와 item assembly에 사용된다.

### 4. rule-based 파서

현재 파서는 다음을 처리한다.

- vendor name 추출
- purchased_at 추출
- totals / payment_amount 추출
- header / items / totals / payment / ignored 구간 분리
- 여러 유형의 품목 줄 조립

현재 커버하는 대표 패턴:

- 컬럼형 `상품명 / 수량 / 금액`
- POS 한 줄형
- 바코드 다음 줄 상세형
- 상품명 한 줄 + 숫자 상세 줄 2줄형
- gift row `상품명 1 증정품`
- code + price + inferred quantity 패턴

현재 제거하는 대표 노이즈:

- 쿠폰
- 봉투
- 보증금
- 카드/전표 문구
- 물품가액/세액/합계 등 footer 성격 줄

### 5. review / confidence

현재 파서는 다음 상태를 결과에 포함한다.

- `confidence`
- `review_required`
- `review_reasons`
- `diagnostics.unresolved_groups`

현재 item 단위 review 이유 예시:

- `low_confidence`
- `missing_purchased_at`
- `unknown_item`
- `missing_quantity_or_unit`
- `missing_amount` (gift 제외, Qwen 보정 대상으로 사용)

현재 전역 review 이유 예시:

- `missing_vendor_name`
- `missing_purchased_at`
- `unresolved_items`
- `total_mismatch`

### 6. Qwen 보정

Qwen은 현재 메인 파서가 아니다.

역할:

- header rescue
  - vendor/date 보정
- item normalization
  - 저신뢰/의심 품목만 선택 보정

현재 정책:

- OCR + rule-based가 1차 결과를 만든다.
- review item이 있을 때만 Qwen payload를 만든다.
- Qwen 실패 시 전체 응답은 fallback 유지한다.

### 7. 합성 영수증 데이터셋 생성기

현재 저장소에는 템플릿 기반 합성 영수증 생성기가 추가되어 있다.

구성:

- `ocr_qwen/synthetic_receipts.py`
- `scripts/build_synthetic_receipts.py`

현재 기본 생성 목표:

- 총 300장
- 레이아웃 분포
  - `convenience_pos`: 90
  - `mart_column`: 90
  - `barcode_detail`: 60
  - `compact_single_line`: 30
  - `mixed_noise`: 30

현재 생성 산출물:

- 이미지 파일
- annotation JSON
- manifest JSON

현재 저장 경로:

- `data/receipt_synthetic/receipt-synthetic-v1/`

### 8. 추천 시스템 현재 구조

현재 추천 API는 `POST /ai/recommend`이며, 공개 request/response 계약은 유지한 상태에서 내부 로직만 고도화되었다.

현재 운영 기준:

- 레시피 데이터:
  - `data/db/recipes.json`
  - `data/db/recipe_ingredients.json`
  - `data/db/recipe_steps.json`
- 재료 데이터:
  - `data/db/ingredients.json`
- 내부 추천 엔진:
  - `recipe_recommender.RecipeRecommender`

현재 정책:

- `/ai/ingredient/prediction`은 계속 broad product mapping 역할만 한다.
- `/ai/recommend`는 DB에 존재하는 `ingredientId` 중에서
  `recipe_ingredients.json`에 실제로 등장하는 재료만 추천 입력으로 사용한다.
- 즉, OCR에서 상품이 재료로 매핑되어도 레시피 그래프에 없는 재료는 추천 단계에서 자동 제외된다.
- 개인화 입력도 함께 받을 수 있다.
  - `preferredIngredientIds`
  - `dislikedIngredientIds`
  - `allergyIngredientIds`
  - `preferredCategories`
  - `excludedCategories`
  - `preferredKeywords`
  - `excludedKeywords`
- 개인화 처리 원칙:
  - `dislikedIngredientIds` + `allergyIngredientIds`는 hard filter
  - `excludedCategories`, `excludedKeywords`도 hard filter
  - `preferredIngredientIds`, `preferredCategories`, `preferredKeywords`는 score boost

현재 추천 API 공개 응답은 그대로 유지한다.

- 유지 필드:
  - `recipeId`, `name`, `category`, `imageUrl`
  - `matchedIngredients`, `missingIngredients`
  - `matchRate`, `totalIngredientCount`
- 내부 엔진이 가진 `score`, `weightedMatchRate`, `coreCoverage`, `substitutions`는 현재 외부에 노출하지 않는다.

### 9. 실사 receipt dataset 현재 구조

현재 실사 계열 데이터셋 자산은 아래처럼 정리된다.

- gold-like set:
  - `data/receipt_gold/assistant-visual-v0`
  - annotation `4개`
- gold-like set 신규:
  - `data/receipt_gold/jevi-gold-v0`
  - annotation `4개`
  - `assistant-curated draft`
- silver set:
  - `data/receipt_silver/jevi-silver-v0`
  - annotation `11개`
  - 초기 제비 샘플 기반
- silver set 최신본:
  - `data/receipt_silver/jevi-silver-v1`
  - image `11개`
  - `total_item_count = 100`
  - `review_required_count = 10`
- silver set 확장본:
  - `data/receipt_silver/jevi-silver-v2`
  - image `35개`
  - `total_item_count = 162`
  - `review_required_count = 32`
  - `.webp` 실사 영수증까지 포함

현재 `제비` 원본 폴더 기준 인벤토리:

- full receipt image `35개`
- crop image `3개`
- full receipt 기준으로는 현재 silver coverage가 완료됐다.
- 아직 남은 미편입 자산은 crop image 위주다.

즉, 현재는 실사 검증 경로가 전혀 없는 상태는 아니고,  
`gold 8장 + silver 35장 + 추가 gold 후보 shortlist` 구조까지는 확보된 상태다.

현재 추가 gold 후보로 볼 만한 샘플:

- `R (2).jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
- `OIP (22).webp`

## 현재 검증 상태

### 테스트

2026-04-18 기준 전체 테스트 결과:

- `160 passed`

집중 검증 테스트:

- `test_ocr_api_contract.py`
- `test_receipt_quality_rules.py`
- `test_receipt_qwen_item_normalization.py`
- `test_receipt_service_date_fallback.py`

세부 확인된 항목:

- GS25 / 세븐일레븐 유형 vendor/date 회귀
- `img2`, `img3` 스타일 품목 조립
- gift row 처리
- gift + barcode detail 금액 비추정 처리
- coupon / bag / false positive 제거
- date fallback
- header rescue / item normalization fallback
- compact merged line 회귀

### 추가 표본 점검

2026-04-18 야간 표본 25장 재검증:

- `review_required_rate`: `0.56`
- 정상화 확인 샘플:
  - `barcode_detail-0001`
  - `compact_single_line-0061`
  - `mixed_noise-0271`

해석:

- 서비스 레이어 오탐은 상당 부분 제거되었다.
- 남은 손실은 `compact_single_line`, `convenience_pos`, `mixed_noise`의 OCR merge 노이즈 비중이 높다.

### 추가 증분

추가 보강 후 확인된 샘플:

- `mixed_noise-0272`: F1 `1.0`
- `mixed_noise-0273`: F1 `1.0`
- `mixed_noise-0274`: F1 `1.0`
- `mixed_noise-0275`: F1 `1.0`

현재 가장 약한 군:

- `convenience_pos`
  - 품목명이 통째로 다른 문자열로 OCR되는 경우가 남아 있다.
- `barcode_detail`
  - 품목명 줄 자체가 누락되면 rule-based 복구 한계가 있다.

### 최신 공식 300장 synthetic 재평가

2026-04-19 최신 코드 기준 `synthetic-eval-ocr-only.json` 재생성 결과:

- `item_name_f1_avg`: `0.905`
- `quantity_match_rate_avg`: `0.9828`
- `amount_match_rate_avg`: `0.9834`
- `review_required_rate`: `0.3067`
- `avg_processing_seconds`: `6.7348`

직전 공식 리포트 대비 변화:

- `item_name_f1_avg`: `0.9019 -> 0.905`
- `quantity_match_rate_avg`: `0.9881 -> 0.9828`
- `amount_match_rate_avg`: `0.9901 -> 0.9834`
- `review_required_rate`: `0.33 -> 0.3067`
- `avg_processing_seconds`: `11.6199 -> 6.7348`

레이아웃별 최신 상태:

- `barcode_detail`: `0.9271`
- `compact_single_line`: `0.8921`
- `convenience_pos`: `0.8686`
- `mart_column`: `0.9386`
- `mixed_noise`: `0.8822`

주의:

- 현재 `vendor_name_accuracy=0.88`은 실제 파서 약점이 반영된 값이다.
- 대표 원인:
  - `7.-ELEVEN`, `7,-ELEVEN` 같은 OCR punctuation 잡음
  - convenience hard-case에서 상단 vendor line이 `금루금`, `금크루금`처럼 완전히 깨지는 경우
- 즉, 다음 vendor 고도화는 evaluator 수정이 아니라 parser normalization과 실사 기반 fallback 설계 쪽이 맞다.

### convenience hard-case variant 상태

2026-04-19 기준 convenience synthetic를 hard-case variant로 재생성하고 부분 재평가했다.

전체 convenience 90장 최신 재평가:

- `item_name_f1_avg`: `0.8686`
- `quantity_match_rate_avg`: `0.9778`
- `amount_match_rate_avg`: `0.9778`
- `review_required_rate`: `0.4111`

variant별:

- `header_noise`: `0.8683`
- `split_rows`: `0.9214`
- `default`: `0.7976`
- `narrow_columns`: `0.8904` (`22장 subset 재평가`)

해석:

- `split_rows`는 parser 보강 이후 안정화되었다.
- `narrow_columns`는 현재 명확히 개선되었고, 최저점 구간은 더 이상 아니다.
- convenience 전체는 `0.8220 -> 0.8686`으로 올라갔다.
- 다음 고도화는 `vendor_name_accuracy`와 mixed-noise 저점 샘플 정리에 집중하는 것이 효율적이다.

### mixed-noise 추가 부분 재평가

2026-04-19 추가 parser 보강 후 `mixed_noise` 30장 subset을 별도 재평가했다.

- 저장:
  - `reports/synthetic-eval-ocr-only.mixed-noise.json`
  - `reports/synthetic-eval-ocr-only.mixed-noise.md`
- 결과:
  - `item_name_f1_avg`: `0.9711`
  - `quantity_match_rate_avg`: `0.9933`
  - `amount_match_rate_avg`: `1.0`
  - `review_required_rate`: `0.0667`

해석:

- `mixed_noise`의 남아 있던 대표 저점 샘플
  - `계란 10구 4,590 1 증정품`
  - `허쉬쿠키앤초코 1,600 1 증정품`
  - `라라스윗 바닐라파인트4746,900213,800`
  - `닭주물럭2.2kg 14,900 )1 14,900`
  를 parser 보강으로 복구했다.
- 공식 300장 리포트는 subset 평가 후 백업본으로 복구해 canonical 상태를 유지했다.

### vendor 추가 부분 재평가

2026-04-19 추가 vendor normalization 후 `barcode_detail` 60장 subset을 별도 재평가했다.

- 저장:
  - `reports/synthetic-eval-ocr-only.barcode-detail.json`
  - `reports/synthetic-eval-ocr-only.barcode-detail.md`
- 결과:
  - `vendor_name_accuracy`: `1.0`
  - `item_name_f1_avg`: `0.9271`
  - `quantity_match_rate_avg`: `1.0`
  - `amount_match_rate_avg`: `1.0`

해석:

- `7.-ELEVEN`, `7,-ELEVEN`는 alias normalization으로 해결됐다.
- 남은 vendor 손실은 주로 convenience hard-case처럼 OCR이 상단 상호 자체를 읽지 못하는 경우다.
- 공식 300장 리포트는 subset 평가 후 백업본으로 복구했고, 전체 재평가는 아직 다시 돌리지 않았다.

### top-strip vendor fallback 추가

2026-04-19 추가로 서비스 레이어에 `top-strip vendor fallback`을 넣었다.

적용 내용:

- main OCR에서 `vendor_name`이 비어 있을 때
- 이미 존재하던 `top_strip_extraction` 결과에서 vendor를 한 번 더 추출
- 성공 시
  - `diagnostics.vendor_fallback_used = true`
  - `diagnostics.vendor_fallback_source = "top_strip"`

의미:

- `main OCR은 놓쳤지만 상단 crop OCR은 잡는` 케이스를 즉시 회수할 수 있다.
- 이 fallback은 Qwen 없이도 동작한다.

현재 한계:

- convenience hard-case 일부 샘플은 `top_strip` 재OCR에서도
  - `금루금`
  - `금리루금`
  같은 잡음만 읽힌다.
- 따라서 이 군은 `top-strip fallback`만으로는 해결되지 않고, OCR-only 경로에서 더 이상의 deterministic 복구는 어렵다.
- 이 구간은 다음 단계에서
  - Qwen header rescue 활성화
  또는
  - 실사 상단 상호 fallback 전략
  으로 넘기는 것이 맞다.

## 현재 품질 판단

### 잘 될 가능성이 높은 입력

- 최근 스마트폰으로 촬영
- 영수증 전체가 프레임 안에 포함
- 텍스트가 육안으로 읽힘
- 편의점/마트/일반 POS형 구조
- 과도한 반사, 극단적 흔들림, 심한 잘림이 없음

### 아직 불안한 입력

- 상단/하단 일부 잘림
- 심한 기울기
- 그림자/반사
- 감열지 흐림이 심한 경우
- 비식품 품목과 안내성 문구가 강하게 섞이는 특수 레이아웃

## 문서화 상태 평가

현재 문서는 다음까지는 정리되어 있다.

- 구현 개요
- TODO
- 품질 baseline
- gold/silver dataset 개요
- v0.1 release 문서

아직 약한 부분:

- 날짜별 현재 상태 문서
- 세션 단위 업데이트 문서
- 입력 품질 기준 문서
- 합성데이터 생성 규격 문서
- 운영용 재촬영 가이드 문서

위 5개는 현재 정리 완료 상태다. 대신 아직 약한 부분은 아래다.

- 합성셋을 OCR 평가 스크립트에 직접 연결한 자동 benchmark
- 합성셋별 정량 지표 리포트 자동 생성
- 합성셋과 실사셋 비교 리포트

## 다음 우선순위

1. 합성 영수증 기반 구조 회귀셋 설계
2. 정상 입력 기준 정의
3. 저품질 입력 재촬영 기준 정의
4. 소량 실사셋과 합성셋의 역할 분리

## 2026-04-21 추가 보강

실사 `image.png`, `R.jpg` 계열을 기준으로 parser를 한 번 더 보강했다.

추가한 내용:

- `16, 980`, `6, 780`, `6, 680`처럼 공백이 끼어 있는 numeric detail row 정규화
- `상품명 + 바코드/숫자상세` 2줄형 품목 복구 강화
- `품`, `세 물물`, `세 품품세`, `가` 같은 summary fragment tail 제거
- `TE.CO.KR` 같은 domain noise 품목 제거
- `크라우참쌀서과 -> 크라운참쌀선과`, `해태구문감자 -> 해태구운감자` OCR alias 추가

효과:

- 실제 서비스 경로에서 `image.png`는 item 11개가 quantity/amount까지 정상 복구됐다.
- `image.png`의 totals는 `117,580 / 112,580`까지 다시 잡힌다.
- `R.jpg`는 현재 `홈플러스` vendor와 snack 주요 품목 대부분이 안정적으로 나온다.

실사 gold baseline 최신 결과:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8916`
- `quantity_match_rate_avg = 0.9188`
- `amount_match_rate_avg = 0.9163`
- `review_required_accuracy = 0.5`

남은 병목:

- `R.jpg`의 snack OCR 오타
  - `와이멘씨라이스퍼프`
  - `부드러운쿠키블루베`
- `image.png`의 vendor/date 누락
  - totals와 items는 회복됐지만 header 자체는 여전히 약하다.
- 확장 gold hard-case
  - `img3.jpg`
  - `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `OIP (10).webp`

## 2026-04-21 img3 lower item strip fallback

추가한 내용:

- service 레이어에 `lower item strip fallback` 추가
- 적용 조건은 좁게 제한했다.
  - `receipt_image_url`
  - 저화질 구간
  - item header 아래에서 `OV00` 같은 짧은 placeholder 행 뒤에 barcode/qty/amount 행이 이어지는 경우
- fallback은 원본 하단 strip만 다시 OCR하고, 기존 결과에 없는 새 품목만 병합한다.

추가 alias:

- `L맥주바이젠미니 -> 맥주 바이젠 미니`
- `롯데 앤디카페조릿 다크 -> 롯데 앤디카페 초콜릿 다크빈`

효과:

- `img3.jpg`
  - `맥주 바이젠 미니` 복구
  - `diagnostics.item_strip_fallback_used = true`
  - `item_f1 = 0.2857 -> 0.5`
- fallback 범위를 다시 좁혀서
  - `R.jpg`
  - `SE-...jpg`
  - `OIP (10).webp`
  에서는 추가 오탐 없이 기존 성능을 유지한다.

검증:

- 신규 서비스 fallback 테스트 1개 추가
- 전체 테스트: `146 passed`

## 2026-04-21 gold evaluation pack-count normalization

추가한 내용:

- gold/silver 비교 정규화에서 `(5입)`, `(2개)` 같은 parenthetical pack-count 표기를 제거
- 범위는 좁게 제한했다.
  - `속이편한 누룽지(5입)` vs `속이편한 누룽지`는 같은 품목으로 본다.
  - `355ml`, `500ml` 같은 실제 용량 차이는 그대로 다른 품목으로 유지한다.

효과:

- `img3.jpg`는 parser가 이미 복구한 `속이편한 누룽지` 2건이 정당하게 매칭된다.
- `img3.jpg item_f1 = 0.5 -> 1.0`
- gold 8장 baseline:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.8743`

검증:

- silver dataset 테스트 2개 추가
- 전체 테스트: `148 passed`

## 2026-04-21 SE gift-tail item strip fallback

추가한 내용:

- `gift_tail` 전용 item strip fallback 추가
  - `1 증정풍`처럼 상품명 없이 gift tail만 남은 row를 fallback trigger로 사용
  - 이 경우에는 bbox 기반 dynamic crop 대신, 실제 샘플에서 더 잘 읽히는 중간 item band를 다시 OCR
- fallback merge도 gap kind 기준으로 제한
  - `gift_tail`이면 gift candidate만 병합
  - `placeholder_barcode`면 일반 candidate만 병합
- alias 추가
  - `투썰로알밀크티 -> 투썸로얄밀크티`
  - `투썸로알밀크티 -> 투썸로얄밀크티`

효과:

- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `diagnostics.item_strip_fallback_used = true`
  - `item_strip_fallback_added_count = 1`
  - 누락됐던 `투썸로얄밀크티` gift item 복구
  - `item_f1 = 0.9000 -> 0.9524`
- `img3.jpg`
  - 기존처럼 `item_strip` fallback 유지
  - `item_f1 = 1.0` 유지
- `R.jpg`
  - fallback 비활성 유지

최신 gold 8장 baseline:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8877`

검증:

- 신규 서비스 fallback 테스트 1개 추가
- 전체 테스트: `149 passed`

## 2026-04-21 gold evaluation metric expansion

추가한 내용:

- `compare_silver_annotation()`에 이름 F1 외 추가 지표를 넣음
  - `quantity_match_rate`
  - `amount_match_rate`
  - `review_required_match`
- `evaluate_receipt_silver_set.py` summary에도 평균 지표 추가
  - `quantity_match_rate_avg`
  - `amount_match_rate_avg`
  - `review_required_accuracy`

최신 gold 8장 baseline:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8916`
- `quantity_match_rate_avg = 0.9188`
- `amount_match_rate_avg = 0.9163`
- `review_required_accuracy = 0.5`

해석:

- 이름/수량/금액은 이미 꽤 올라와 있다.
- 현재 실사 gold 축의 다음 병목은 `review_required` 정렬이다.
  - `2a4dd3...jpg`, `SE-...jpg`는 parser 품목 복구보다 review 정책 쪽이 점수를 더 깎고 있다.

검증:

- silver dataset 테스트 2개 추가
- 전체 테스트: `151 passed`

## 2026-04-21 review alignment follow-up

추가한 내용:

- `low_confidence` 단독은 item-level unresolved에서 제외
- item header가 없는 item-block crop도 `partial_receipt`로 판단 가능하도록 확장
- `unconsumed_item_amount_total` 계산 추가
  - parser가 소비하지 못한 잔여 item amount를 totals 검증에 반영
  - 결제 footer 금액은 합산에서 제외
- parser filter 보강
  - `미클립스 피치향 34g` 같은 pack-size dangling single-line은 item으로 유지하지 않음

효과:

- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
  - `review_required = false`
  - `partial_receipt = true`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `review_required = false`
  - `unconsumed_item_amount_total = 5190.0`
- gold 8장 baseline:
  - `item_name_f1_avg = 0.8916`
  - `review_required_accuracy = 0.5`

검증:

- 신규 review alignment 테스트 3개 추가
- parser 회귀 테스트 1개 추가
- 전체 테스트: `155 passed`

## 2026-04-21 서비스 review 정책 보강

추가한 내용:

- `missing_purchased_at`는 item-level unresolved 사유에서 제외
- OCR 원문에서 `할인`, `에누리`, `포인트`, `S-POINT` 등의 음수 금액을 모아 `discount_adjustment_total`로 계산
- `상품명` header로 바로 시작하는 cropped 입력은 `partial_receipt=true`로 기록
- partial receipt는 vendor/date가 없어도 item/totals가 정상이고 할인 반영 합계가 맞으면 review로 올리지 않음

현재 효과:

- `image.png`
  - `review_required = false`
  - `diagnostics.partial_receipt = true`
  - `diagnostics.discount_adjustment_total = -11500.0`
  - `diagnostics.unresolved_groups = 0`
- `R.jpg`
  - 여전히 `review_required = false`
  - 일반 full receipt로 유지

추가 정리:

- `single_line_name_amount` 경로에서 이름에 붙은 가격 꼬리를 제거
- 예:
  - `와이멘씨라이스퍼프1 3,980` -> `와이멘씨라이스퍼프`
- 범위는 trailing orphan digit `1` 케이스로만 제한해서
  - `갈바니'리코타치느4`
  같은 실제 상품명 숫자는 보존한다.

## 2026-04-22 focused receipt + packaging + final consumed-id alignment

추가한 내용:

- `ReceiptParser`
  - `용기면` 같은 식품명은 packaging noise로 버리지 않도록 예외 처리
  - filtered-out non-food row는 final surviving items 기준으로 다시 계산한 `consumed_line_ids`에서 제외
- `ReceiptParseService`
  - focused receipt 예외 추가
    - `item_strip_fallback_used` + purchased_at 존재
    - 또는 OCR row 수가 충분한 단일상품 payment receipt
    - 위 두 경우에는 `missing_vendor_name`만으로 review를 올리지 않음
  - `unconsumed_item_amount_total` 계산에서 `부 I 가 세`, 포인트/고객님/소멸 문구 같은 metadata row 제외

검증:

- 신규 parser/service 회귀 테스트 5개 추가
- 전체 테스트: `160 passed`

효과:

- `R (1).jpg`, `R (2).jpg`
  - `농심 쌀국수 용기면 6입` 2줄 품목 복구
  - `item_f1 = 0.8889 -> 0.9286`
  - non-food row `1,000`이 totals reconciliation에 다시 반영되면서 `total_mismatch` 해소
- `img3.jpg`, `OIP (10).webp`
  - focused receipt 예외로 `missing_vendor_name` review 제거
- 최신 gold 8장 baseline:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.9015`
  - `quantity_match_rate_avg = 0.9367`
  - `amount_match_rate_avg = 0.9342`
  - `review_required_accuracy = 1.0`
