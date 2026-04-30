# Local Integration Test Report 2026-04-30

검증 기준: 로컬 개발 환경에서 AI OCR/Qwen API, AI 추천 API, Spring 백엔드, Expo/Apps in Toss 프론트를 실제 실행 또는 빌드 가능한 수준까지 확인한다.

## 결론

2026-04-30 1차 검증에서는 전체 E2E 통합테스트가 막혔지만, 후속 수정 후 Docker를 제외한 로컬 프로세스 기준 API smoke와 브라우저 UI E2E가 통과했다.

현재 통과한 범위는 AI 단독 테스트, AI 추천 API smoke, AI OCR/소비기한 API smoke, 백엔드 단위/컨텍스트 테스트, 백엔드 `bootRun` 기동, 프론트 Expo export, Apps in Toss 미니앱 타입/도메인 테스트, 백엔드 경유 추천/OCR smoke, 브라우저 기반 사용자 UI E2E다.

남은 차단 지점은 Docker 기반 실행 검증과 실제 모바일 기기/토스 WebView 검증이다. HTTP API 기준 인증/DB 저장 포함 시나리오와 브라우저 UI 클릭 시나리오는 후속 검증에서 통과했다.

- Docker daemon이 꺼져 있어 Docker Compose 기반 컨테이너 통합 실행은 확인하지 않았다.
- 프론트 화면을 실제 브라우저에서 클릭하는 UI E2E는 Playwright 기준으로 통과했다.
- 백엔드 `AiService`의 기존 `/ai/*` 내부 로직은 남아 있지만, 프론트 공개 경로 `/ingredient/analyze`, `/recipe/recommendations`, `/ingredient/recommondation`은 AI gateway를 통해 FastAPI OCR/추천 서비스로 연결했다.

따라서 현업 기준으로는 “Docker 제외 로컬 프로세스 API/UI E2E는 통과, Docker 실행 검증과 실제 기기/Toss WebView 검증은 다음 단계”로 판단한다.

## 검증 환경

| 항목 | 값 |
| --- | --- |
| 작업 루트 | `C:\Users\USER-PC\Desktop\jp` |
| AI 레포 | `.cache\AI-Repository-fresh` |
| 백엔드 레포 | `.cache\Back-Repository-fresh` |
| 프론트 레포 | `.cache\Front-Repository-application-fresh` |
| 검증일 | 2026-04-30 |
| OS shell | Windows PowerShell |

## AI 검증 결과

### Pytest

명령:

```powershell
cd C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh
python -m pytest -q
```

결과:

```text
212 passed, 5 warnings in 10.32s
```

판정: 통과.

주의: FastAPI `on_event` deprecation warning, `python_multipart` warning이 있으나 테스트 실패는 아니다.

### Docker Compose 표면 검증

명령:

```powershell
docker-compose config --services
```

결과:

```text
recommend-api
ocr-api
```

판정: Compose 파일 구조는 유효.

차단:

```text
docker ps
failed to connect to the docker API at npipe:////./pipe/dockerDesktopLinuxEngine
```

Docker Desktop daemon이 꺼져 있어 `docker-compose up` 기반 컨테이너 통합 실행은 미검증이다. 사용자가 이번 라운드에서 Docker가 필요 없다고 판단했기 때문에 로컬 uvicorn 프로세스 기준으로 대체 검증했다.

### AI 추천 API smoke

실행:

```powershell
python -m uvicorn app_recommend:app --host 127.0.0.1 --port 8002
POST http://127.0.0.1:8002/ai/ingredient/recommondation
```

요청 핵심:

```json
{
  "userIngredient": {
    "ingredients": ["김치", "계란"],
    "preferIngredients": ["돼지고기"],
    "dispreferIngredients": ["오이"],
    "IngredientRatio": 0.5
  },
  "candidates": [
    {
      "recipe_id": "r1",
      "title": "김치계란볶음밥",
      "ingredients": ["김치", "계란", "밥"]
    },
    {
      "recipe_id": "r2",
      "title": "오이무침",
      "ingredients": ["오이", "고춧가루"]
    }
  ]
}
```

결과:

```json
{
  "openapiTitle": "추천 AI API",
  "success": true,
  "recommendationCount": 1,
  "firstTitle": "김치계란볶음밥"
}
```

판정: 통과.

의미:

- `IngredientRatio: 0.5` 기준으로 절반 이상 보유한 후보가 추천된다.
- `dispreferIngredients`에 걸린 `오이무침`은 제외된다.
- 응답 shape는 `success:true/data/recommendations`다.

### AI OCR/소비기한 API smoke

실행:

```powershell
python -m uvicorn app_ocr:app --host 127.0.0.1 --port 8000
POST http://127.0.0.1:8000/ai/ingredient/prediction
```

초기 관찰:

- 첫 openapi 응답까지 약 40초가 걸렸다.
- PaddleOCR 모델 로딩이 startup을 잡고 있어 cold start가 길다.

정상 요청:

```json
{
  "item_name": "우유",
  "category": "유제품",
  "purchase_date": "2026-03-11"
}
```

결과:

```json
{
  "success": true,
  "data": {
    "item_name": "우유",
    "purchase_date": "2026-03-11",
    "storage_method": "냉장",
    "expiry_date": "2026-03-18",
    "confidence": 0.7,
    "method": "rule-based",
    "reason": "우유 냉장 기준 7일",
    "d_day": -44,
    "risk_level": "expired"
  },
  "error": null
}
```

판정: 통과.

계약 주의:

- AI 소비기한 API는 `item_name`을 요구한다.
- `product_name`으로 요청하면 `ExpiryRequest.item_name` 누락으로 500이 발생했다.
- 백엔드/프론트가 `product_name`, `ingredientName`, `item_name` 중 무엇을 공식 계약으로 쓸지 어댑터에서 명확히 변환해야 한다.

## 백엔드 검증 결과

### Gradle 테스트

명령:

```powershell
cd C:\Users\USER-PC\Desktop\jp\.cache\Back-Repository-fresh
.\gradlew.bat test
```

결과:

```text
BUILD SUCCESSFUL in 17s
```

판정: 통과.

현재 테스트 범위:

- Spring context load
- Admin service unit tests
- AiService unit tests

### 백엔드 서버 기동

명령:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=test --server.port=8080"
```

초기 결과:

```text
Cannot load driver class: org.h2.Driver
Task :bootRun FAILED
```

초기 판정: 실패.

원인:

- `build.gradle`의 H2 의존성이 `testRuntimeOnly 'com.h2database:h2'`로만 들어가 있다.
- `bootRun`은 main runtime classpath로 실행되므로 test profile이 H2 URL을 사용해도 H2 driver를 로딩하지 못한다.

조치:

- `build.gradle`에서 H2를 `runtimeOnly 'com.h2database:h2'`로 변경했다.

후속 결과:

```text
Tomcat started on port 8080
GET /ai/health/check -> server is Running!
```

후속 판정: 통과.

### AI adapter 상태

확인 파일:

```text
src/main/java/com/team200/graduation_project/domain/ai/service/AiService.java
```

초기 판정:

- 현재 백엔드 `/ai/ocr/analyze`, `/ai/ocr/prediction`, `/ai/recommendations/*`는 AI FastAPI 컨테이너를 호출하지 않는다.
- `IngredientRepository`, `UserIngredientRepository`, `RecipeRepository`, `RecipeIngredientRepository`를 읽어 내부 Java 로직으로 응답한다.
- 따라서 AI 컨테이너가 정상이어도 백엔드 경유 사용자 경로에서는 OCR/Qwen/벡터 추천 컨테이너가 사용되지 않는다.

조치:

- `AiGatewayClient` / `HttpAiGatewayClient`를 추가했다.
- `POST /ingredient/analyze`는 백엔드가 multipart 이미지를 받아 AI OCR `POST /ai/ocr/analyze`로 전달한다.
- `POST /recipe/recommendations`는 백엔드가 요청 body를 AI 추천 `POST /ai/ingredient/recommondation`으로 전달한다.
- Apps in Toss 미니앱 호환을 위해 `POST /ingredient/recommondation`도 같은 추천 gateway로 연결했다.

후속 판정: 프론트 공개 경로 기준 통과. 기존 `/ai/*` Java 내부 로직은 유지되어 있으므로, 팀 API 정책에 따라 이후 정리 여부를 결정한다.

## 프론트 검증 결과

### Expo 사용자 앱 export

명령:

```powershell
cd C:\Users\USER-PC\Desktop\jp\.cache\Front-Repository-application-fresh
$env:EXPO_PUBLIC_API_BASE_URL='http://127.0.0.1:8080'
npx --no-install expo export --platform web --output-dir $env:TEMP\mulmu-expo-integration-check
```

결과:

```text
Exported: C:\Users\USER-PC\AppData\Local\Temp\mulmu-expo-integration-check
```

판정: 통과.

### Apps in Toss 미니앱

명령:

```powershell
cd C:\Users\USER-PC\Desktop\jp\.cache\Front-Repository-application-fresh\apps-in-toss-miniapp
node .\node_modules\typescript\bin\tsc --noEmit
node .\scripts\test-domain.mjs
```

결과:

```text
domain tests passed
```

판정: 통과.

이미 별도 검증된 제출 번들:

- WSL/Linux + Node 24 기준 `MulmuMulmu.ait` 빌드 성공.

### 프론트 API 계약 관찰

Expo app:

- `src/api/config.js`: 기본 URL `https://sokksik.click`, env로 `EXPO_PUBLIC_API_BASE_URL` 변경 가능.
- `src/api/ingredients.js`: `POST /ingredient/analyze`, `GET /ingredient/all/my`, `POST /ingredient/input`.
- `src/api/recipes.js`: `POST /recipe/recommendations`.

Apps in Toss miniapp:

- `src/services/miniappApi.ts`: base URL `http://localhost:8080` 하드코딩.
- Toss Login: `POST /auth/toss/login`.
- OCR: `POST /ingredient/analyze`.
- 추천: `POST /ingredient/recommondation`.

계약 차이:

- AI 추천 컨테이너는 `/ai/ingredient/recommondation`.
- 미니앱은 백엔드에 `/ingredient/recommondation`을 호출한다.
- Expo 앱은 백엔드에 `/recipe/recommendations`를 호출한다.
- 백엔드 현재 AI 컨트롤러는 `/ai/recommendations/only`, `/ai/recommendations/not/only`다.

이 상태에서는 “프론트가 백엔드를 통해 AI 추천 컨테이너를 호출한다”는 단일 계약이 아직 확정되지 않았다.

## 통합 smoke 시나리오 판정

| 단계 | 상태 | 근거 |
| --- | --- | --- |
| AI OCR API 실행 | 부분 통과 | 로컬 uvicorn 기동 및 소비기한 smoke 통과. Docker daemon 꺼짐 |
| AI 추천 API 실행 | 통과 | 로컬 uvicorn 기동 및 추천 smoke 통과 |
| 백엔드 테스트 | 통과 | `gradlew test` 성공 |
| 백엔드 로컬 서버 | 통과 | H2 runtime classpath 수정 후 `GET /ai/health/check` 성공 |
| 프론트 빌드/export | 통과 | Expo web export 성공 |
| Apps in Toss 미니앱 타입/도메인 | 통과 | `tsc`, domain tests 성공 |
| 프론트 -> 백엔드 -> AI OCR | 통과 | `POST /ingredient/analyze`가 AI OCR 응답 key를 포함한 백엔드 envelope 반환 |
| 프론트 -> 백엔드 -> AI 추천 | 통과 | `POST /recipe/recommendations`, `POST /ingredient/recommondation` 모두 추천 1건 반환 |
| 회원가입 -> 로그인 -> 식재료 저장 -> 조회 -> 추천 | 통과 | JWT 발급, `POST /ingredient/input`, `GET /ingredient/all/my`, 추천 API 연계 확인 |
| 브라우저 UI E2E | 통과 | Playwright로 로그인, 직접 식재료 입력, 추천 결과 화면까지 확인 |

## 후속 로컬 프로세스 smoke 결과

Docker 없이 각 서비스를 로컬 프로세스로 실행했다.

실행 서비스:

- AI OCR: `python -m uvicorn app_ocr:app --host 127.0.0.1 --port 8000`
- AI 추천: `python -m uvicorn app_recommend:app --host 127.0.0.1 --port 8002`
- 백엔드: `.\gradlew.bat bootRun --args="--spring.profiles.active=test --server.port=8080"`

검증 결과:

```json
{
  "ready": {
    "backend": true,
    "recommend": true,
    "ocr": true
  },
  "health": "server is Running!",
  "recipeSuccess": true,
  "recipeCount": 1,
  "recipeFirst": "김치계란볶음밥",
  "miniRecipeSuccess": true,
  "ocrSuccess": true,
  "ocrResultKeys": "diagnostics,food_count,food_items,model,ocr_texts,purchased_at,review_reasons,review_required,totals,trace_id,vendor_name"
}
```

판정: Docker 제외 로컬 프로세스 기준 백엔드-AI smoke 통과.

## 인증/저장 포함 API E2E 결과

Docker 없이 각 서비스를 로컬 프로세스로 실행한 뒤, 백엔드 공개 API만 사용해 사용자 흐름을 검증했다.

시나리오:

1. `POST /auth/signup`
2. `POST /auth/login`
3. 로그인 JWT를 `Authorization` 헤더에 넣고 `POST /ingredient/input`
4. `GET /ingredient/all/my`
5. 조회된 보유 재료를 사용해 `POST /recipe/recommendations`
6. 테스트 이미지를 사용해 `POST /ingredient/analyze`

검증 결과:

```json
{
  "ready": {
    "ocr": true,
    "recommend": true,
    "backend": true
  },
  "signup": true,
  "login": true,
  "tokenReceived": true,
  "input": true,
  "mySuccess": true,
  "myCount": 1,
  "myFirst": "김치",
  "myDday": "D-5",
  "recommend": true,
  "recommendCount": 1,
  "recommendFirst": "김치계란볶음밥",
  "ocr": true,
  "ocrFoodCount": 0
}
```

판정: HTTP API 기준 인증/저장/조회/추천/OCR E2E 통과.

주의: OCR은 테스트용 단순 이미지라 `food_count`는 0이다. 이 값은 OCR 품질 실패가 아니라 백엔드 경유 OCR 호출과 envelope 확인 목적의 smoke 결과다. 실사 영수증 품질 평가는 별도 OCR 품질셋으로 검증해야 한다.

## 브라우저 UI E2E 결과

Docker 없이 로컬 프로세스로 AI 추천 API와 백엔드를 실행하고, Expo web 앱을 `http://127.0.0.1:8082`에서 실행했다.

실행 서비스:

- AI 추천: `python -m uvicorn app_recommend:app --host 127.0.0.1 --port 8002`
- 백엔드: `.\gradlew.bat bootRun --args="--spring.profiles.active=test --server.port=8080"`
- 프론트: `EXPO_PUBLIC_API_BASE_URL=http://127.0.0.1:8080 npx --no-install expo start --web --localhost --port 8082`

사전 조치:

- Expo web 실행 시 TypeScript 파일이 감지되었지만 루트 앱에 `typescript` 의존성이 없어 기동이 중단됐다.
- 프론트 레포에 `typescript@~5.9.2`, `playwright`를 dev dependency로 추가해 로컬 UI E2E를 재현 가능하게 했다.

시나리오:

1. 테스트 사용자를 백엔드 `POST /auth/signup`으로 생성한다.
2. 추천 성공 조건을 맞추기 위해 같은 사용자에 `돼지고기`를 사전 보유 재료로 저장한다.
3. 브라우저에서 로그인 화면에 접속한다.
4. `POST /auth/login` 성공 후 신규 사용자 온보딩으로 이동한다.
5. 알레르기, 선호 재료, 비선호 재료 화면을 통과한다.
6. 냉장고 화면에서 사전 저장한 `돼지고기`가 보이는지 확인한다.
7. `+ 추가 -> 직접 입력`에서 `김치`, `26.05.05`, `가공식품`을 입력한다.
8. `POST /ingredient/input` 성공 후 냉장고 화면에서 `김치`가 보이는지 확인한다.
9. 레시피 탭으로 이동해 `내 식자재로 레시피 추천받기`를 누른다.
10. 보유 재료 `김치`, `돼지고기`가 추천 입력에 표시되는지 확인한다.
11. `선택한 재료로 레시피 추천받기`를 눌러 결과 화면으로 이동한다.
12. 결과 화면에서 `AI 추천 결과 안내`와 `돼지고기 김치찌개` 카드가 보이는지 확인한다.

검증 결과:

```json
{
  "success": true,
  "apiStatuses": [
    "200 /auth/login",
    "200 /ingredient/all/my",
    "200 /ingredient/all/my",
    "200 /ingredient/input",
    "200 /ingredient/all/my",
    "200 /ingredient/all/my",
    "200 /recipe/recommendations"
  ],
  "screenshot": "C:\\Users\\USER-PC\\AppData\\Local\\Temp\\mulmu-ui-e2e-result-final.png"
}
```

판정: 브라우저 UI 기준 로그인/식재료 저장/조회/추천 결과 표시 E2E 통과.

후속 수정:

- 로그인 화면이 백엔드 `firstLogin` boolean을 우선 사용하고, 기존 오타 필드 `fisrtLogin`도 fallback으로 허용하도록 수정했다.
- 냉장고 화면은 포커스 복귀 시 `GET /ingredient/all/my`를 다시 호출하도록 수정해 직접 입력 후 목록이 갱신되도록 했다.

## 후속 수정 내역

- 백엔드 `POST /ingredient/input` 추가.
- 백엔드 `GET /ingredient/all/my` 추가.
- `Ingredient`, `UserIngredient` 로컬 저장을 위해 ID 자동 생성과 생성 메서드 추가.
- `Authorization` 헤더의 raw JWT 또는 `Bearer` JWT를 모두 허용.
- 식재료 조회 응답은 프론트 계약에 맞춰 `ingredient`, `name`, `category`, `expirationDate`, `dDay`를 반환한다.

## 우선순위 조치

### 1. 백엔드 로컬 실행 환경부터 고정

목표:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local --server.port=8080"
```

성공 기준:

- `GET /ai/health/check`가 200으로 응답한다.
- DB 의존 endpoint는 seed 또는 mock 데이터 기준으로 실패하지 않는다.

권장:

- 통합테스트용 MySQL Docker Compose를 백엔드 레포에 추가하거나,
- `local` profile + H2 runtime 의존성을 명시한다.

### 2. 백엔드 AI adapter 구현

목표:

- 백엔드는 프론트 공개 API만 제공한다.
- 백엔드 내부에서 AI OCR `http://localhost:8000`과 AI 추천 `http://localhost:8002`를 호출한다.

필수 env:

```text
AI_OCR_BASE_URL=http://localhost:8000
AI_RECOMMEND_BASE_URL=http://localhost:8002
```

필수 변환:

- 백엔드 OCR 공개 응답: `success/code/result` envelope 유지.
- AI OCR analyze 응답 `data.food_items[]`를 백엔드 식재료 저장 후보 DTO로 변환.
- 백엔드 소비기한 입력 `ingredientName` 또는 `product_name`을 AI `item_name`으로 변환.
- 백엔드 추천 후보 레시피를 AI `/ai/ingredient/recommondation`의 `candidates[]`로 변환.

### 3. 추천 API 공개 계약 단일화

현재 후보가 세 개다.

- Expo app: `/recipe/recommendations`
- Miniapp: `/ingredient/recommondation`
- Backend AI controller: `/ai/recommendations/only`, `/ai/recommendations/not/only`
- AI recommend container: `/ai/ingredient/recommondation`

권장:

- 프론트 공개 API는 백엔드 담당자가 정한 하나만 남긴다.
- AI 컨테이너 API는 내부 API로 숨긴다.
- 오타가 포함된 `recommondation`은 이미 AI 계약에 남아 있으므로, 외부 공개 API에는 새로 노출하지 않는 편이 낫다.

### 4. Docker Desktop 실행 후 컨테이너 통합 재검증

명령:

```powershell
cd C:\Users\USER-PC\Desktop\jp\.cache\AI-Repository-fresh
docker-compose up --build ocr-api recommend-api
```

성공 기준:

- `GET http://localhost:8000/openapi.json`
- `GET http://localhost:8002/openapi.json`
- OCR/추천 smoke POST 200.

## 다음 통합테스트 통과 기준

다음 라운드에서 아래가 모두 통과해야 “배포 직전 통합테스트 완료”라고 판단한다.

1. AI `ocr-api`, `recommend-api`가 Docker 또는 로컬 프로세스로 동시에 실행된다.
2. 백엔드가 `8080`에서 실행된다.
3. 백엔드가 AI OCR/추천 컨테이너를 실제 HTTP로 호출한다.
4. 프론트는 AI를 직접 호출하지 않고 백엔드만 호출한다.
5. 프론트 화면에서 직접 `회원가입/로그인 -> 식재료 저장 -> 내 식재료 조회 -> 추천 요청 -> 추천 결과`가 이어진다. 현재 브라우저 기준 통과했으며, 실제 기기/Toss WebView 기준 재검증이 필요하다.
6. 실패 응답은 백엔드 envelope `success:false/code/result`를 유지한다.
