# OCR/Recommend Split Vector Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** OCR/Qwen 기능과 추천 기능을 두 컨테이너로 분리하고, 추천 엔진을 절반 이상 재료 보유 기준의 벡터 유사도 방식으로 교체한다.

**Architecture:** 단일 레포 안에서 OCR 앱과 추천 앱을 분리한다. OCR 앱은 기존 `main.py` 기반 라우트에서 추천/레시피/검색을 제거하고, 추천 앱은 `POST /recommend`만 제공한다. 추천 엔진은 재료 이진/가중 벡터 + cosine similarity + coverage ratio threshold 0.5를 사용한다.

**Tech Stack:** FastAPI, Python, Docker, pytest

---

### Task 1: 추천 앱 분리용 failing test 추가

**Files:**
- Create: `tests/test_recommend_app_surface.py`
- Modify: `tests/test_public_api_surface.py`

**Step 1: OCR 앱에서 제거될 라우트 failing test 작성**

- `/ai/recommend` 404
- `/ai/recipes/{recipe_id}` 404
- `/ai/ingredients/search` 404

**Step 2: 추천 앱 공개 라우트 failing test 작성**

- `POST /recommend` 200

**Step 3: 테스트 실행**

Run:

```powershell
pytest tests/test_public_api_surface.py tests/test_recommend_app_surface.py -q
```

Expected:

- 추천 앱 관련 테스트 실패

### Task 2: 추천 앱 엔트리포인트 분리

**Files:**
- Create: `app_ocr.py`
- Create: `app_recommend.py`
- Modify: `main.py`

**Step 1: OCR 앱 엔트리포인트 작성**

- 기존 `main.app`를 OCR 전용 surface로 제한

**Step 2: 추천 앱 엔트리포인트 작성**

- `POST /recommend`만 노출

**Step 3: OCR 앱에서 추천/레시피/검색 라우트 제거**

**Step 4: 테스트 실행**

```powershell
pytest tests/test_public_api_surface.py tests/test_recommend_app_surface.py -q
```

### Task 3: 벡터 추천 엔진 failing test 추가

**Files:**
- Create: `recommendation/vector_engine.py`
- Create: `tests/test_vector_recommend_engine.py`

**Step 1: 아래 케이스 테스트 작성**

- 모든 재료 보유 시 추천
- 절반 이상 보유 시 추천
- 절반 미만 보유 시 제외
- 알레르기 재료 포함 시 제외
- 선호 재료 포함 시 동일 coverage 내 우선

**Step 2: 테스트 실행**

```powershell
pytest tests/test_vector_recommend_engine.py -q
```

Expected:

- 실패

### Task 4: 벡터 추천 엔진 구현

**Files:**
- Create: `recommendation/vector_engine.py`
- Modify: `app_recommend.py`

**Step 1: recipe ingredient matrix 구성**

**Step 2: coverage ratio 계산 구현**

**Step 3: cosine similarity 계산 구현**

**Step 4: hard filter 구현**

- allergy
- disliked
- excluded category

**Step 5: soft boost 구현**

- preferred ingredient
- preferred category
- preferred keyword

**Step 6: 테스트 실행**

```powershell
pytest tests/test_vector_recommend_engine.py tests/test_recommend_app_surface.py -q
```

### Task 5: 기존 추천 테스트 대체/정리

**Files:**
- Modify: `tests/test_recommendation_runtime.py`
- Modify: `tests/test_selected_main_modules.py`

**Step 1: 기존 `main.py` 의존 추천 테스트 제거 또는 app_recommend 기준으로 이동**

**Step 2: 추천 결과 shape 유지 테스트**

**Step 3: 실행**

```powershell
pytest tests/test_recommendation_runtime.py tests/test_selected_main_modules.py -q
```

### Task 6: Docker 분리

**Files:**
- Modify: `Dockerfile`
- Modify: `docker-compose.yml`
- Modify: `cloudbuild.cpu.yaml`
- Modify: `cloudbuild.gpu.yaml`

**Step 1: OCR 앱 entrypoint 반영**

**Step 2: 추천 앱 entrypoint 반영**

**Step 3: compose 서비스 분리**

- `ocr-api`
- `recommend-api`

**Step 4: config 검증**

```powershell
docker-compose -f docker-compose.yml config
```

### Task 7: 문서 업데이트

**Files:**
- Modify: `README.md`
- Modify: `docs/api/API_SPEC.md`
- Modify: `docs/architecture/PROJECT_PROCESS_AND_RATIONALE.md`
- Modify: `docs/operations/DOCKER_DEV.md`
- Modify: `docs/operations/GCP_DEPLOYMENT.md`

**Step 1: 공개 API surface를 두 앱 기준으로 갱신**

**Step 2: 추천 알고리즘 설명을 벡터 방식으로 갱신**

**Step 3: 컨테이너 구조 설명 갱신**

### Task 8: 최종 검증

**Files:**
- Test only

**Step 1: 주요 테스트 실행**

```powershell
pytest tests/test_public_api_surface.py tests/test_recommend_app_surface.py tests/test_vector_recommend_engine.py tests/test_ingredient_prediction_rules.py -q
```

**Step 2: 전체 테스트 실행**

```powershell
pytest -q
```

**Step 3: compose config 검증**

```powershell
docker-compose -f docker-compose.yml config
```

**Step 4: 커밋**

```powershell
git add .
git commit -m "feat: split ocr and recommend services"
```
