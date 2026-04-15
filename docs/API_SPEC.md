# AI FastAPI 요청/응답 명세서

> **프로젝트**: 영수증 기반 식재료 인식 및 레시피 추천 시스템  
> **AI 서버**: FastAPI (Python)  
> **백엔드 서버**: Spring Boot (Java)  
> **Base URL**: `http://{AI_SERVER_HOST}:8000`

---

## 목차

1. [시스템 아키텍처](#1-시스템-아키텍처)
2. [DB 스키마 (ERD)](#2-db-스키마-erd)
3. [API 엔드포인트 목록](#3-api-엔드포인트-목록)
4. [API 상세 명세](#4-api-상세-명세)
   - 4.1 [영수증 OCR + Qwen 보정](#41-영수증-ocr--qwen-보정)
   - 4.2 [OCR 추출 상품명 → DB 재료 매칭](#42-ocr-추출-상품명--db-재료-매칭)
   - 4.3 [보유 재료 기반 레시피 추천](#43-보유-재료-기반-레시피-추천)
   - 4.4 [레시피 상세 조회](#44-레시피-상세-조회)
   - 4.5 [재료 키워드 검색](#45-재료-키워드-검색)
   - 4.6 [서비스 상태 확인 (Health Check)](#46-서비스-상태-확인-health-check)
5. [에러 응답 공통 형식](#5-에러-응답-공통-형식)
6. [전체 흐름 시퀀스](#6-전체-흐름-시퀀스)

---

## 1. 시스템 아키텍처

```
Flutter App (클라이언트)
    │
    ▼
Spring Boot (백엔드)
    │
    ├─── DB (MySQL/PostgreSQL) ◀── Recipe, Ingredient, RecipeIngredient, RecipeStep
    │
    └───▶ AI FastAPI 서버
              ├── PaddleOCR (영수증 텍스트 인식)
              ├── Qwen LLM (OCR 오타 보정 + 상품명 정리)
              └── 재료 매칭 / 레시피 추천 엔진
```

| 담당 | Spring Boot | AI FastAPI |
|------|------------|------------|
| 영수증 OCR + LLM 보정 | 이미지 전달 | **PaddleOCR + Qwen 처리** |
| 재료 매칭 | 요청 전달 | **유사도 기반 매칭** |
| 레시피 추천 | 요청 전달 | **추천 알고리즘 수행** |
| 레시피 CRUD | **JPA/DB 직접 처리** | - |
| 회원 관리 | **Spring Security** | - |

---

## 2. DB 스키마 (ERD)

### Recipe 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `recipeId` | UUID (PK) | 레시피 고유 ID |
| `name` | VARCHAR | 레시피명 |
| `category` | VARCHAR | 카테고리 (반찬, 국/찌개, 볶음류, 디저트 등) |
| `imageUrl` | VARCHAR | 레시피 이미지 URL |

### Ingredient 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `ingredientId` | UUID (PK) | 재료 고유 ID |
| `ingredientName` | VARCHAR | 재료명 |
| `category` | VARCHAR | 분류 (정육/계란, 해산물, 채소/과일, 유제품, 쌀/면/빵, 소스/조미료/오일, 가공식품, 기타) |

### RecipeIngredient 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `recipeIngredientId` | UUID (PK) | 고유 ID |
| `recipeId` | UUID (FK → Recipe) | 레시피 ID |
| `ingredientId` | UUID (FK → Ingredient) | 재료 ID |
| `amount` | FLOAT | 수량 |
| `unit` | VARCHAR | 단위 (g, ml, 개, 큰술 등) |

### RecipeStep 테이블
| 컬럼 | 타입 | 설명 |
|------|------|------|
| `recipeStepId` | UUID (PK) | 고유 ID |
| `recipeId` | UUID (FK → Recipe) | 레시피 ID |
| `stepOrder` | INT | 조리 순서 (1, 2, 3...) |
| `description` | TEXT | 조리 단계 설명 |

---

## 3. API 엔드포인트 목록

| # | Method | Endpoint | 설명 |
|---|--------|----------|------|
| 1 | `POST` | `/api/ocr/receipt` | 영수증 이미지 OCR + Qwen LLM 보정 |
| 2 | `POST` | `/api/ingredients/match` | OCR 추출 상품명 → DB Ingredient 매칭 |
| 3 | `POST` | `/api/recipes/recommend` | 보유 재료 기반 레시피 추천 |
| 4 | `GET`  | `/api/recipes/{recipeId}` | 레시피 상세 조회 (재료 + 조리 단계) |
| 5 | `GET`  | `/api/ingredients/search` | 키워드로 재료 검색 |
| 6 | `GET`  | `/api/health` | 서비스 상태 확인 |

---

## 4. API 상세 명세

### 4.1 영수증 OCR + Qwen 보정

영수증 이미지를 업로드하면 PaddleOCR로 텍스트를 인식하고, Qwen LLM이 OCR 오타를 보정하여 식품 상품명 목록을 반환합니다.

**`POST /api/ocr/receipt`**

#### Request

| 항목 | 값 |
|------|-----|
| Content-Type | `multipart/form-data` |

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `image` | File (jpg/png) | O | 영수증 이미지 파일 |
| `use_qwen` | boolean | X (기본: true) | Qwen LLM 보정 사용 여부 |

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "ocr_texts": [
      {"text": "신선설렁탕", "confidence": 0.9512},
      {"text": "깻잎", "confidence": 0.9821},
      {"text": "3,900", "confidence": 0.9134},
      {"text": "국산콩두부", "confidence": 0.8745}
    ],
    "food_items": [
      {
        "product_name": "깻잎",
        "amount_krw": 1500,
        "notes": ""
      },
      {
        "product_name": "국산콩 두부",
        "amount_krw": 3900,
        "notes": "국산콩두부 → 국산콩 두부"
      },
      {
        "product_name": "삼겹살",
        "amount_krw": 12900,
        "notes": ""
      }
    ],
    "food_count": 3,
    "model": "qwen3:latest"
  }
}
```

#### Response 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `ocr_texts` | Array | PaddleOCR 원본 인식 결과 (전체 텍스트) |
| `ocr_texts[].text` | string | 인식된 텍스트 |
| `ocr_texts[].confidence` | float | 인식 신뢰도 (0~1) |
| `food_items` | Array | Qwen 보정 후 최종 식품 목록 |
| `food_items[].product_name` | string | 보정된 상품명 |
| `food_items[].amount_krw` | int \| null | 결제 금액 (원), 불확실하면 null |
| `food_items[].notes` | string | OCR 오타 수정 내역 등 |
| `food_count` | int | 추출된 식품 개수 |
| `model` | string | 사용된 LLM 모델명 |

---

### 4.2 OCR 추출 상품명 → DB 재료 매칭

OCR에서 추출된 상품명(예: "국산콩 두부")을 DB의 `Ingredient` 테이블과 매칭하여, 가장 유사한 재료를 반환합니다.

**`POST /api/ingredients/match`**

#### Request

| 항목 | 값 |
|------|-----|
| Content-Type | `application/json` |

```json
{
  "product_names": ["국산콩 두부", "깻잎", "삼겹살", "CJ 햇반"]
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `product_names` | string[] | O | OCR에서 추출된 상품명 배열 |

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "matched": [
      {
        "product_name": "국산콩 두부",
        "ingredientId": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "ingredientName": "두부",
        "category": "가공식품",
        "similarity": 0.92
      },
      {
        "product_name": "깻잎",
        "ingredientId": "b2c3d4e5-f6a7-8901-bcde-f12345678901",
        "ingredientName": "깻잎",
        "category": "채소/과일",
        "similarity": 1.0
      },
      {
        "product_name": "삼겹살",
        "ingredientId": "c3d4e5f6-a7b8-9012-cdef-123456789012",
        "ingredientName": "삼겹살",
        "category": "정육/계란",
        "similarity": 1.0
      }
    ],
    "unmatched": [
      {
        "product_name": "CJ 햇반",
        "reason": "DB에 일치하는 재료 없음",
        "suggestions": ["밥", "쌀"]
      }
    ],
    "matched_count": 3,
    "unmatched_count": 1
  }
}
```

#### Response 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `matched` | Array | 매칭 성공한 재료 목록 |
| `matched[].product_name` | string | 입력된 상품명 (원본) |
| `matched[].ingredientId` | UUID | DB 재료 ID |
| `matched[].ingredientName` | string | DB 재료명 |
| `matched[].category` | string | 재료 카테고리 |
| `matched[].similarity` | float | 매칭 유사도 (0~1) |
| `unmatched` | Array | 매칭 실패한 상품 목록 |
| `unmatched[].product_name` | string | 매칭 실패한 상품명 |
| `unmatched[].reason` | string | 실패 사유 |
| `unmatched[].suggestions` | string[] | 유사 재료 추천 |

---

### 4.3 보유 재료 기반 레시피 추천

사용자가 보유한 재료 ID 목록을 받아, 해당 재료로 만들 수 있는 레시피를 추천합니다.

**`POST /api/recipes/recommend`**

#### Request

| 항목 | 값 |
|------|-----|
| Content-Type | `application/json` |

```json
{
  "ingredientIds": [
    "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
    "b2c3d4e5-f6a7-8901-bcde-f12345678901",
    "c3d4e5f6-a7b8-9012-cdef-123456789012"
  ],
  "top_k": 10,
  "category": null
}
```

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `ingredientIds` | UUID[] | O | 보유 재료 ID 목록 |
| `top_k` | int | X (기본: 10) | 최대 추천 개수 |
| `category` | string \| null | X | 카테고리 필터 (null이면 전체) |

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "recommendations": [
      {
        "recipeId": "0848e1e1-65b9-4302-ab8c-f6e2ee9c70e8",
        "name": "두부깻잎전",
        "category": "반찬",
        "imageUrl": "",
        "matchedIngredients": [
          {"ingredientId": "a1b2...", "ingredientName": "두부"},
          {"ingredientId": "b2c3...", "ingredientName": "깻잎"}
        ],
        "missingIngredients": [
          {"ingredientId": "d4e5...", "ingredientName": "부침가루"},
          {"ingredientId": "e5f6...", "ingredientName": "계란"}
        ],
        "matchRate": 0.67,
        "totalIngredientCount": 6
      },
      {
        "recipeId": "233c9632-a481-44f1-967d-b78ce0e3a173",
        "name": "삼겹살깻잎구이",
        "category": "구이류",
        "imageUrl": "",
        "matchedIngredients": [
          {"ingredientId": "c3d4...", "ingredientName": "삼겹살"},
          {"ingredientId": "b2c3...", "ingredientName": "깻잎"}
        ],
        "missingIngredients": [
          {"ingredientId": "f6a7...", "ingredientName": "소금"}
        ],
        "matchRate": 0.75,
        "totalIngredientCount": 4
      }
    ],
    "total_count": 2,
    "input_ingredient_count": 3
  }
}
```

#### Response 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `recommendations` | Array | 추천 레시피 목록 (matchRate 내림차순) |
| `recommendations[].recipeId` | UUID | 레시피 ID |
| `recommendations[].name` | string | 레시피명 |
| `recommendations[].category` | string | 카테고리 |
| `recommendations[].imageUrl` | string | 이미지 URL |
| `recommendations[].matchedIngredients` | Array | 보유 중인 재료 목록 |
| `recommendations[].missingIngredients` | Array | 부족한 재료 목록 |
| `recommendations[].matchRate` | float | 재료 일치율 (0~1) |
| `recommendations[].totalIngredientCount` | int | 레시피에 필요한 전체 재료 수 |
| `total_count` | int | 추천된 레시피 총 개수 |
| `input_ingredient_count` | int | 입력된 재료 수 |

---

### 4.4 레시피 상세 조회

레시피 ID로 레시피 상세 정보(재료 목록 + 조리 단계)를 조회합니다.

**`GET /api/recipes/{recipeId}`**

#### Path Parameter

| 파라미터 | 타입 | 설명 |
|----------|------|------|
| `recipeId` | UUID | 조회할 레시피 ID |

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "recipeId": "0848e1e1-65b9-4302-ab8c-f6e2ee9c70e8",
    "name": "L.A갈비구이",
    "category": "반찬",
    "imageUrl": "",
    "ingredients": [
      {
        "recipeIngredientId": "7b21236d-6ce6-43bb-8d42-f97c8be6e8e9",
        "ingredientId": "b287457a-6bd2-410c-82d7-29a1de745623",
        "ingredientName": "L.A갈비",
        "category": "정육/계란",
        "amount": 200.0,
        "unit": "g"
      },
      {
        "ingredientId": "fcb73e85-1b87-49d1-9637-11394d76baba",
        "ingredientName": "양파",
        "category": "채소/과일",
        "amount": 20.0,
        "unit": "g"
      },
      {
        "ingredientId": "4d26fb3a-a0d7-4843-9d1a-61d08a5888b3",
        "ingredientName": "저염간장",
        "category": "소스/조미료/오일",
        "amount": 20.0,
        "unit": "g"
      }
    ],
    "steps": [
      {
        "recipeStepId": "4a36e484-9480-4259-9eb1-800cbd7d0fad",
        "stepOrder": 1,
        "description": "L.A 갈비는 물에 담그어 핏물과 갈비 톱밥을 제거시켜 놓는다."
      },
      {
        "recipeStepId": "a93aa941-2095-4025-b8bc-d30ffc17d64c",
        "stepOrder": 2,
        "description": "강판에 배와 양파를 곱게 갈아 준비한다."
      },
      {
        "recipeStepId": "e6a5d2b9-05ce-417a-a5c7-5e61270b2289",
        "stepOrder": 3,
        "description": "핏물을 제거한 갈비에 배즙과 양파즙을 넣어 숙성시킨다."
      }
    ],
    "step_count": 3,
    "ingredient_count": 3
  }
}
```

#### Response 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `recipeId` | UUID | 레시피 ID |
| `name` | string | 레시피명 |
| `category` | string | 카테고리 |
| `imageUrl` | string | 이미지 URL (없으면 빈 문자열) |
| `ingredients` | Array | 필요한 재료 목록 |
| `ingredients[].ingredientId` | UUID | 재료 ID |
| `ingredients[].ingredientName` | string | 재료명 |
| `ingredients[].category` | string | 재료 카테고리 |
| `ingredients[].amount` | float | 수량 |
| `ingredients[].unit` | string | 단위 |
| `steps` | Array | 조리 단계 목록 (stepOrder 오름차순) |
| `steps[].recipeStepId` | UUID | 조리 단계 ID |
| `steps[].stepOrder` | int | 조리 순서 |
| `steps[].description` | string | 조리 설명 |

---

### 4.5 재료 키워드 검색

키워드로 DB의 재료를 검색합니다. 사용자가 수동으로 재료를 추가할 때 사용합니다.

**`GET /api/ingredients/search`**

#### Query Parameter

| 파라미터 | 타입 | 필수 | 설명 |
|----------|------|------|------|
| `q` | string | O | 검색 키워드 |
| `category` | string | X | 카테고리 필터 |
| `limit` | int | X (기본: 20) | 최대 반환 개수 |

#### 예시 요청

```
GET /api/ingredients/search?q=돼지&category=정육/계란&limit=10
```

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "results": [
      {
        "ingredientId": "f1234567-abcd-4321-efab-1234567890ab",
        "ingredientName": "돼지고기",
        "category": "정육/계란"
      },
      {
        "ingredientId": "a2345678-bcde-5432-fabc-234567890abc",
        "ingredientName": "돼지갈비",
        "category": "정육/계란"
      },
      {
        "ingredientId": "b3456789-cdef-6543-abcd-34567890abcd",
        "ingredientName": "돼지안심",
        "category": "정육/계란"
      }
    ],
    "total_count": 3,
    "query": "돼지"
  }
}
```

#### Response 필드 설명

| 필드 | 타입 | 설명 |
|------|------|------|
| `results` | Array | 검색 결과 재료 목록 |
| `results[].ingredientId` | UUID | 재료 ID |
| `results[].ingredientName` | string | 재료명 |
| `results[].category` | string | 재료 카테고리 |
| `total_count` | int | 검색 결과 총 개수 |
| `query` | string | 입력된 검색어 |

---

### 4.6 서비스 상태 확인 (Health Check)

AI 서버 및 의존 서비스(PaddleOCR, Qwen LLM)의 상태를 확인합니다.

**`GET /api/health`**

#### Response — `200 OK`

```json
{
  "success": true,
  "data": {
    "status": "healthy",
    "version": "1.0.0",
    "services": {
      "paddleocr": "available",
      "qwen_llm": "available",
      "database": "connected"
    },
    "stats": {
      "total_recipes": 2005,
      "total_ingredients": 3176,
      "total_recipe_ingredients": 17101,
      "total_recipe_steps": 10984
    }
  }
}
```

---

## 5. 에러 응답 공통 형식

모든 API는 에러 발생 시 동일한 형식으로 응답합니다.

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "사람이 읽을 수 있는 에러 메시지"
  }
}
```

### 에러 코드 목록

| HTTP Status | code | 설명 |
|-------------|------|------|
| `400` | `INVALID_REQUEST` | 필수 파라미터 누락 또는 형식 오류 |
| `400` | `INVALID_IMAGE` | 이미지 파일이 아니거나 읽을 수 없음 |
| `404` | `RECIPE_NOT_FOUND` | 해당 recipeId의 레시피가 없음 |
| `404` | `INGREDIENT_NOT_FOUND` | 해당 ingredientId의 재료가 없음 |
| `422` | `OCR_FAILED` | OCR 처리 실패 (이미지 품질 문제 등) |
| `500` | `LLM_ERROR` | Qwen LLM 호출 실패 |
| `500` | `INTERNAL_ERROR` | 서버 내부 오류 |
| `503` | `SERVICE_UNAVAILABLE` | PaddleOCR 또는 LLM 서비스 비활성 |

### 에러 응답 예시

```json
{
  "success": false,
  "error": {
    "code": "INVALID_IMAGE",
    "message": "지원하지 않는 이미지 형식입니다. jpg, png 파일만 업로드 가능합니다."
  }
}
```

```json
{
  "success": false,
  "error": {
    "code": "RECIPE_NOT_FOUND",
    "message": "레시피를 찾을 수 없습니다: 0848e1e1-65b9-4302-ab8c-000000000000"
  }
}
```

---

## 6. 전체 흐름 시퀀스

사용자가 영수증을 촬영하고 레시피를 추천받기까지의 전체 흐름입니다.

```
┌──────────┐    ┌──────────────┐    ┌──────────────┐
│  Flutter  │    │ Spring Boot  │    │  AI FastAPI   │
│   App     │    │   Backend    │    │   Server      │
└────┬─────┘    └──────┬───────┘    └──────┬───────┘
     │                 │                    │
     │ ① 영수증 촬영    │                    │
     │ ────────────────>                    │
     │                 │ ② 이미지 전달       │
     │                 │ ──────────────────> │
     │                 │   POST /api/ocr/   │
     │                 │   receipt           │
     │                 │                    │
     │                 │   PaddleOCR 실행    │
     │                 │   Qwen LLM 보정    │
     │                 │                    │
     │                 │ ③ 식품명 목록 반환   │
     │                 │ <────────────────── │
     │                 │                    │
     │ ④ 추출된 상품    │                    │
     │   목록 표시      │                    │
     │ <────────────────                    │
     │                 │                    │
     │ ⑤ 사용자 확인    │                    │
     │   (수정/삭제)    │                    │
     │ ────────────────>                    │
     │                 │ ⑥ 상품명→재료 매칭   │
     │                 │ ──────────────────> │
     │                 │   POST /api/       │
     │                 │   ingredients/match │
     │                 │                    │
     │                 │ ⑦ 매칭된 재료 반환   │
     │                 │ <────────────────── │
     │                 │                    │
     │                 │ ⑧ 재료 목록으로     │
     │                 │   레시피 추천 요청   │
     │                 │ ──────────────────> │
     │                 │   POST /api/       │
     │                 │   recipes/recommend │
     │                 │                    │
     │                 │ ⑨ 추천 레시피 반환   │
     │                 │ <────────────────── │
     │                 │                    │
     │ ⑩ 추천 레시피    │                    │
     │   목록 표시      │                    │
     │ <────────────────                    │
     │                 │                    │
     │ ⑪ 레시피 선택    │                    │
     │ ────────────────>                    │
     │                 │ ⑫ 레시피 상세 조회   │
     │                 │ ──────────────────> │
     │                 │   GET /api/recipes/ │
     │                 │   {recipeId}        │
     │                 │                    │
     │                 │ ⑬ 상세 정보 반환    │
     │                 │ <────────────────── │
     │                 │                    │
     │ ⑭ 레시피 상세    │                    │
     │   화면 표시      │                    │
     │ <────────────────                    │
     │                 │                    │
```

### 단계별 요약

| 단계 | 설명 | API 호출 |
|------|------|----------|
| ① ~ ③ | 영수증 촬영 → OCR + LLM 보정 | `POST /api/ocr/receipt` |
| ④ ~ ⑤ | 추출된 상품 목록 사용자 확인/수정 | (클라이언트 처리) |
| ⑥ ~ ⑦ | 확인된 상품명 → DB 재료 매칭 | `POST /api/ingredients/match` |
| ⑧ ~ ⑨ | 매칭된 재료로 레시피 추천 | `POST /api/recipes/recommend` |
| ⑩ ~ ⑪ | 추천 레시피 목록 → 사용자 선택 | (클라이언트 처리) |
| ⑫ ~ ⑭ | 선택한 레시피 상세 조회 | `GET /api/recipes/{recipeId}` |

---

### 참고: 재료 카테고리 코드

| 코드 | 설명 | 예시 |
|------|------|------|
| `정육/계란` | 육류 및 계란 | 소고기, 돼지고기, 닭고기, 계란 |
| `해산물` | 수산물 | 새우, 오징어, 연어, 조개 |
| `채소/과일` | 채소류 및 과일 | 양파, 감자, 시금치, 사과 |
| `유제품` | 우유, 치즈 등 | 우유, 생크림, 모짜렐라치즈 |
| `쌀/면/빵` | 주식류 | 쌀, 소면, 식빵, 떡 |
| `소스/조미료/오일` | 양념 및 소스 | 간장, 고추장, 참기름, 소금 |
| `가공식품` | 가공/포장 식품 | 두부, 어묵, 햄, 통조림 |
| `기타` | 기타 분류 | 젤라틴, 한천, 식용꽃 |
