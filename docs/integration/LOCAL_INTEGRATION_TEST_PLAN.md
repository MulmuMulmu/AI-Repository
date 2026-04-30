# Local Integration Test Plan

이 문서는 로컬 Docker 기준으로 AI OCR/Qwen 서비스, AI 추천 서비스, Spring 백엔드, Expo 사용자 앱을 연결 검증하는 절차다.

## 대상 레포와 브랜치

- AI: `AI-Repository`, `v0.2`
- 백엔드: `Back-Repository`, `main`
- 프론트 사용자 앱: `Front-Repository`, `application`

## 로컬 포트

| 서비스 | 포트 | 실행 기준 | 역할 |
| --- | --- | --- | --- |
| AI OCR/Qwen API | `8000` | AI `docker compose`의 `ocr-api` | 영수증 OCR, 구매일자/품목/카테고리/수량 추출, 소비기한 예측 |
| AI 추천 API | `8002` | AI `docker compose`의 `recommend-api` | 보유 재료와 후보 레시피 간 거리/겹침 기반 추천 |
| Spring 백엔드 | `8080` | 백엔드 `bootRun` 또는 Docker | 프론트 공개 API, AI adapter |
| Expo 사용자 앱 | `8082` | 프론트 `expo start --web` | 사용자 앱 화면 |

## AI 단독 검증

```powershell
docker compose up --build ocr-api recommend-api
Invoke-RestMethod http://localhost:8000/openapi.json
Invoke-RestMethod http://localhost:8002/openapi.json
python -m pytest -q
```

추천 smoke 요청:

```powershell
$body = @{
  userIngredient = @{
    ingredients = @("김치")
    preferIngredients = @("고등어", "소고기")
    dispreferIngredients = @("샐러드", "오이")
    IngredientRatio = 0.5
  }
  candidates = @(
    @{
      recipe_id = "exampleUUID1"
      title = "돼지고기 김치찌개"
      ingredients = @("김치", "돼지고기", "두부", "대파", "고춧가루")
    }
  )
} | ConvertTo-Json -Depth 5

Invoke-RestMethod http://localhost:8002/ai/ingredient/recommondation -Method Post -ContentType "application/json" -Body $body
```

## 백엔드 단독 검증

```powershell
$env:AI_OCR_BASE_URL = "http://localhost:8000"
$env:AI_RECOMMEND_BASE_URL = "http://localhost:8002"
.\gradlew.bat test
.\gradlew.bat bootRun
```

검증 기준:

- AI client 단위 테스트는 mock HTTP 응답으로 성공/실패를 확인한다.
- `POST /ingredient/analyze`는 백엔드 envelope `success/code/result`를 유지한다.
- `POST /recipe/recommendations`는 백엔드 envelope `success/code/result`를 유지한다.
- AI 장애 시 백엔드는 `success:false`, `code:AI500` 형태로 응답한다.

## 프론트 단독 검증

```powershell
$env:EXPO_PUBLIC_API_BASE_URL = "http://localhost:8080"
npm install
npx expo start --web --localhost --port 8082
```

검증 기준:

- 로그인 화면이 백엔드 base URL을 공통 설정에서 사용한다.
- 내 식자재 화면은 `GET /ingredient/all/my` 실패 시에도 기존 더미 화면이 깨지지 않는다.
- 영수증 촬영/갤러리 후 OCR API가 실패해도 수동 입력으로 이어진다.
- 레시피 추천 API가 실패해도 추천 결과 더미 화면이 유지된다.

## 로컬 통합 smoke 시나리오

1. AI 컨테이너 2개 실행: OCR `8000`, 추천 `8002`
2. 백엔드 실행: `8080`, `AI_OCR_BASE_URL`, `AI_RECOMMEND_BASE_URL` 설정
3. 프론트 실행: `8082`, `EXPO_PUBLIC_API_BASE_URL=http://localhost:8080` 설정
4. 사용자 로그인
5. 영수증 촬영 또는 갤러리 선택
6. 백엔드 `POST /ingredient/analyze` 호출 확인
7. OCR 결과를 사용자가 확인하고 식재료 저장
8. 내 식재료 조회
9. 레시피 추천 요청
10. 백엔드 `POST /recipe/recommendations` 및 AI 추천 호출 확인

## 통과 기준

- 프론트 화면 전환이 중단되지 않는다.
- 백엔드 응답은 항상 `success/code/result` envelope를 유지한다.
- AI OCR/Qwen 컨테이너와 AI 추천 컨테이너 로그에서 호출 흔적이 확인된다.
- 추천 API는 `success:true`, `result.recommendations` 또는 장애 시 `success:false`, `code:AI500`로 내려온다.

## 제외 범위

- 나눔/채팅 전체 플로우
- 운영 Cloud Run 배포 자동화
- OCR 정규화 사전 확장
- 추천 후보 레시피를 백엔드 DB에서 자동 구성하는 고도화
