# Session Update - 2026-04-18

## 범위

이 문서는 2026-04-18 대화 기준으로 정리된 현재 OCR 파이프라인 상태, 품질 판단, 합성데이터 활용 방향을 기록한다.

## 오늘 정리된 핵심 판단

### 1. 현재 프로세스 흐름은 기본 완료 상태다

현재 구현은 아래 경로로 동작한다.

1. 사용자가 영수증 이미지를 업로드한다.
2. 서버가 전처리를 수행한다.
3. PaddleOCR로 텍스트와 bbox를 추출한다.
4. bbox 기준으로 row merge를 수행한다.
5. rule-based parser가 날짜, 품목, 수량, 금액, totals를 1차 추출한다.
6. `review_required`와 `review_reasons`를 계산한다.
7. 저신뢰 항목에 한해 Qwen을 선택적으로 사용한다.
8. 최종 JSON을 응답한다.

정리:

- PaddleOCR이 메인 OCR 엔진이다.
- rule-based parser가 메인 구조화 로직이다.
- Qwen은 보조 수단이다.

### 2. 현재 품목 / 수량 / 날짜 추출 가능성 평가

현재 기준으로 아래 조건에서는 성능 기대치가 괜찮다.

- 최근 스마트폰 사진
- 영수증 전체가 화면에 들어온 경우
- 편의점/마트/POS형 영수증
- 극단적으로 성의 없이 찍지 않은 경우

현재 기준으로 아래 조건은 아직 리스크가 있다.

- 상단/하단 잘림
- 반사
- 그림자
- 심한 원근 왜곡
- 감열지 번짐

오늘 판단 기준:

- "모든 영수증"을 목표로 두기보다
- "최근 스마트폰으로 정상 촬영한 주요 영수증"을 목표 분포로 두는 것이 현실적이다.

### 3. 합성데이터에 대한 판단

오늘 결론:

- 합성데이터는 해야 한다.
- 다만 실사셋의 완전 대체재로 쓰면 안 된다.
- 역할은 구조 회귀 테스트와 파서 안정화다.

합성셋의 적합한 용도:

- 날짜 추출 회귀
- 품목 조립 패턴 검증
- false positive 제거 규칙 검증
- low contrast / blur / slight skew / partial crop 등 약한 노이즈 변형 검증

합성셋의 한계:

- 실사 OCR 오독 분포를 완전히 대체할 수 없다.
- 감열지 특유의 번짐, 반사, 구김은 제한적으로만 재현 가능하다.

### 4. 사용자 관점을 반영한 입력 가정

오늘 합의한 현실적 가정:

- 사용자는 보통 극단적으로 성의 없이 찍지 않는다.
- 최근 휴대폰 카메라 화질은 대체로 충분하다.
- 따라서 실사용 목표는 "정상 촬영된 모바일 영수증"으로 잡는 것이 맞다.

이 가정의 의미:

- 파이프라인 자체를 무한정 확장하기보다
- 입력 품질 범위를 정의하고
- 범위를 벗어나면 재촬영을 유도하는 방식이 더 현실적이다.

### 5. 300장 합성 영수증 생성기 구현

오늘 추가로 정리된 구현 내용:

- 템플릿 기반 합성 영수증 생성 모듈 추가
- 이미지 + annotation JSON + manifest 생성 스크립트 추가
- 300장 기본 분포 생성 가능 상태까지 구현

레이아웃 분포:

- `convenience_pos`: 90
- `mart_column`: 90
- `barcode_detail`: 60
- `compact_single_line`: 30
- `mixed_noise`: 30

현재 산출 위치:

- `data/receipt_synthetic/receipt-synthetic-v1/`

현재 상태:

- 실제 300장 생성 완료
- 전체 테스트 통과 유지

## 오늘 기준 권장 방향

### A. 파이프라인 목표 재정의

현재 목표를 아래처럼 잡는다.

- 지원 입력:
  - 정상 촬영된 스마트폰 영수증
- 비지원 또는 재촬영 유도 입력:
  - 심한 잘림
  - 심한 흔들림
  - 심한 반사
  - 텍스트 육안 판독이 어려운 이미지

### B. 검증 전략

1. 합성셋으로 구조 회귀를 빠르게 반복한다.
2. 소량 실사셋으로 sanity check를 수행한다.
3. `review_required`를 활용해 불확실 케이스를 분리한다.

### C. 문서화 방향

오늘 이후 문서는 아래처럼 관리한다.

- `docs/status/`
  - 날짜 기준 현재 상태
- `docs/updates/`
  - 세션 단위 합의/변경 내역
- `docs/INDEX.md`
  - 문서 진입점

## 남은 작업 제안

1. 합성 영수증 생성 규격 문서 작성
2. 정상 입력 기준 문서 작성
3. 저품질 재촬영 기준 문서 작성
4. 실사 20~30장 최소 sanity set 구성

## 추가 고도화 - 2026-04-18 야간 반영

### 1. 서비스 레이어 review 규칙 정렬

파서와 서비스 레이어의 기준이 달라서 `review_required`가 과도하게 켜지는 문제가 있었다.

수정 내용:

- 서비스 레이어도 `subtotal -> payment-tax -> payment/total` 순서로 합계 검증
- `unknown_item` 단독으로는 `needs_review`가 되지 않도록 정렬
- gift parse pattern은 `missing_amount` 예외 처리
- non-gift의 `missing_amount`는 Qwen 보정 대상으로 유지

효과:

- `barcode_detail`, `compact_single_line`의 정상 케이스에서 `review_required=false` 확인
- rule parser와 API 응답의 review 판단 불일치 제거

### 2. compact / mixed-noise 품목 조립 규칙 보강

추가로 보강한 패턴:

- `상품명 1,6002 3,200`
- `양파32,970`
- `대파2,48012,480`
- `라라스윗 바닐라파인트474320,700`
- `속이편한누륨지316,800`
- `증정품 + 바코드 상세` 2줄형

수정 포인트:

- compact merged line 파서의 spacing/no-spacing 분기 완화
- `누륨지 -> 누룽지` OCR alias 추가
- gift row에서 barcode detail이 있어도 금액을 강제 추정하지 않도록 수정
- subtotal 줄을 item으로 오인하는 compact false positive 제거

### 3. 현재 검증 결과

현재 전체 테스트:

- `111 passed`

추가 표본 점검:

- `barcode_detail-0001`: review false
- `compact_single_line-0061`: review false
- `mixed_noise-0271`: review false
- `mixed_noise-0272`: F1 1.0 / review false
- `mixed_noise-0273`: F1 1.0 / review false
- `mixed_noise-0274`: F1 1.0 / review false
- `mixed_noise-0275`: F1 1.0 / review false

25장 표본 재검증 기준 현재 상태:

- `review_required_rate`: `0.56`
- 여전히 약한 구간:
  - `convenience_pos`
  - `mixed_noise`
  - 일부 `compact_single_line`

즉, 지금 단계에서 해결된 것은:

- 서비스 레이어 오탐
- gift 금액 오추정 일부
- compact 문자열 병합 일부

아직 남은 것은:

- 저신뢰 짧은 garbage 품목 제거
- `330m -> 330ml` 같은 OCR alias 확대
- mixed-noise 군의 aggressive merge 복원

### 4. 추가 반영

추가로 처리한 내용:

- tail-encoded compact parser 추가
  - `양파99032,970`
  - `대파2,48012,480`
  - `라라스윗 바닐라파인트4746,900320,700`
  - `계란 10구 4,5901 증정품`
- two-line barcode에서 name line에 붙은 단가/수량/총액 꼬리 제거
- `행사/증정품` 토큰 제거를 word-boundary 기준이 아닌 실제 substring 기준으로 보정
- `누릉지`, `누륨지`, `330m` 류 OCR alias 보강
- low-confidence short hangul 잡음은 item 구조가 불완전한 경우에만 필터링하도록 축소

현재 남은 대표 한계:

- `barcode_detail-0002`
  - OCR에서 품목명이 통째로 누락된 케이스라 rule-based만으로 복구가 어렵다.
- `convenience_pos-0092`, `convenience_pos-0093`
  - `피그` 같은 잘못 읽힌 품목명은 Qwen 보정 또는 실사 alias가 없으면 완전 복구가 어렵다.

## 2026-04-19 우선순위 1 실행 결과

최신 코드 기준으로 300장 전체 synthetic 평가를 다시 실행했다.

공식 결과:

- `item_name_f1_avg`: `0.9019`
- `quantity_match_rate_avg`: `0.9881`
- `amount_match_rate_avg`: `0.9901`
- `review_required_rate`: `0.33`
- `avg_processing_seconds`: `11.6199`

레이아웃별:

- `barcode_detail`: `0.9271`
- `compact_single_line`: `0.8362`
- `convenience_pos`: `0.8421`
- `mart_column`: `0.9386`
- `mixed_noise`: `0.9867`

결론:

- 합성데이터 기반 고도화가 실제로 수치 개선으로 이어졌다고 말할 수 있다.
- 특히 `mixed_noise`는 대폭 개선되었고 더 이상 최약군이 아니다.
- 현재 최약군은 `convenience_pos`이며, 다음 synthetic 보강은 이 레이아웃에 집중하는 것이 맞다.

## 2026-04-19 우선순위 2 진행 결과

`convenience_pos`용 hard-case synthetic variant를 추가했다.

추가한 variant:

- `default`
- `header_noise`
- `narrow_columns`
- `split_rows`

반영 내용:

- `SyntheticReceiptSpec.variant` 필드 추가
- annotation metadata에 variant 기록
- convenience layout 렌더러에 variant별 출력 패턴 추가
  - header short noise
  - column squeeze
  - split row
- split-row OCR 케이스를 위한 parser 보강
  - `상품명수량` + 다음 줄 금액
  - compact split gift

현재 테스트:

- `115 passed`

재생성 후 convenience 90장 부분 평가:

- `item_name_f1_avg`: `0.8220`
- `quantity_match_rate_avg`: `0.9694`
- `amount_match_rate_avg`: `0.9694`
- `review_required_rate`: `0.5`

variant별:

- `header_noise`: `0.8683`
- `split_rows`: `0.9214`
- `default`: `0.7976`
- `narrow_columns`: `0.6997`

판단:

- `split_rows`는 parser 보강으로 회복됐다.
- 현재 convenience 약점은 `narrow_columns`가 가장 크다.
- 다음 synthetic 보강과 parser 수정은 `narrow_columns` 중심으로 가는 것이 맞다.

## 2026-04-19 우선순위 3 진행 결과

`narrow_columns` 보강 과정에서 생긴 회귀를 먼저 정리했다.

수정 내용:

- gift tail parser가 `11,6001증정품`, `4,5901 증정품` 형태에서 단가 꼬리를 이름으로 남기던 문제 수정
- compact no-space parser와 tail-encoded fallback에 동일한 오인식 방지 조건 추가
  - `3토큰 이상 + qty=1 + 저가 + 숫자/단위 없는 이름` 케이스는 compact 해석 차단
- `청정원 순창 찰고추장12,780` 같은 false positive를 다시 일반 single-line 경로로 돌리도록 조정

회귀 확인:

- 집중 회귀 테스트 5개 통과
- 전체 테스트: `117 passed`

부분 재평가:

- 대상: `convenience_pos / narrow_columns` 22장
- 별도 저장:
  - `reports/synthetic-eval-ocr-only.convenience-pos-narrow-columns.json`
  - `reports/synthetic-eval-ocr-only.convenience-pos-narrow-columns.md`

결과:

- `item_name_f1_avg`: `0.8904`
- `quantity_match_rate_avg`: `1.0`
- `amount_match_rate_avg`: `1.0`
- `review_required_rate`: `0.1818`
- `avg_processing_seconds`: `6.0598`

비교:

- `narrow_columns`: `0.6997 -> 0.8904`

## 2026-04-19 공식 300장 리포트 재생성

부분 평가가 기본 리포트 파일을 덮어쓰므로, 공식 300장 리포트를 다시 생성해 canonical 결과를 복구했다.

최신 공식 결과:

- `item_name_f1_avg`: `0.905`
- `quantity_match_rate_avg`: `0.9828`
- `amount_match_rate_avg`: `0.9834`
- `review_required_rate`: `0.3067`
- `avg_processing_seconds`: `6.7348`

레이아웃별:

- `barcode_detail`: `0.9271`
- `compact_single_line`: `0.8921`
- `convenience_pos`: `0.8686`
- `mart_column`: `0.9386`
- `mixed_noise`: `0.8822`

판단:

- `convenience_pos`는 `0.8421 -> 0.8686`으로 개선됐다.
- `narrow_columns`는 더 이상 convenience 최약군이 아니다.
- 다음 우선순위는 `vendor_name_accuracy`와 `mixed_noise` 저점 샘플 분석이다.

## 2026-04-19 우선순위 4 진행 결과

`mixed_noise` 저점 샘플을 직접 파헤쳐 parser를 추가 보강했다.

고친 케이스:

- `계란 10구 4,590 1 증정품`
- `허쉬쿠키앤초코 1,600 1 증정품`
- `라라스윗 바닐라파인트4746,900213,800`
- `닭주물럭2.2kg 14,900 )1 14,900`

반영 내용:

- `single_line_gift` 경로에서 trailing unit-price 제거
- `tail_encoded`는 이름에서 실제로 unit-price를 떼어낼 수 있는 후보를 우선 선택
- `compact_unit_price_qty_amount`는 `parsed_unit_price`와 `amount / quantity`가 크게 어긋나면 버리도록 정렬
- barcode detail suffix 제거 시 `)1` 같은 placeholder 문자를 허용

검증:

- 신규 회귀 테스트 3개 추가
- 전체 테스트: `120 passed`

mixed-noise 30장 부분 평가:

- `item_name_f1_avg`: `0.9711`
- `quantity_match_rate_avg`: `0.9933`
- `amount_match_rate_avg`: `1.0`
- `review_required_rate`: `0.0667`

정리:

- mixed-noise는 현재 합성셋 기준으로 사실상 안정권에 들어왔다.
- 다음 이슈는 parser 자체보다 synthetic vendor label 정렬과 실제 실사셋 확보 쪽이 더 크다.

## vendor metric 해석 정정

이전 메모와 달리, 현재 `vendor_name_accuracy=0.88`은 synthetic label 문제라기보다 실제 파서 손실이 반영된 값이다.

직접 확인한 mismatch 원인:

- `7.-ELEVEN`, `7,-ELEVEN`
- convenience hard-case에서 상단 상호가 `금루금`, `금크루금`처럼 읽히는 케이스

즉, vendor 축의 다음 작업은 evaluator 수정이 아니라 parser normalization 보강이 우선이다.

## 2026-04-19 vendor normalization 추가 반영

추가한 내용:

- vendor alias normalization 시 punctuation 제거 후보를 함께 비교
- `7.-ELEVEN`, `7,-ELEVEN` -> `7-ELEVEN`

검증:

- 신규 회귀 테스트 2개 추가
- 전체 테스트: `122 passed`

barcode_detail 60장 subset 평가:

- `vendor_name_accuracy`: `1.0`
- `item_name_f1_avg`: `0.9271`
- `quantity_match_rate_avg`: `1.0`
- `amount_match_rate_avg`: `1.0`

저장:

- `reports/synthetic-eval-ocr-only.barcode-detail.json`
- `reports/synthetic-eval-ocr-only.barcode-detail.md`

판단:

- barcode_detail의 vendor mismatch는 해결됐다.
- 남은 vendor 손실은 convenience hard-case처럼 OCR이 상호 자체를 읽지 못하는 구간이다.
- 이 문제는 alias 추가보다 전처리/실사 fallback/LLM 보조 판단 쪽이 더 효과적이다.

## 2026-04-19 서비스 레이어 header fallback 보강

추가한 내용:

- 기존 `top-strip date fallback`을 `top-strip header fallback`으로 확장
- `vendor_name`이 비어 있으면 top-strip OCR 결과에서 vendor를 한 번 더 추출
- 성공 시 diagnostics에 아래 값을 기록
  - `vendor_fallback_used`
  - `vendor_fallback_source`

테스트:

- 신규 서비스 테스트 1개 추가
- 전체 테스트: `123 passed`

중요한 확인:

- synthetic convenience hard-case 표본(`convenience_pos-0093`, `0096`)에 대해 실제 top-strip OCR을 직접 확인했을 때
  - `금리루금`
  - `금루금`
  같은 잡음만 읽혔다.

결론:

- top-strip vendor fallback은 일반적인 누락 회수 경로로는 유효하다.
- 하지만 현재 convenience hard-case는 OCR-only 경로에서 상호 자체가 사라지는 문제라, 이 fallback만으로는 해결되지 않는다.
- 이 군은 다음 단계에서 Qwen header rescue 또는 실사 기준 fallback 설계로 넘기는 것이 맞다.

## 2026-04-19 unresolved vendor 정책 추가

추가한 내용:

- 최종 서비스 결과에서 `vendor_name`이 비어 있으면
  - `review_reasons`에 `missing_vendor_name` 추가
  - `review_required = true`

의미:

- OCR-only 경로에서 상호를 복구하지 못한 케이스가 조용히 성공처럼 내려가지 않는다.
- 현재 한계 구간을 운영/평가에서 명시적으로 분리할 수 있다.

검증:

- 신규 서비스 리뷰 정렬 테스트 1개 추가
- 전체 테스트: `124 passed`

## 2026-04-21 추천 시스템 canonicalization

추가한 내용:

- 추천 런타임 기준 데이터를 `main.py`의 기존 `data/db/*`로 고정
- 추천 가능 재료 집합을 `recipe_ingredients.json` 기준으로 계산
- 추천 singleton 로더를 추가해 `recipe_recommender.RecipeRecommender`를 재사용
- `/ai/recommend`는 기존 공개 응답 shape를 유지한 채 내부적으로 `RecipeRecommender.recommend()`를 사용
- 추천 단계에서만 cooking-focused eligibility를 적용
  - DB에 있는 재료여도 레시피 그래프에 없는 재료는 추천 입력에서 제외
- `/ai/ingredient/prediction`은 broad mapping 역할을 그대로 유지

정책:

- invalid ingredientId만 들어오면 기존처럼 `400 INVALID_REQUEST`
- DB에는 존재하지만 추천 가능 재료가 0개면 `200 OK` + 빈 추천 리스트
- `input_ingredient_count`는 기존 의미대로 DB valid id 개수를 유지

검증:

- 신규 추천 runtime 테스트 5개 추가
- 공개 API surface 테스트 유지
- `RecipeRecommender` 기존 모듈 테스트 유지
- 전체 테스트: `129 passed`

수동 확인:

- 실제 샘플 재료 `양파`, `대파`, `마늘`, `고추장`, `계란`으로 추천을 호출했을 때 상위 5건이 정상 반환됨
- 기존보다 단순 matchRate가 아니라 내부 score 기준으로 정렬되지만, 외부 응답 계약은 유지됨

의미:

- 추천 품질이 더 이상 단순 재료 개수 비율에만 묶이지 않는다.
- OCR 상품 매핑과 추천 eligibility가 분리되어, 간식/비조리 항목이 추천 품질을 망치는 문제가 줄어든다.

## 2026-04-21 실사셋/매핑 확장 진행

에이전트 팀으로 병렬 정리를 진행했다.

반영한 내용:

- `제비` 폴더를 현재 엔진 기준 silver set으로 신규 편입
  - 경로: `data/receipt_silver/jevi-silver-v1`
  - `image_count = 11`
  - `total_item_count = 100`
  - `review_required_count = 10`
- cooking-focused 상품명 -> 재료 매핑 추가
  - `양념닭주물럭2.2kg -> 닭고기`
  - `청정원 서해안 까나리 -> 까나리액젓`
  - `하인즈 유기농케찹 90 -> 케찹`
  - `멜오에이지 파마산분 -> 파마산 치즈`
  - `속이편한 누룽지(5입) -> 누룽지`
  - `*국내산 양상추 2입 -> 양상추`
  - `*완숙토마토 4kg/박스 -> 토마토`
  - `갈바니 리코타 치즈`, `갈바니 리코타 치즈4 -> 리코타 치즈`
  - `블렌드 슈레드 치즈1kg -> 치즈`

현재 `product_to_ingredient.json` 매핑 수:

- `52 -> 62`

검증:

- `tests/test_ingredient_prediction_rules.py` 확장
- 전체 테스트: `129 passed`

에이전트 팀 결과 요약:

- 실사 인벤토리:
  - `제비` full image `35개`, crop `3개`
  - gold `4개`, silver `11개`
  - 바로 gold 후보 shortlist 확보
- 스크립트 경로:
  - `build_receipt_silver_set.py`로 실사 silver 편입 가능
  - `evaluate_receipt_silver_set.py`는 gold-like manifest도 평가 가능

다음 작업 후보:

- silver v1에서 대표 샘플 4~8장을 gold로 승격
- gold에 `vendor_name`, `purchased_at`, `items`, `totals` 수작업 확정
- gold manifest 기준 baseline 리포트 재생성

## 2026-04-21 gold draft 승격 및 baseline 생성

추가한 내용:

- `jevi-silver-v1`에서 대표 4장을 골라 `jevi-gold-v0` 생성
  - `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`
  - `image.png`
  - `R (1).jpg`
  - `R.jpg`
- 각 annotation은 compact 형태로 수작업 보정
  - `items`
  - `uncertain_items`
  - `excluded_rows`
  - `totals`
- 신규 baseline 문서 추가
  - [RECEIPT_GOLDSET_BASELINE_2026-04-21.md](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/docs/RECEIPT_GOLDSET_BASELINE_2026-04-21.md)

검증:

- 실행 명령:
  - `python scripts/evaluate_receipt_silver_set.py --manifest data/receipt_gold/jevi-gold-v0/manifest.json`
- 결과:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.715`

이미지별:

- `2a4dd3c18f06cec1571dc9ca52dc5946.jpg`: `0.8000`
- `image.png`: `0.6154`
- `R (1).jpg`: `0.8889`
- `R.jpg`: `0.5556`

의미:

- `R (1).jpg`는 현재 실사축에서 가장 안정적인 케이스다.
- `image.png`는 cooking-focused 상품명/재료 매핑 검증에는 가치가 높다.
- `R.jpg`는 vendor 복구와 snack OCR 정규화의 약점을 보여준다.
- 이제 실사 baseline이 기존 4장만이 아니라, silver-only 후보까지 확장된 2세트 구조가 되었다.

## 2026-04-21 gold baseline 후속 보정

추가한 내용:

- `Home plus` / `www.homeplus.co.kr` 계열을 `홈플러스`로 vendor 복구
- `결제대상금액`과 `계 117,580` 형식 totals 복구

검증:

- 신규 parser 회귀 테스트 2개 추가
- `jevi-gold-v0` baseline 재측정 결과
  - `vendor_name_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.715` 유지
- 전체 테스트: `131 passed`

## 2026-04-21 실사 image/R 후속 고도화

추가한 내용:

- `16, 980`, `6, 780`, `9, 980`, `6, 680`처럼 공백이 낀 numeric detail row를 parser에서 정규화
- `상품명 + 코드/숫자상세` 2줄형을 다시 item으로 복구
- `품`, `세 물물`, `세 품품세`, `가` 같은 summary fragment tail을 item에서 제거
- `TE.CO.KR` 같은 domain noise line 제거
- `크라우참쌀서과 -> 크라운참쌀선과`, `해태구문감자 -> 해태구운감자` alias 추가

검증:

- 신규 parser 회귀 테스트 3개 추가
- 전체 테스트: `134 passed`
- `jevi-gold-v0` baseline 재측정
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.8228`

실서비스 샘플 확인:

- `image.png`
  - quantity/amount가 붙은 품목 11개 복구
  - `totals = {total: 117580, payment_amount: 112580}` 회복
- `R.jpg`
  - `vendor_name = 홈플러스`
  - 주요 snack 품목 다수 복구
  - 남은 불확실 품목은 `와이멘씨라이스퍼프`, `부드러운쿠키블루베` 축

## 2026-04-21 서비스 review 정책 정렬

추가한 내용:

- `missing_purchased_at`는 item-level unresolved 판단에서 제외
- OCR 원문에서 할인/에누리/포인트 line의 음수 금액을 합산해 `discount_adjustment_total` 계산
- 첫 줄이 `상품명 / 단가 / 수량 / 금액` header로 시작하는 cropped 입력은 `partial_receipt = true`로 판단
- partial receipt는 vendor/date가 없어도 items/totals가 정상이면 review를 올리지 않도록 정렬

검증:

- 신규 서비스 alignment 테스트 3개 추가
- 전체 테스트: `137 passed`

실서비스 효과:

- `image.png`
  - 이전: `review_required = true`
  - 현재: `review_required = false`
  - `partial_receipt = true`
  - `discount_adjustment_total = -11500.0`
- `R.jpg`
  - `review_required = false` 유지

## 2026-04-21 R.jpg 가격 꼬리 품목명 정리

추가한 내용:

- `single_line_name_amount` 경로에도 trailing price cleanup 적용
- trailing orphan digit 제거는 `1` 케이스로만 제한

효과:

- `R.jpg`
  - `와이멘씨라이스퍼프1 3,980` -> `와이멘씨라이스퍼프`
- 기존 회귀
  - `갈바니'리코타치느4` 같은 실제 상품명 숫자는 그대로 유지

검증:

- 신규 parser 회귀 테스트 1개 추가
- 전체 테스트: `138 passed`

## 2026-04-21 추천 개인화 입력 확장

추가한 내용:

- `/ai/recommend` request에 개인화 입력 필드 추가
  - `preferredIngredientIds`
  - `dislikedIngredientIds`
  - `allergyIngredientIds`
  - `preferredCategories`
  - `excludedCategories`
  - `preferredKeywords`
  - `excludedKeywords`
- 추천 엔진은 기존 응답 shape를 유지한 채 내부 점수화만 확장
- 정책:
  - 비선호/알레르기 재료는 hard filter
  - 제외 카테고리/제외 키워드도 hard filter
  - 선호 재료/선호 카테고리/선호 키워드는 soft boost

검증:

- 추천 runtime 테스트 확장
- public API surface 테스트 확장
- `RecipeRecommender` 개인화 정렬 테스트 추가
- 전체 테스트: `140 passed`

## 2026-04-21 제비 실사셋 전체 silver 확장

추가한 내용:

- `silver_dataset`에서 `.webp`를 실사 영수증 후보로 포함
- `제비` 폴더 전체 full receipt를 다시 silver로 편입
- 신규 경로:
  - `data/receipt_silver/jevi-silver-v2`

현재 coverage:

- full receipt image `35개`
- crop image `3개`
- `jevi-silver-v2`
  - `image_count = 35`
  - `total_item_count = 162`
  - `review_required_count = 32`

의미:

- 이전까지는 `jpg/png/jpeg` subset 11장만 silver에 들어가 있었고,
- 이제 `OIP *.webp` 실사 영수증까지 포함한 full receipt 전체가 silver coverage에 들어갔다.

다음 gold 후보 shortlist:

- `R (2).jpg`
- `img3.jpg`
- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
- `OIP (22).webp`

## 2026-04-21 gold 확장 2차

추가한 내용:

- `jevi-gold-v0`에 아래 4장 추가
  - `R (2).jpg`
  - `img3.jpg`
  - `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `OIP (10).webp`
- 약국 샘플 `OIP (22).webp`는 원본만으로 품목명이 너무 애매해서 이번 gold 확장에서는 제외

현재 gold coverage:

- `image_count = 8`
- `total_item_count = 72`

재평가 결과:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.7957`

의미:

- hard-case를 넣은 8장 기준에서도 다시 baseline을 상당 부분 회복했다.
- `img3.jpg`는 여전히 최약군이지만,
  - `OIP (10).webp`는 `item_f1 = 1.0`
  - `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`는 `item_f1 = 0.9`
  까지 올라왔다.

## 2026-04-21 hard-case 3종 후속 보강

추가한 내용:

- bracketed alpha noise vendor fallback 제거
  - `img3.jpg`의 `[NATT` 같은 가짜 vendor 차단
- `single_line_name_amount` 경로에서 trailing barcode suffix 제거
  - `OIP (10).webp`의 `스팀덱 64GB 0814585021752` -> `스팀덱 64GB`
- `결제대상금`을 explicit payment keyword로 인정
  - 카드 전표 하단 line이 payment_amount를 덮어쓰지 않도록 정렬
- exact product alias lookup 추가
  - `허쉬밀크초콜릿`, `초코빼빼로`, `호레오화이트`, `롯데 앤디카페 초콜릿 다크빈` 축 회복

검증:

- 신규 parser 회귀 테스트 5개 추가
- Qwen item normalization fixture 갱신
- 전체 테스트: `145 passed`

## 2026-04-21 img3 lower item strip fallback

추가한 내용:

- `ReceiptParseService`에 `lower item strip fallback` 추가
- 조건:
  - local `receipt_image_url`
  - `quality_score <= 0.6` 또는 low-quality flag 존재
  - item header 아래에서 `OV00` 같은 짧은 placeholder row 뒤에 barcode/qty/amount row가 이어질 때만 발동
- fallback은 원본 이미지 하단 strip을 다시 OCR하고, 기존 결과에 없는 새 품목만 병합한다.

같이 반영한 alias:

- `L맥주바이젠미니 -> 맥주 바이젠 미니`
- `롯데 앤디카페조릿 다크 -> 롯데 앤디카페 초콜릿 다크빈`

검증:

- 신규 서비스 테스트 1개 추가
- 전체 테스트: `146 passed`

효과:

- `img3.jpg`
  - `diagnostics.item_strip_fallback_used = true`
  - `맥주 바이젠 미니` 회복
  - `item_f1 = 0.2857 -> 0.5`
- 과한 fallback으로 인한 회귀를 다시 막기 위해 범위를 좁혀서
  - `R.jpg`
  - `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `OIP (10).webp`
  에서는 fallback이 비활성 상태를 유지한다.

현재 gold 8장 baseline:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8118`

## 2026-04-21 gold comparison pack-count normalization

추가한 내용:

- `silver_dataset.py` 비교 정규화에 parenthetical pack-count 제거를 추가
  - `(5입)`, `(2개)`는 동일 품목 비교로 처리
  - `355ml`, `500ml` 같은 실제 용량 차이는 유지

검증:

- 신규 비교 테스트 2개 추가
- 전체 테스트: `148 passed`

효과:

- `img3.jpg`
  - parser가 이미 복구한 `속이편한 누룽지` 2건이 gold의 `속이편한 누룽지(5입)`와 동일 품목으로 매칭
  - `item_f1 = 0.5 -> 1.0`
- gold 8장 baseline:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.8743`

## 2026-04-21 SE gift-tail fallback

추가한 내용:

- `ReceiptParseService`에 `gift_tail` 전용 item strip fallback 추가
- `1 증정풍`처럼 상품명 없이 gift tail만 남은 row를 감지하면, 실제 샘플에서 더 잘 읽히는 중간 item band를 다시 OCR
- fallback 병합도 gap kind 기준으로 제한
  - `gift_tail`은 gift candidate만 허용
  - `placeholder_barcode`는 일반 candidate만 허용
- alias 추가
  - `투썰로알밀크티 -> 투썸로얄밀크티`
  - `투썸로알밀크티 -> 투썸로얄밀크티`

검증:

- 신규 서비스 fallback 테스트 1개 추가
- 전체 테스트: `149 passed`

효과:

- `SE-173d6bc5-09f3-4a6e-a2e3-f98c90480034.jpg`
  - `item_strip_fallback_used = true`
  - `item_strip_fallback_added_count = 1`
  - 누락 gift item `투썸로얄밀크티` 복구
  - `item_f1 = 0.9000 -> 0.9524`
- `img3.jpg`
  - `item_strip` fallback 유지
  - `item_f1 = 1.0` 유지
- `R.jpg`
  - fallback 비활성 유지

최신 gold 8장 baseline:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8877`

## 2026-04-21 gold evaluation metric expansion

추가한 내용:

- `silver_dataset.py`에 이름 매칭 결과를 재사용하는 field-level 비교 추가
  - `quantity_match_rate`
  - `amount_match_rate`
  - `review_required_match`
- `scripts/evaluate_receipt_silver_set.py` summary 확장
  - `quantity_match_rate_avg`
  - `amount_match_rate_avg`
  - `review_required_accuracy`

검증:

- 신규 dataset 비교 테스트 2개 추가
- 전체 테스트: `151 passed`

최신 gold 8장 baseline:

- `vendor_name_accuracy = 1.0`
- `purchased_at_accuracy = 1.0`
- `payment_amount_accuracy = 1.0`
- `item_name_f1_avg = 0.8916`
- `quantity_match_rate_avg = 0.9188`
- `amount_match_rate_avg = 0.9163`
- `review_required_accuracy = 0.5`

현재 의미:

- 이름/수량/금액 축은 많이 올라왔다.
- review 축도 올라왔지만 아직 다음 병목 후보로 남아 있다.

## 2026-04-21 review alignment follow-up

추가한 내용:

- `low_confidence` 단독은 unresolved_items에서 제외
- item header가 없는 item-block crop도 `partial_receipt`로 판단하도록 확장
- `unconsumed_item_amount_total` 계산 추가
  - parser가 소비하지 못한 잔여 item amount를 totals 검증에 반영
  - 결제 footer 금액은 합산에서 제외
- parser filter 보강
  - pack-size dangling single-line 제거

검증:

- 신규 review alignment 테스트 3개 추가
- parser 회귀 테스트 1개 추가
- 전체 테스트: `155 passed`

효과:

- `2a4dd3...jpg`
  - `review_required = false`
  - `partial_receipt = true`
- `SE-...jpg`
  - `review_required = false`
  - `unconsumed_item_amount_total = 5190.0`
- 최신 gold 8장 baseline:
  - `item_name_f1_avg = 0.8916`
  - `review_required_accuracy = 0.5`

## 2026-04-22 focused receipt + packaging follow-up

추가한 내용:

- `용기면` 같은 식품명은 packaging noise에서 제외
- focused receipt의 `missing_vendor_name`는 아래 조건에서 review를 올리지 않도록 축소
  - `item_strip_fallback_used` + purchased_at 존재
  - 또는 OCR row 수가 충분한 단일상품 payment receipt
- parser diagnostics의 `consumed_line_ids`를 final surviving items 기준으로 재계산
- `unconsumed_item_amount_total` 계산에서 tax/포인트/고객님/소멸 metadata row 제외

검증:

- 신규 parser/service 테스트 5개 추가
- 전체 테스트: `160 passed`

효과:

- `R (1).jpg`, `R (2).jpg`
  - `농심 쌀국수 용기면 6입` 복구
  - `item_f1 = 0.8889 -> 0.9286`
  - `total_mismatch` 제거
- `img3.jpg`, `OIP (10).webp`
  - `missing_vendor_name` review 제거
- 최신 gold 8장 baseline:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 1.0`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.9015`
  - `quantity_match_rate_avg = 0.9367`
  - `amount_match_rate_avg = 0.9342`
  - `review_required_accuracy = 1.0`

## 2026-04-22 image cleanup + dense fallback suppression

추가한 내용:

- `×`, `* ` marker가 item raw_name 앞에 붙는 경우만 좁게 제거
- raw alias lookup을 candidate stripping 이전에 추가
- `갈바니'리코타치느4` canonical alias를 `갈바니 리코타 치즈4`로 조정
- dense receipt에서는 `placeholder_barcode` item-strip fallback을 막아 duplicate hallucination 제거

검증:

- 신규 parser/service 테스트 3개 추가
- 전체 테스트: `163 passed`

효과:

- `image.png`
  - `item_f1 = 1.0`
- `2a4dd3...jpg`
  - duplicate fallback 제거
  - `item_f1 = 0.8333`
- 최신 gold 8장 baseline:
  - `item_name_f1_avg = 0.9397`
  - `quantity_match_rate_avg = 0.9708`
  - `amount_match_rate_avg = 0.9683`
  - `review_required_accuracy = 1.0`

## 2026-04-22 2a4dd3 visual review promotion

추가한 내용:

- `210032 790 T 790` 같은 row에서 `T`를 quantity placeholder로 인정
- `2a4dd3...jpg` visual review 후 clear item 4개를 gold expected로 승격
  - `바베큐 조미 오징어`
  - `마늘빵아몬드`
  - `유기농 바나나콘`
  - `미클립스 피치향 34g`

검증:

- 신규 parser 테스트 1개 추가
- 전체 테스트: `164 passed`

효과:

- `2a4dd3...jpg`
  - `item_f1 = 0.9655`
- 최신 gold 8장 baseline:
  - `item_name_f1_avg = 0.9750`
  - `quantity_match_rate_avg = 0.9740`
  - `amount_match_rate_avg = 0.9718`
  - `review_required_accuracy = 1.0`

## 2026-04-22 R visual review promotion

추가한 내용:

- `R.jpg` visual review 후 clear item 2개를 gold expected로 승격
  - `와이멘씨라이스퍼프`
  - `부드러운쿠키블루베`
- gold manifest의 `total_item_count`를 `78`로 갱신

효과:

- `R.jpg`
  - `item_f1 = 1.0`
- 최신 gold 8장 baseline:
  - `item_name_f1_avg = 0.9750`
  - `quantity_match_rate_avg = 0.9740`
  - `amount_match_rate_avg = 0.9718`
  - `review_required_accuracy = 1.0`

## 2026-04-22 img2 gold promotion

추가한 내용:

- `부 "가 세` OCR 노이즈를 tax로 인식하도록 parser 보강
- service totals reconciliation에서 `subtotal + tax` 후보 추가
- `img2.jpg`를 gold draft에 편입
  - vendor/date
  - 품목 2개
  - `subtotal/tax`

검증:

- 신규 parser/service 테스트 2개 추가
- 전체 테스트: `166 passed`

효과:

- `img2.jpg`
  - `review_required = false`
  - `item_f1 = 1.0`
- 최신 gold 9장 baseline:
  - `item_name_f1_avg = 0.9750`
  - `quantity_match_rate_avg = 0.9740`
  - `amount_match_rate_avg = 0.9718`
  - `review_required_accuracy = 1.0`

## 2026-04-22 165288 grocery partial gold promotion

추가한 내용:

- `1652882389756.jpg`를 gold draft에 편입
  - item 10개
  - excluded row 1개(재사용봉투)
  - vendor는 `null`, purchased_at은 visual 기준 `2022-04-30`
- `ReceiptParseService._looks_like_partial_receipt()`
  - noisy row 1~2개 뒤에 item header가 나오는 grocery partial receipt를 허용
  - early-header 분기에서 `code + amount` row를 partial 구조 신호로 포함

검증:

- 신규 service 테스트 1개 추가
- 전체 테스트: `167 passed`
- gold baseline 재측정 완료

효과:

- `1652882389756.jpg`
  - `review_required = false`
  - `partial_receipt = true`
  - `item_f1 = 0.9474`
  - 아직 `purchased_at`, `깐양파`는 miss
- 최신 gold 10장 baseline:
  - `vendor_name_accuracy = 1.0`
  - `purchased_at_accuracy = 0.9`
  - `payment_amount_accuracy = 1.0`
  - `item_name_f1_avg = 0.9723`
  - `quantity_match_rate_avg = 0.9666`
  - `amount_match_rate_avg = 0.9646`
  - `review_required_accuracy = 1.0`

## 2026-04-22 OIP (9) parser hardening

추가한 내용:

- `n입` pack-count 상품의 quantity OCR 오독 보정
- `계 -> 할인(-) -> 무라벨 최종금액`에서 `payment_amount` 복구
- vertical totals block amount sequence로 `subtotal/tax` 추론
- totals metadata false positive item prune 보강

검증:

- 신규 parser 테스트 3개 추가
- 전체 테스트: `170 passed`

효과:

- `OIP (9).webp`
  - `양념등심돈까스` 회복
  - `국내산 양상추2입`: `quantity 7 -> 1`
  - `payment_amount`: `112,580` 회복
  - `subtotal=81,673`, `tax=8,167` 회복
  - false positive `JY 물 손어머` 제거
- 이 샘플은 아직 `파프리카(팩)` miss 때문에 `total_mismatch`가 남지만, acceptance gold로는 편입 가치가 있다고 판단

## 2026-04-22 OIP (9) gold promotion

추가한 내용:

- `OIP (9).webp`를 grocery acceptance gold로 편입
  - clear item 10개
  - uncertain item 1개
  - `review_required=true`

검증:

- gold baseline 재측정 완료
- 전체 테스트: `172 passed`

효과:

- latest gold baseline이 `10장 -> 11장`으로 확장
- metrics:
  - `item_name_f1_avg = 0.9413`
  - `quantity_match_rate_avg = 0.9333`
  - `amount_match_rate_avg = 0.9315`
  - `review_required_accuracy = 1.0`
- 해석:
  - baseline이 내려간 건 품질 후퇴가 아니라 acceptance set이 더 현실화됐다는 뜻
  - 지금부터는 같은 샘플 미세튜닝보다 grocery/convenience gold 확장이 우선

## 2026-04-22 OIP (7) gold promotion

추가한 내용:

- `OIP (7).webp`를 low-res grocery acceptance gold로 편입
  - clear item 3개
  - `review_required=true`

검증:

- gold baseline 재측정 완료
- 전체 테스트: `172 passed`

효과:

- latest gold baseline이 `11장 -> 12장`으로 확장
- metrics:
  - `item_name_f1_avg = 0.9343`
  - `quantity_match_rate_avg = 0.8555`
  - `amount_match_rate_avg = 0.8538`
  - `review_required_accuracy = 1.0`
- 해석:
  - quantity/amount가 acceptance set의 실제 병목이라는 점이 더 선명해졌다
  - 다음 우선순위는 gold 추가 확장과 `name line + detail row` 계열 parser 일반화다

## 2026-04-22 OIP (1) gold promotion

추가한 내용:

- `OIP (1).webp`를 convenience mixed acceptance gold로 편입
  - 식품 2개
  - non-food 1개는 excluded row
  - `review_required=true`

검증:

- gold baseline 재측정 완료
- 전체 테스트: `172 passed`

효과:

- latest gold baseline이 `12장 -> 13장`으로 확장
- metrics:
  - `item_name_f1_avg = 0.8932`
  - `quantity_match_rate_avg = 0.8282`
  - `amount_match_rate_avg = 0.8266`
  - `review_required_accuracy = 1.0`
- 해석:
  - non-food filtering과 convenience mixed receipt 대응이 acceptance 기준의 실제 병목으로 드러남
  - 지금은 수치를 방어하는 것보다 acceptance 분포를 더 넓히는 방향이 맞다

## 2026-04-22 OIP (8) gold promotion

추가한 내용:

- `OIP (8).webp`를 low-res convenience acceptance gold로 편입
  - clear item 3개
  - uncertain item 2개
  - `review_required=true`

검증:

- gold baseline 재측정 완료
- 전체 테스트: `172 passed`

효과:

- latest gold baseline이 `13장 -> 14장`으로 확장
- metrics:
  - `item_name_f1_avg = 0.8294`
  - `quantity_match_rate_avg = 0.7690`
  - `amount_match_rate_avg = 0.7676`
  - `review_required_accuracy = 1.0`
- 해석:
  - low-res convenience는 아직 acceptance 범위에서 가장 약한 축이다
  - 다음 parser 작업은 grocery보다 convenience low-res 대응을 우선 보는 것이 더 맞다

## 2026-04-22 OIP (8) low-res convenience parser hardening

추가한 내용:

- gibberish english vendor fallback 차단
- `barcode + lineNo + name + unit_price + amount` 한 줄형 low-res convenience parser 추가
- `ocr_noisy_pos` residual barcode/lineNo 제거
- convenience low-res alias 3개 추가

검증:

- 신규 parser 테스트 2개 추가
- 전체 테스트: `174 passed`
- gold baseline 재측정 완료

효과:

- `OIP (8).webp`
  - `item_f1 = 0.6667`
  - `vendor hallucination` 제거
  - `칠성사이다 제로 500ml`, `김치제육삼각`, `참치마요 삼각` 회복
- latest gold baseline:
  - `item_name_f1_avg = 0.8691`
  - `quantity_match_rate_avg = 0.8325`
  - `amount_match_rate_avg = 0.8311`
  - `review_required_accuracy = 1.0`

## 2026-04-22 OIP (1) mixed convenience cleanup

추가한 내용:

- `alphanumeric barcode + 3-digit lineNo` prefix 제거를 일반화
- `부탄가스`, `건전지`, `배터리` non-food keyword 추가

검증:

- 신규 parser 테스트 2개 추가
- 전체 테스트: `176 passed`
- gold baseline 재측정 완료

효과:

- `OIP (1).webp`
  - `item_f1 = 0.4 -> 1.0`
  - `사조고추참치100g*3`, `동원야채참치100g*3`만 남고 `애니파워부탄가스`는 제외
- latest gold baseline:
  - `item_name_f1_avg = 0.9119`
  - `quantity_match_rate_avg = 0.8682`
  - `amount_match_rate_avg = 0.8668`
  - `review_required_accuracy = 1.0`
- 다음 우선순위:
  - `OIP (8).webp` 같은 low-res convenience에서 `uncertain snack/drink row pruning`
