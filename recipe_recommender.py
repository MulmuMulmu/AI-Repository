"""
레시피 추천 AI 모델 (규칙 기반 다요소 가중치 스코어링)

보유 재료 목록을 받아 최적의 레시피를 추천한다.
외부 ML 라이브러리 없이 순수 Python으로 구현.

스코어링 요소:
  1) 가중 일치율 — 주재료가 양념보다 높은 가중치
  2) 핵심 재료 커버리지 — 핵심 재료를 얼마나 갖고 있는지
  3) 대체 재료 보너스 — 유사 재료로 부분 충족
  4) 실현 가능성 — 부족한 핵심 재료가 적을수록 유리
  5) 다양성 보장 — 상위 결과에서 카테고리 다양성 확보
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple


CATEGORY_WEIGHTS: Dict[str, float] = {
    "정육/계란": 3.0,
    "해산물": 3.0,
    "채소/과일": 2.0,
    "유제품": 2.0,
    "쌀/면/빵": 2.0,
    "가공식품": 1.5,
    "기타": 1.5,
    "소스/조미료/오일": 1.0,
}

PANTRY_STAPLES: Set[str] = {
    "소금",
    "설탕",
    "물",
    "식용유",
    "후추",
    "후춧가루",
    "참기름",
    "식초",
    "간장",
    "깨",
    "통깨",
}
PANTRY_WEIGHT = 0.3

SUBSTITUTION_GROUPS: List[Set[str]] = [
    {"대파", "쪽파", "파", "실파"},
    {"간장", "진간장", "국간장", "양조간장", "맛간장"},
    {"식용유", "카놀라유", "포도씨유", "올리브유", "해바라기유"},
    {"고추", "풋고추", "청양고추", "홍고추", "꽈리고추"},
    {"고춧가루", "고추가루", "굵은 고춧가루"},
    {"마늘", "다진 마늘", "깐마늘", "마늘편"},
    {"설탕", "흑설탕", "백설탕", "황설탕"},
    {"소금", "천일염", "꽃소금", "맛소금"},
    {"후추", "후춧가루", "통후추", "흰후추"},
    {"된장", "쌈장"},
    {"우유", "저지방우유"},
    {"참기름", "들기름"},
    {"양배추", "적양배추"},
    {"팽이버섯", "새송이버섯", "표고버섯", "느타리버섯", "양송이버섯"},
    {"계란", "달걀", "유정란"},
    {"두부", "부침두부", "찌개두부"},
    {"호박", "애호박", "단호박", "주키니"},
    {"고추장", "태양초고추장"},
    {"식초", "현미식초", "사과식초"},
    {"물엿", "올리고당", "조청"},
    {"무", "총각무", "알타리무"},
    {"밀가루", "강력분", "중력분", "박력분"},
    {"삼겹살", "대패삼겹", "오겹살"},
    {"닭고기", "닭가슴살", "닭다리", "닭날개", "닭봉"},
]

SUBSTITUTION_CREDIT = 0.6

_PREP_PREFIX_RE = re.compile(
    r"^(다진|깐|편|채\s*썬?|슬라이스|갈은|간|으깬|삶은|데친|볶은|구운"
    r"|말린|건|냉동|해동|불린|저민|얇게\s*썬?|굵게\s*썬?"
    r"|곱게\s*다진|굵게\s*다진|반으로\s*자른|한입\s*크기"
    r"|양념\s*|조림양념\s*|소스\s*|곁들임\s*|밑간\s*|고명\s*"
    r"|[\-·•]\s*양념\s*[::]\s*|[\-·•]\s*주재료\s*[::]\s*"
    r"|[\-·•]\s*부재료\s*[::]\s*|[\-·•]\s*소스\s*[::]\s*"
    r"|[\-·•]\s*곁들이\s*[::]\s*|필수\s*재료\s*[::]\s*"
    r")\s*"
)

INGREDIENT_HIERARCHY: Dict[str, Set[str]] = {
    "돼지고기": {"삼겹살", "대패삼겹", "오겹살", "목살", "앞다리", "뒷다리", "항정살", "갈매기살", "등갈비", "돼지갈비"},
    "소고기": {"등심", "안심", "갈비", "차돌박이", "불고기", "채끝", "부채살", "살치살", "양지", "사태"},
    "닭": {"닭고기", "닭가슴살", "닭다리", "닭날개", "닭봉"},
    "생선": {"고등어", "갈치", "삼치", "연어", "참치", "광어", "우럭"},
}
HIERARCHY_CREDIT = 0.7
PREFERRED_INGREDIENT_BONUS = 0.12
PREFERRED_CATEGORY_BONUS = 0.08
PREFERRED_KEYWORD_BONUS = 0.08
MAX_PERSONALIZATION_BONUS = 0.25


class RecipeRecommender:
    """
    보유 재료 기반 레시피 추천 엔진.

    초기화 시 DB 데이터를 받아 내부 인덱스를 구축하고,
    recommend() 호출로 추천 결과를 반환한다.
    """

    def __init__(
        self,
        recipes: Dict[str, dict],
        ingredients: Dict[str, dict],
        recipe_ingredients: Dict[str, List[dict]],
    ):
        self._recipes = recipes
        self._ingredients = ingredients
        self._recipe_ingr = recipe_ingredients

        self._ingr_name_map: Dict[str, str] = {}
        for iid, ingr in ingredients.items():
            self._ingr_name_map[iid] = ingr["ingredientName"]

        self._sub_index = self._build_substitution_index()
        self._prep_index = self._build_prep_index()
        self._hierarchy_index = self._build_hierarchy_index()
        self._ingr_frequency = self._compute_ingredient_frequency()

    def _build_substitution_index(self) -> Dict[str, Set[str]]:
        name_to_ids: Dict[str, List[str]] = defaultdict(list)
        for iid, ingr in self._ingredients.items():
            name_to_ids[ingr["ingredientName"]].append(iid)

        sub_index: Dict[str, Set[str]] = defaultdict(set)

        for group in SUBSTITUTION_GROUPS:
            group_ids: Set[str] = set()
            for name in group:
                for iid in name_to_ids.get(name, []):
                    group_ids.add(iid)

            for iid in group_ids:
                sub_index[iid] = group_ids - {iid}

        return dict(sub_index)

    def _build_prep_index(self) -> Dict[str, Set[str]]:
        name_to_ids: Dict[str, List[str]] = defaultdict(list)
        for iid, ingr in self._ingredients.items():
            name_to_ids[ingr["ingredientName"]].append(iid)

        prep_index: Dict[str, Set[str]] = {}

        for iid, ingr in self._ingredients.items():
            raw_name = ingr["ingredientName"]
            stripped = _PREP_PREFIX_RE.sub("", raw_name).strip()
            stripped = re.sub(r"\s*[::]\s*", "", stripped).strip()

            if stripped and stripped != raw_name and len(stripped) >= 2:
                base_ids = name_to_ids.get(stripped, [])
                if base_ids:
                    prep_index[iid] = set(base_ids)

        return prep_index

    def _build_hierarchy_index(self) -> Dict[str, Set[str]]:
        name_to_ids: Dict[str, List[str]] = defaultdict(list)
        for iid, ingr in self._ingredients.items():
            name_to_ids[ingr["ingredientName"]].append(iid)

        hier_index: Dict[str, Set[str]] = {}

        for parent_name, child_names in INGREDIENT_HIERARCHY.items():
            parent_ids = name_to_ids.get(parent_name, [])
            child_ids: Set[str] = set()
            for cn in child_names:
                child_ids.update(name_to_ids.get(cn, []))

            for pid in parent_ids:
                hier_index[pid] = child_ids

        return hier_index

    def _compute_ingredient_frequency(self) -> Dict[str, int]:
        freq: Counter = Counter()
        for ri_list in self._recipe_ingr.values():
            for ri in ri_list:
                freq[ri["ingredientId"]] += 1
        return dict(freq)

    def _get_weight(self, ingredient_id: str) -> float:
        ingr = self._ingredients.get(ingredient_id)
        if not ingr:
            return 1.0

        name = ingr["ingredientName"]
        if name in PANTRY_STAPLES:
            return PANTRY_WEIGHT

        category = ingr.get("category", "기타")
        base_weight = CATEGORY_WEIGHTS.get(category, 1.5)

        freq = self._ingr_frequency.get(ingredient_id, 0)
        total_recipes = len(self._recipes)
        if total_recipes > 1 and freq > 0:
            idf = math.log(total_recipes / freq)
            idf_factor = min(idf / math.log(total_recipes), 1.5)
        else:
            idf_factor = 1.0

        return base_weight * max(idf_factor, 0.5)

    def _is_core_ingredient(self, ingredient_id: str) -> bool:
        ingr = self._ingredients.get(ingredient_id)
        if not ingr:
            return False
        if ingr["ingredientName"] in PANTRY_STAPLES:
            return False
        category = ingr.get("category", "")
        return category in ("정육/계란", "해산물", "채소/과일", "유제품", "쌀/면/빵")

    def _find_substitution(self, missing_id: str, owned_ids: Set[str]) -> Optional[Tuple[str, float]]:
        subs = self._sub_index.get(missing_id, set())
        for sub_id in subs:
            if sub_id in owned_ids:
                return (sub_id, SUBSTITUTION_CREDIT)

        prep_bases = self._prep_index.get(missing_id, set())
        for base_id in prep_bases:
            if base_id in owned_ids:
                return (base_id, 0.85)

        child_ids = self._hierarchy_index.get(missing_id, set())
        for child_id in child_ids:
            if child_id in owned_ids:
                return (child_id, HIERARCHY_CREDIT)

        return None

    def _score_recipe(self, recipe_id: str, owned_ids: Set[str]) -> Optional[Dict[str, Any]]:
        recipe = self._recipes.get(recipe_id)
        if not recipe:
            return None

        ri_list = self._recipe_ingr.get(recipe_id, [])
        if not ri_list:
            return None

        recipe_ingr_ids = {ri["ingredientId"] for ri in ri_list}
        if not recipe_ingr_ids:
            return None

        matched_ids: Set[str] = owned_ids & recipe_ingr_ids
        missing_ids: Set[str] = recipe_ingr_ids - owned_ids

        substituted: Dict[str, Tuple[str, float]] = {}
        still_missing: Set[str] = set()

        for mid in missing_ids:
            sub = self._find_substitution(mid, owned_ids)
            if sub:
                substituted[mid] = sub
            else:
                still_missing.add(mid)

        if not matched_ids and not substituted:
            return None

        total_weight = 0.0
        matched_weight = 0.0
        substituted_weight = 0.0

        core_total = 0
        core_matched = 0

        for iid in recipe_ingr_ids:
            w = self._get_weight(iid)
            total_weight += w

            is_core = self._is_core_ingredient(iid)
            if is_core:
                core_total += 1

            if iid in matched_ids:
                matched_weight += w
                if is_core:
                    core_matched += 1
            elif iid in substituted:
                _, credit = substituted[iid]
                substituted_weight += w * credit
                if is_core:
                    core_matched += 1

        if total_weight == 0:
            return None

        weighted_match = (matched_weight + substituted_weight) / total_weight
        core_coverage = core_matched / core_total if core_total > 0 else 1.0
        missing_core = sum(1 for iid in still_missing if self._is_core_ingredient(iid))
        feasibility = 1.0 - (missing_core / max(core_total, 1))
        simplicity = 1.0 / (1.0 + math.log1p(len(recipe_ingr_ids)))

        score = 0.45 * weighted_match + 0.25 * core_coverage + 0.20 * feasibility + 0.10 * simplicity

        matched_list = self._build_ingredient_list(matched_ids)
        missing_list = self._build_ingredient_list(still_missing)
        substituted_list = [
            {
                "missing": self._ingr_name_map.get(mid, mid),
                "substitutedBy": self._ingr_name_map.get(sid, sid),
            }
            for mid, (sid, _) in substituted.items()
        ]

        simple_match_rate = len(matched_ids) / len(recipe_ingr_ids)

        return {
            "recipeId": recipe_id,
            "name": recipe["name"],
            "category": recipe.get("category", ""),
            "cookingMethod": recipe.get("cookingMethod", ""),
            "cookingMethodCode": recipe.get("cookingMethodCode", ""),
            "imageUrl": recipe.get("imageUrl", ""),
            "score": round(score, 4),
            "matchRate": round(simple_match_rate, 4),
            "weightedMatchRate": round(weighted_match, 4),
            "coreCoverage": round(core_coverage, 4),
            "feasibility": round(feasibility, 4),
            "matchedIngredients": matched_list,
            "missingIngredients": missing_list,
            "substitutions": substituted_list,
            "totalIngredientCount": len(recipe_ingr_ids),
            "missingCount": len(still_missing),
        }

    def _build_ingredient_list(self, ids: Set[str]) -> List[Dict[str, str]]:
        result = []
        for iid in ids:
            ingr = self._ingredients.get(iid)
            if ingr:
                result.append(
                    {
                        "ingredientId": iid,
                        "ingredientName": ingr["ingredientName"],
                        "category": ingr.get("category", ""),
                    }
                )
        return result

    def recommend(
        self,
        ingredient_ids: List[str],
        *,
        top_k: int = 10,
        category: Optional[str] = None,
        cooking_method: Optional[str] = None,
        min_score: float = 0.0,
        min_match_rate: float = 0.0,
        preferred_ingredient_ids: Optional[List[str]] = None,
        blocked_ingredient_ids: Optional[List[str]] = None,
        preferred_categories: Optional[List[str]] = None,
        excluded_categories: Optional[List[str]] = None,
        preferred_keywords: Optional[List[str]] = None,
        excluded_keywords: Optional[List[str]] = None,
        diversity: bool = True,
    ) -> List[Dict[str, Any]]:
        owned = set(ingredient_ids)
        preferred_ingredient_set = set(preferred_ingredient_ids or [])
        blocked_ingredient_set = set(blocked_ingredient_ids or [])
        preferred_category_set = {value.strip() for value in preferred_categories or [] if value.strip()}
        excluded_category_set = {value.strip() for value in excluded_categories or [] if value.strip()}
        preferred_keyword_set = {self._normalize_keyword(value) for value in preferred_keywords or [] if value.strip()}
        excluded_keyword_set = {self._normalize_keyword(value) for value in excluded_keywords or [] if value.strip()}
        candidates: List[Dict[str, Any]] = []

        for recipe_id, recipe in self._recipes.items():
            if category and recipe.get("category", "") != category:
                continue
            if excluded_category_set and recipe.get("category", "") in excluded_category_set:
                continue

            if cooking_method and not self._matches_cooking_method(recipe, cooking_method):
                continue

            scored = self._score_recipe(recipe_id, owned)
            if scored is None:
                continue
            recipe_ingredient_ids = {
                ingredient["ingredientId"]
                for ingredient in scored.get("matchedIngredients", []) + scored.get("missingIngredients", [])
                if ingredient.get("ingredientId")
            }
            if blocked_ingredient_set and recipe_ingredient_ids.intersection(blocked_ingredient_set):
                continue
            if excluded_keyword_set and self._recipe_matches_keywords(recipe, excluded_keyword_set):
                continue

            personalization_bonus = self._compute_personalization_bonus(
                recipe=recipe,
                recipe_ingredient_ids=recipe_ingredient_ids,
                preferred_ingredient_ids=preferred_ingredient_set,
                preferred_categories=preferred_category_set,
                preferred_keywords=preferred_keyword_set,
            )
            if personalization_bonus:
                scored["score"] = round(min(scored["score"] + personalization_bonus, 1.0), 4)
                scored["personalizationBonus"] = round(personalization_bonus, 4)

            if scored["score"] < min_score:
                continue
            if scored["matchRate"] < min_match_rate:
                continue

            candidates.append(scored)

        candidates.sort(key=lambda r: -r["score"])

        if diversity and len(candidates) > top_k:
            return self._diversify(candidates, top_k)

        return candidates[:top_k]

    @staticmethod
    def _normalize_keyword(value: str) -> str:
        return re.sub(r"\s+", "", value).strip().casefold()

    def _recipe_matches_keywords(self, recipe: dict, keywords: Set[str]) -> bool:
        if not keywords:
            return False
        haystack = self._normalize_keyword(
            " ".join(
                [
                    str(recipe.get("name", "")),
                    str(recipe.get("category", "")),
                    str(recipe.get("cookingMethod", "")),
                ]
            )
        )
        return any(keyword and keyword in haystack for keyword in keywords)

    def _compute_personalization_bonus(
        self,
        *,
        recipe: dict,
        recipe_ingredient_ids: Set[str],
        preferred_ingredient_ids: Set[str],
        preferred_categories: Set[str],
        preferred_keywords: Set[str],
    ) -> float:
        bonus = 0.0

        if preferred_ingredient_ids:
            preferred_hits = len(recipe_ingredient_ids.intersection(preferred_ingredient_ids))
            if preferred_hits > 0:
                ingredient_bonus = preferred_hits / len(preferred_ingredient_ids)
                bonus += PREFERRED_INGREDIENT_BONUS * ingredient_bonus

        if preferred_categories and recipe.get("category", "") in preferred_categories:
            bonus += PREFERRED_CATEGORY_BONUS

        if preferred_keywords and self._recipe_matches_keywords(recipe, preferred_keywords):
            bonus += PREFERRED_KEYWORD_BONUS

        return min(bonus, MAX_PERSONALIZATION_BONUS)

    @staticmethod
    def _matches_cooking_method(recipe: dict, method: str) -> bool:
        m = method.strip()
        r_method = recipe.get("cookingMethod", "")
        r_code = recipe.get("cookingMethodCode", "")
        return m == r_method or m.upper() == r_code.upper()

    @staticmethod
    def _diversify(candidates: List[Dict[str, Any]], top_k: int) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        cat_count: Counter = Counter()
        remaining = list(candidates)
        max_per_cat = max(3, top_k // 3)

        while remaining and len(result) < top_k:
            picked = False
            for i, cand in enumerate(remaining):
                cat = cand.get("category", "")
                if cat_count[cat] < max_per_cat:
                    result.append(cand)
                    cat_count[cat] += 1
                    remaining.pop(i)
                    picked = True
                    break

            if not picked:
                result.append(remaining.pop(0))

        return result

    @staticmethod
    def explain(recommendation: Dict[str, Any]) -> str:
        name = recommendation["name"]
        matched = recommendation["matchedIngredients"]
        missing = recommendation["missingIngredients"]
        subs = recommendation.get("substitutions", [])
        score = recommendation["score"]

        matched_names = [m["ingredientName"] for m in matched[:4]]
        matched_str = ", ".join(matched_names)
        if len(matched) > 4:
            matched_str += f" 외 {len(matched) - 4}개"

        parts = [f"[{name}] 추천 점수 {score:.0%}"]
        parts.append(f"보유 재료: {matched_str}")

        if subs:
            sub_strs = [f"{s['missing']}→{s['substitutedBy']}" for s in subs[:2]]
            parts.append(f"대체 가능: {', '.join(sub_strs)}")

        if missing:
            miss_names = [m["ingredientName"] for m in missing[:3]]
            miss_str = ", ".join(miss_names)
            if len(missing) > 3:
                miss_str += f" 외 {len(missing) - 3}개"
            parts.append(f"부족: {miss_str}")
        else:
            parts.append("모든 재료 보유!")

        return " | ".join(parts)
