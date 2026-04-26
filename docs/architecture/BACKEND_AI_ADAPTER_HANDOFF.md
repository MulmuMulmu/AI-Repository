# Backend AI Adapter Handoff

## 목적

이 문서는 백엔드 담당자가 AI Cloud Run 서비스를 백엔드 공개 API에 연결할 때 필요한 역할, 계약, 구현 범위를 정리한다.

핵심 원칙:

- AI 코드를 백엔드에 복사하지 않는다.
- 백엔드는 AI Cloud Run을 HTTP로 호출한다.
- 프론트는 기존처럼 백엔드 공개 API만 호출한다.
- AI 내부 API 변경은 백엔드 adapter에서 흡수한다.

## 현재 상태

AI 레포는 두 개의 컨테이너로 분리되어 있다.

- OCR/Qwen 컨테이너: 영수증 OCR, 소비기한 예측
- 추천 컨테이너: 벡터 기반 레시피 추천

백엔드 레포에는 `/ai/*` 공개 API가 있지만, 현재 로컬 구현은 Cloud Run AI 서비스를 호출하지 않고 백엔드 내부 DB/문자열 기반 로직으로 응답한다.

따라서 제품 경로에서 실제 AI를 사용하려면 백엔드에 AI adapter/client 계층이 필요하다.

## Adapter 역할

백엔드 AI adapter는 백엔드와 AI Cloud Run 사이의 번역기다.

담당 역할:

- AI Cloud Run URL을 환경변수로 읽는다.
- 백엔드 DTO를 AI 내부 API 요청 형식으로 변환한다.
- AI 응답을 백엔드 DTO로 변환한다.
- timeout, 네트워크 실패, 4xx/5xx 응답을 백엔드 예외로 변환한다.
- 사용자 인증, DB 저장, 프론트 응답 계약은 백엔드 서비스 계층에 남긴다.

## 필요한 환경변수

```properties
OCR_AI_BASE_URL=https://mulmumu-ocr-api-xxxx.a.run.app
RECOMMEND_AI_BASE_URL=https://mulmumu-recommend-api-xxxx.a.run.app
AI_CONNECT_TIMEOUT_MS=3000
AI_READ_TIMEOUT_MS=15000
```

실제 Cloud Run URL은 배포 환경에서 주입한다. 로컬 개발에서는 `.env` 또는 `application-local.properties`에 넣는다.

## 호출 대상

### OCR 분석

AI 내부 API:

```text
POST {OCR_AI_BASE_URL}/ai/ocr/analyze
Content-Type: multipart/form-data
field: image
```

AI 응답 핵심:

```json
{
  "success": true,
  "data": {
    "purchased_at": "2026-03-11",
    "food_items": [
      {"product_name": "우유", "category": "유제품"}
    ],
    "review_required": false,
    "review_reasons": []
  }
}
```

백엔드 adapter 변환:

- `data.purchased_at` -> 백엔드 구매일 필드
- `data.food_items[].product_name` -> 백엔드 식재료 후보명
- `data.food_items[].category` -> 백엔드 카테고리 필드
- `review_required=true`이면 프론트 수동 수정 흐름으로 넘길 수 있게 백엔드 응답에 반영

주의:

- 백엔드 공개 API가 현재 JSON `image` 문자열을 받는다면 base64를 multipart 파일로 변환해야 한다.
- 가능하면 공개 API도 multipart 업로드로 정리하는 것이 운영상 더 자연스럽다.

### 상품명 정규화와 식재료 ID 매핑

이 단계는 AI Cloud Run 호출이 아니라 백엔드 내부 책임이다.

처리 기준:

- OCR 응답의 `food_items[].product_name`을 입력으로 사용한다.
- 백엔드 재료 DB 기준으로 alias/rule/exact/fuzzy 매핑을 수행한다.
- `MAPPED`만 자동 등록 후보로 쓰고, `UNMAPPED`는 사용자 수정 UI나 관리자 리뷰 대상으로 넘긴다.
- 비식품/잡화로 판정되는 항목은 `EXCLUDED`로 처리한다.

AI 레포의 내부 상품명 매칭 helper는 OCR 보조와 회귀 테스트용이며, 백엔드가 호출할 공개 API 계약이 아니다.

### 소비기한 예측

AI 내부 API:

```text
POST {OCR_AI_BASE_URL}/ai/ingredient/prediction
Content-Type: application/json
```

요청:

```json
{
  "purchaseDate": "2026-04-09",
  "ingredients": ["우유", "당근", "상추"]
}
```

응답:

```json
{
  "success": true,
  "result": {
    "purchaseDate": "2026-04-09",
    "ingredients": [
      {"ingredientName": "우유", "expirationDate": "2026-04-16"}
    ]
  }
}
```

백엔드 책임:

- 구매일 형식 검증
- OCR 상품명 정규화와 `ingredientId` 매핑
- 사용자 재고 저장
- AI 실패 시 백엔드 에러 또는 보수적 fallback 정책 결정

### 레시피 추천

AI 내부 API:

```text
POST {RECOMMEND_AI_BASE_URL}/recommend
Content-Type: application/json
```

요청:

```json
{
  "ingredientIds": ["1", "2", "3"],
  "topK": 10,
  "minCoverageRatio": 0.5,
  "preferredIngredientIds": [],
  "dislikedIngredientIds": [],
  "allergyIngredientIds": [],
  "preferredCategories": [],
  "excludedCategories": [],
  "preferredKeywords": [],
  "excludedKeywords": []
}
```

운영 기준:

- `minCoverageRatio=1.0`: 보유 재료만으로 가능한 레시피
- `minCoverageRatio=0.5`: 레시피 재료를 절반 이상 보유한 추천
- 알레르기/비선호 재료는 hard filter로 전달
- 선호 재료/카테고리/키워드는 soft boost 조건으로 전달

백엔드 adapter 변환:

- 백엔드 사용자 재고의 ingredient id를 `ingredientIds`로 변환
- 사용자 알레르기/선호/비선호 설정을 추천 요청 필드로 변환
- AI 응답의 `recipeId`, `matchedIngredients`, `missingIngredients`, `coverageRatio`를 백엔드 DTO로 변환
- 레시피 상세 메타데이터가 백엔드 DB 기준이면 `recipeId`로 백엔드 DB를 조회해 최종 응답을 보강

## 장애 처리 기준

권장 정책:

- AI 400: 백엔드 400 계열로 변환
- AI 500/503/timeout: 백엔드 502 또는 서비스 내부 에러로 변환
- OCR 품질 불확실: 실패가 아니라 `review_required=true`로 사용자 수정 흐름 전환
- 추천 실패: 빈 추천을 조용히 반환하지 말고 백엔드 로그와 에러 응답으로 드러낸다

## 백엔드 구현 범위

백엔드 담당자가 구현할 범위:

1. `OcrAiClient` 작성
2. `RecommendAiClient` 작성
3. Cloud Run URL 환경변수 추가
4. OCR 결과의 상품명 정규화/재료 DB 매핑 로직 연결
5. 기존 `AiService`의 로컬 mock/DB 추천 로직을 client 호출로 교체
6. AI 응답을 기존 백엔드 응답 DTO로 변환
7. timeout/error handling 추가
8. adapter 단위 테스트와 controller 통합 테스트 추가

AI 담당자가 제공할 범위:

1. OCR/Qwen 컨테이너 URL
2. 추천 컨테이너 URL
3. API 명세 문서
4. 요청/응답 예시
5. 테스트용 샘플 payload

## 백엔드 담당자에게 전달할 한 줄 설명

```text
백엔드 AI adapter는 프론트 공개 API를 유지한 채, 내부에서 AI Cloud Run OCR/추천 서비스를 호출하고 응답을 백엔드 DTO로 변환하는 계층입니다.
```
