# Recommendation Quality Baseline

기준 엔진:

- [vector_engine.py](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/recommendation/vector_engine.py)

기준 fixture:

- [recommendation_quality_cases.json](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/data/labels/recommendation_quality_cases.json)

평가 스크립트:

- [evaluate_recommendation_quality_cases.py](C:/Users/USER-PC/Desktop/jp/.cache/AI-Repository-fresh/scripts/evaluate_recommendation_quality_cases.py)

## 현재 기준

- case 수: `14`
- pass 수: `14`
- overall pass rate: `1.0`
- positive case 수: `11`
- positive top1 hit rate: `1.0`
- positive top3 hit rate: `1.0`
- exclusion case 수: `3`
- exclusion pass rate: `1.0`

## 케이스별 결과

| caseId | expected | actual rank | result |
|---|---|---:|---|
| `japchae_partial_core` | `가는파잡채` | `1` | pass |
| `galbitang_core` | `갈비탕` | `1` | pass |
| `egg_jjim_partial` | `계란찜` | `1` | pass |
| `kimchi_jjigae_partial` | `김치찌개` | `1` | pass |
| `tteok_skewer_partial` | `가래떡꼬치` | `1` | pass |
| `egg_roll_partial` | `계란말이` | `1` | pass |
| `eggplant_beef_stirfry_partial` | `가지쇠고기볶음` | `1` | pass |
| `cutlassfish_braise_partial` | `갈치무조림` | `1` | pass |
| `pork_bone_stew_partial` | `감자탕` | `1` | pass |
| `kimchi_tofu_wrap_partial` | `김치두부쌈` | `1` | pass |
| `egg_jjim_preferred_category` | `계란찜` | `1` | pass |
| `galbitang_allergy_beef_excluded` | `갈비탕 제외` | `-` | pass |
| `kimchi_tofu_disliked_pork_excluded` | `김치두부쌈 제외` | `-` | pass |
| `japchae_excluded_category` | `가는파잡채 제외` | `-` | pass |

## 해석

- 현재 추천 엔진은 `coverageRatio >= 0.5` 조건을 유지한다.
- 그 위에서 `weightedCoverage`, `coreCoverage`, `missingCoreIngredients`를 사용해 재랭킹한다.
- 즉, 절반 이상 보유한 후보 중에서도 핵심 재료를 가진 레시피가 앞에 오도록 설계되어 있다.
- 개인화 QA는 두 부류로 본다.
  - positive case: 기대 레시피가 top1 또는 지정 rank 안에 들어오는지
  - exclusion case: 알레르기/비선호/제외 카테고리 때문에 특정 레시피가 빠지는지

## 다음 확장 우선순위

1. `볶음류`, `찌개/전골류`, `밥류`, `국/탕류`별 fixture 확대
2. 비선호/알레르기 hard filter fixture 추가
3. 선호 카테고리/키워드 boost fixture 추가
4. 실제 사용자 재료 세트 기반 fixture 20건 이상으로 확대
