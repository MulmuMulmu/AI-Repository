# OCR/추천 서비스 분리 및 벡터 추천 전환 설계

## 목표

현재 단일 AI 서버에 섞여 있는 기능을 아래 두 컨테이너로 분리한다.

1. OCR/Qwen 컨테이너
2. 추천 컨테이너

동시에 추천 엔진은 기존 규칙 기반 가중치 점수화에서  
**거리/벡터 기반 추천**으로 전환한다.

---

## 현재 문제

현재 [main.py](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/main.py)는 아래 기능을 한 앱에서 모두 처리한다.

- 영수증 OCR
- 소비기한 계산
- 레시피 추천
- 레시피 상세 조회
- 재료 검색

이 구조의 문제:

- OCR/Qwen과 추천은 리소스 성격이 다르다.
- OCR/Qwen은 추론 중심이고, 추천은 벡터 계산/데이터 조회 중심이다.
- 컨테이너를 따로 배포하고 확장하기 어렵다.
- 현재 백엔드 요구사항과 맞지 않는다.

---

## 요구사항 해석

이번 변경의 명확한 목표는 아래다.

### 유지

- `/ai/ocr/analyze`
- `/ai/ingredient/prediction`

### 제거

- `/ai/recommend`
- `/ai/recipes/{recipe_id}`
- `/ai/ingredients/search`

### 새 구조

- OCR/Qwen 컨테이너
  - OCR, 소비기한 계산 담당
- 추천 컨테이너
  - 추천 전용 API만 담당

상품명 정규화와 `ingredientId` 매핑은 백엔드 재료 DB 기준으로 처리한다. 별도 상품명-재료 매칭 엔드포인트는 공개 AI API 계약에서 제외한다.

---

## 접근안 비교

### 안 1. 한 레포, 두 FastAPI 앱, 두 컨테이너

- 같은 레포 안에서 OCR 앱과 추천 앱을 분리
- Docker target/entrypoint를 각각 둠

장점:

- 현재 코드 재사용이 쉽다
- 데이터 파일 공유가 쉽다
- 테스트와 배포 스크립트 수정 범위가 가장 작다

단점:

- 레포 단위로는 완전히 독립적이지 않다

### 안 2. 추천 코드를 별도 패키지로만 분리

- 단일 앱 안에 남겨두되 내부 모듈만 분리

장점:

- 구현량이 적다

단점:

- 컨테이너 분리 요구를 충족하지 못한다

### 안 3. 추천 서버를 별도 레포로 완전 분리

- 추천 앱을 새 레포로 분리

장점:

- 책임 분리가 가장 명확하다

단점:

- 지금 단계에서는 과하다
- 스키마/배포/테스트 동기화 비용이 커진다

### 추천

**안 1**이 맞다.

이유:

- 현재 요구사항을 정확히 만족한다
- 구현 난이도 대비 이득이 크다
- 기존 OCR/Qwen 경로를 안정적으로 유지할 수 있다

---

## 목표 구조

```text
AI-Repository-fresh/
├── app_ocr.py
├── app_recommend.py
├── recommendation/
│   ├── __init__.py
│   ├── vector_engine.py
│   ├── schemas.py
│   └── app.py
├── ocr_qwen/
├── data/
├── tests/
└── docker-compose.yml
```

### OCR/Qwen 앱

공개 API:

- `POST /ai/ocr/analyze`
- `POST /ai/ingredient/prediction`

선택 유지:

- 내부 운영용 라우트 (`/ai/ocr/refinement`, `/ai/sharing/check`, `/ai/quality/metrics`)

### 추천 앱

공개 API:

- `POST /recommend`

설명:

- 레시피 상세 조회와 재료 검색은 백엔드가 내부 처리
- 추천 컨테이너는 추천 결과 계산만 담당

---

## 추천 알고리즘 설계

현재 요구는:

- 레시피 재료를 모두 가지고 있거나
- 절반 이상 가지고 있으면
- 추천해주는 느낌

이 요구를 만족하는 가장 단순하고 설명 가능한 방식은  
**가중 벡터 + 코사인 유사도 + 최소 커버리지 0.5**다.

### 입력

- 사용자 보유 재료 ID 집합
- 사용자 선호/비선호/알레르기
- 레시피별 재료 ID 집합

### 벡터화

- 전체 재료 사전을 기준 축으로 사용
- 사용자 벡터: 보유 재료면 1, 아니면 0
- 레시피 벡터: 해당 재료가 필요하면 1, 아니면 0
- 선택적으로 재료 중요도 가중치 적용 가능

### 필터

추천 후보는 아래 조건을 만족해야 한다.

- 알레르기 재료 미포함
- 비선호 재료 미포함
- `coverage_ratio >= 0.5`

여기서:

`coverage_ratio = matched_ingredient_count / recipe_total_ingredient_count`

즉 **절반 이상 가진 레시피만 후보로 남긴다.**

### 점수

기본 점수:

- cosine similarity(user_vector, recipe_vector)

추가 보정:

- 선호 재료 포함 시 가산점
- 선호 카테고리 가산점
- 제외 카테고리 감점 또는 필터

### 출력

- `recipeId`
- `score`
- `coverageRatio`
- `matchedIngredients`
- `missingIngredients`

백엔드는 이 결과를 받아 최종 응답 스키마로 재포장한다.

---

## 왜 규칙 기반을 버리고 벡터 기반으로 가는가

현재 규칙 기반 추천은 설명 가능성은 좋지만,  
결국 수동 점수 설계 비중이 크다.

이번 변경에서는 사용자 요구가 명확하다.

- “재료를 절반 이상 가지고 있으면 추천”

이건 벡터/거리 기반으로 표현하는 게 더 자연스럽다.

장점:

- 구현이 단순하다
- threshold가 명확하다
- `절반 이상 보유` 조건이 직접적으로 반영된다
- 나중에 임베딩/거리 알고리즘으로 확장하기 쉽다

---

## API 계약 방향

### OCR/Qwen 컨테이너

- `POST /ai/ocr/analyze`
- `POST /ai/ingredient/prediction`

### 추천 컨테이너

- `POST /recommend`

예상 입력:

```json
{
  "ingredientIds": ["ingredient-1", "ingredient-2"],
  "preferredIngredientIds": [],
  "dislikedIngredientIds": [],
  "allergyIngredientIds": [],
  "preferredCategories": [],
  "excludedCategories": [],
  "preferredKeywords": [],
  "excludedKeywords": [],
  "topK": 10,
  "minCoverageRatio": 0.5
}
```

---

## Docker/배포 방향

### OCR/Qwen 컨테이너

- 기존 `ai-api` 계열을 OCR 앱 기준으로 재정리

### 추천 컨테이너

- 추천 앱 전용 Dockerfile target 또는 별도 entrypoint

### compose

- `ocr-api`
- `recommend-api`

즉 local/dev와 GCP 배포 둘 다  
**서비스 경계가 동일하게 보이도록** 맞춘다.

---

## 테스트 전략

1. OCR 앱에서 추천/레시피/검색 라우트 제거 테스트
2. 추천 앱에서 `/recommend` 단독 노출 테스트
3. 벡터 추천 엔진 단위 테스트
   - 100% 보유
   - 50% 이상 보유
   - 50% 미만 제외
   - 알레르기 필터
4. 기존 OCR 경로 회귀 테스트 유지

---

## 최종 판단

이 변경은 맞는 방향이다.

이유:

- 백엔드 요구사항과 일치한다
- 컨테이너 경계가 명확해진다
- 추천 알고리즘이 요구사항에 더 직접적으로 맞는다
- OCR/Qwen과 추천의 리소스/배포 성격을 분리할 수 있다

다음 단계는 이 설계를 기준으로  
구현 계획을 작성하고, 그 계획대로 앱 분리와 추천 엔진 교체를 순차적으로 진행하는 것이다.
