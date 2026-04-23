# Recommend API Specification

> 프로젝트: 개인화 레시피 추천 컨테이너  
> 서버: FastAPI  
> Base URL: `http://{RECOMMEND_SERVER_HOST}:8000`

이 문서는 추천 컨테이너의 공개 API를 정리한다.

## 공개 API

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/recommend` | 벡터 기반 레시피 추천 |

## `POST /recommend`

입력 핵심:

- `ingredientIds`
- `topK`
- `minCoverageRatio`
- `preferredIngredientIds`
- `dislikedIngredientIds`
- `allergyIngredientIds`
- `preferredCategories`
- `excludedCategories`
- `preferredKeywords`
- `excludedKeywords`

현재 추천 원칙:

- 레시피 재료를 모두 가지고 있거나 절반 이상 가지고 있으면 후보
- 기본 필터는 `coverageRatio >= 0.5`
- cosine similarity 기반 정렬
- 알레르기/비선호/제외 카테고리는 hard filter
- 선호 재료/카테고리/키워드는 soft boost

응답 핵심:

- `recommendations`
- `totalCount`
- `inputIngredientCount`

각 추천 항목:

- `recipeId`
- `name`
- `category`
- `imageUrl`
- `score`
- `coverageRatio`
- `matchedIngredients`
- `missingIngredients`
- `totalIngredientCount`
