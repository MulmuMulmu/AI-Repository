# Recommend API Specification

> 프로젝트: 개인화 레시피 추천 컨테이너  
> 서버: FastAPI  
> Base URL: `http://{RECOMMEND_SERVER_HOST}:8000`

이 문서는 추천 컨테이너의 공개 API를 정리한다.

## 공개 API

| Method | Endpoint | 설명 |
|---|---|---|
| `POST` | `/ai/ingredient/recommondation` | 백엔드 후보 레시피 기반 벡터 추천 |

> 주의: 경로명은 백엔드 계약에 맞춰 `recommondation` 철자를 그대로 사용한다.

## `POST /ai/ingredient/recommondation`

백엔드가 사용자의 보유 재료, 선호/비선호 재료, 후보 레시피 목록을 넘기면 추천 컨테이너가 후보 안에서 점수화하고 정렬한다.

### Request

```json
{
  "userIngredient": {
    "ingredients": ["김치"],
    "preferIngredients": ["고등어", "소고기"],
    "dispreferIngredients": ["샐러드", "오이"],
    "IngredientRatio": 0.5
  },
  "candidates": [
    {
      "recipe_id": "exampleUUID1",
      "title": "돼지고기 김치찌개",
      "ingredients": ["김치", "돼지고기", "두부", "대파", "고춧가루"]
    },
    {
      "recipe_id": "exampleUUID2",
      "title": "김치볶음밥",
      "ingredients": ["김치", "밥", "스팸", "양파", "고추장"]
    }
  ]
}
```

### Request Fields

| Field | Type | 설명 |
|---|---|---|
| `userIngredient.ingredients` | `string[]` | 사용자가 보유한 재료명 |
| `userIngredient.preferIngredients` | `string[]` | 선호 재료명. 점수에 soft boost로 반영 |
| `userIngredient.dispreferIngredients` | `string[]` | 비선호 재료명. 제목/재료에 포함되면 추천 후보에서 제외 |
| `userIngredient.IngredientRatio` | `number` | 후보 레시피 재료 중 보유 재료가 차지해야 하는 최소 비율. 기본 정책은 `0.5` |
| `candidates[].recipe_id` | `string` | 백엔드 레시피 ID |
| `candidates[].title` | `string` | 레시피명 |
| `candidates[].ingredients` | `string[]` | 해당 레시피에 필요한 재료명 |

### Recommendation Rule

- 후보 레시피 중 `matched / recipe.ingredients.length >= IngredientRatio`인 항목만 추천한다.
- 비선호 재료가 제목 또는 재료에 포함된 후보는 제외한다.
- 점수는 보유 재료 매칭률, cosine 유사도, 선호 재료 boost를 조합한다.
- 결과는 `score` 내림차순으로 정렬한다.

### Success Response

```json
{
  "success": true,
  "data": {
    "recommendations": [
      {
        "recipeId": "exampleUUID1",
        "title": "돼지고기 김치찌개",
        "score": 0.92,
        "match_details": {
          "matched": ["김치", "삼겹살"],
          "missing": ["두부", "대파", "고춧가루"]
        }
      },
      {
        "recipeId": "exampleUUID2",
        "title": "김치볶음밥",
        "score": 0.78,
        "match_details": {
          "matched": ["김치", "양파"],
          "missing": ["밥", "스팸", "고추장"]
        }
      }
    ]
  }
}
```

### Error Response

추천 처리 중 서버 내부 오류가 발생하면 아래 형식을 사용한다.

```json
{
  "success": false,
  "code": "AI500",
  "result": "레시피를 추천할 수 없습니다."
}
```
