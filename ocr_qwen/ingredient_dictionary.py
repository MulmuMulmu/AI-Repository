from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
import json
from pathlib import Path
import re


EXACT_NOISE = {
    "다진",
    "빨간",
    "송송",
    "채",
    "냉동",
    "실온",
    "아기",
    "코인",
    "노란",
    "고운",
}

ALIAS_MAP = {
    "달걀": "계란",
    "다진마늘": "마늘",
    "다진대파": "대파",
    "다진파": "대파",
    "다진양파": "양파",
    "쪽파": "대파",
    "파": "대파",
    "홍고추": "고추",
    "청고추": "고추",
    "청양고추": "고추",
    "저염간장": "간장",
    "고추가루": "고춧가루",
    "후추가루": "후추",
    "후춧가루": "후추",
    "케찹": "케첩",
    "통깨": "깨",
    "참깨": "깨",
    "통깨약간": "깨",
    "참깨약간": "깨",
    "깨소금": "깨",
    "다진파슬리": "파슬리",
    "파슬리가루": "파슬리",
    "들깨가루": "들깨",
    "생강가루": "생강",
    "카레가루": "카레",
    "전분가루": "전분",
    "김가루": "김",
    "슬라이스치즈": "치즈",
    "체다슬라이스치즈": "치즈",
    "파마산치즈가루": "치즈",
    "쌀밥": "밥",
    "크래미": "맛살",
}

CATEGORY_RULES: list[tuple[re.Pattern[str], tuple[str, str, int, int]]] = [
    (re.compile(r"계란"), ("egg", "refrigerated", 21, 5)),
    (re.compile(r"우유|치즈|버터|요거트|생크림"), ("dairy", "refrigerated", 10, 3)),
    (re.compile(r"소고기|돼지고기|닭고기|닭가슴살|닭다리살|닭봉|삼겹살|대패삼겹살|우삼겹|차돌박이|베이컨|햄|스팸|소시지|고기"), ("meat", "refrigerated", 3, 1)),
    (re.compile(r"새우|오징어|멸치|굴|연어|참치|고등어|어묵|맛살|크래미"), ("seafood", "refrigerated", 2, 1)),
    (re.compile(r"두부|순두부"), ("tofu_bean", "refrigerated", 5, 2)),
    (re.compile(r"버섯"), ("mushroom", "refrigerated", 4, 2)),
    (re.compile(r"호두|아몬드|견과"), ("nut", "room", 90, 14)),
    (re.compile(r"사과|레몬|딸기|바나나|토마토|아보카도"), ("fruit", "refrigerated", 5, 2)),
    (re.compile(r"양파|대파|마늘|감자|고구마|당근|오이|김치|깻잎|부추|브로콜리|파프리카|고추|가지|무|상추|청경채|숙주|콩나물|애호박|양배추|시금치|미나리|봄동|알배추|새싹채소"), ("vegetable", "refrigerated", 7, 2)),
    (re.compile(r"쌀|밥|밀가루|박력분|부침가루|튀김가루|빵가루|소면|당면|떡|만두|식빵|모닝빵|또띠아|우동면|파스타면"), ("grain", "room", 180, 21)),
    (re.compile(r"간장|고추장|된장|설탕|소금|식초|참기름|올리고당|물엿|굴소스|맛술|미림|청주|액젓|카레|전분|식용유|올리브유|카놀라유|포도씨유|오일|기름|쌈장|케첩|고춧가루|후추|깨|꿀|알룰로스|매실액|매실청|요리당|머스타드|연겨자|쯔유|치킨스톡|코인육수|베이킹파우더|슈가파우더|다시다"), ("sauce", "room", 180, 30)),
    (re.compile(r"생수|소주|주스|음료"), ("beverage", "room", 180, 30)),
]


def canonicalize_ingredient_name(raw_name: str) -> str | None:
    text = re.sub(r"\([^)]*\)", "", raw_name or "")
    text = re.sub(r"^[●·]+", "", text).strip()
    text = re.sub(r"\s+", "", text).strip()
    if ":" in text:
        left, right = text.split(":", 1)
        if re.search(r"양념|소스|드레싱|재료", left):
            text = right.strip()
    if not text:
        return None
    text = re.sub(r"(약간|조금|톡톡)$", "", text).strip()
    if text in EXACT_NOISE:
        return None
    text = ALIAS_MAP.get(text, text)
    if text in EXACT_NOISE:
        return None
    return text


def classify_ingredient_name(name: str) -> dict[str, object]:
    for pattern, config in CATEGORY_RULES:
        if pattern.search(name):
            category, storage, shelf_life_days, share_threshold_days = config
            return {
                "category": category,
                "default_storage_type": storage,
                "shelf_life_days": shelf_life_days,
                "share_threshold_days": share_threshold_days,
            }
    return {
        "category": "other",
        "default_storage_type": "room",
        "shelf_life_days": 7,
        "share_threshold_days": 2,
    }


def build_ingredient_dictionary(recipes: Iterable[Mapping[str, object]]) -> dict[str, object]:
    raw_counter: Counter[str] = Counter()
    standard_counter: Counter[str] = Counter()
    alias_counter: Counter[tuple[str, str]] = Counter()
    normalized_recipes: list[dict[str, object]] = []
    skipped_raw = 0

    for recipe in recipes:
        raw_names = [str(name).strip() for name in recipe.get("ingredient_names", []) if str(name).strip()]
        normalized_names: list[str] = []
        seen_names: set[str] = set()
        for raw_name in raw_names:
            raw_counter[raw_name] += 1
            standard_name = canonicalize_ingredient_name(raw_name)
            if standard_name is None:
                skipped_raw += 1
                continue
            standard_counter[standard_name] += 1
            if raw_name != standard_name:
                alias_counter[(standard_name, raw_name)] += 1
            if standard_name not in seen_names:
                seen_names.add(standard_name)
                normalized_names.append(standard_name)

        normalized_recipe = dict(recipe)
        normalized_recipe["normalized_ingredient_names"] = normalized_names
        normalized_recipes.append(normalized_recipe)

    ordered_standard_names = [
        name
        for name, _ in sorted(standard_counter.items(), key=lambda item: (-item[1], item[0]))
    ]

    masters: list[dict[str, object]] = []
    standard_to_id: dict[str, int] = {}
    for idx, standard_name in enumerate(ordered_standard_names, start=1):
        standard_to_id[standard_name] = idx
        classification = classify_ingredient_name(standard_name)
        masters.append(
            {
                "id": idx,
                "standard_name": standard_name,
                "category": classification["category"],
                "default_storage_type": classification["default_storage_type"],
                "shelf_life_days": classification["shelf_life_days"],
                "observed_count": standard_counter[standard_name],
            }
        )

    aliases: list[dict[str, object]] = []
    for (standard_name, alias_name), count in sorted(alias_counter.items(), key=lambda item: (-item[1], item[0][1])):
        aliases.append(
            {
                "ingredient_id": standard_to_id[standard_name],
                "alias_name": alias_name,
                "alias_type": "recipe_source",
                "observed_count": count,
            }
        )

    shelf_life_rules = _build_shelf_life_rules(masters)

    return {
        "ingredient_master": masters,
        "ingredient_alias": aliases,
        "shelf_life_rule": shelf_life_rules,
        "normalized_recipes": normalized_recipes,
        "summary": {
            "unique_raw_ingredient_names": len(raw_counter),
            "unique_standard_ingredient_names": len(masters),
            "alias_entries": len(aliases),
            "skipped_raw_ingredient_names": skipped_raw,
        },
    }


def build_ingredient_lookup(
    ingredient_master: Iterable[Mapping[str, object]],
    ingredient_alias: Iterable[Mapping[str, object]],
) -> dict[str, dict[str, str]]:
    by_id = {
        int(item["id"]): {
            "standard_name": str(item["standard_name"]),
            "category": str(item["category"]),
            "storage_type": str(item["default_storage_type"]),
        }
        for item in ingredient_master
    }
    lookup: dict[str, dict[str, str]] = {}
    for record in by_id.values():
        lookup[record["standard_name"]] = dict(record)
    for alias in ingredient_alias:
        ingredient_id = int(alias["ingredient_id"])
        alias_name = str(alias["alias_name"])
        if ingredient_id not in by_id or not alias_name:
            continue
        lookup[alias_name] = dict(by_id[ingredient_id])
    return lookup


def load_ingredient_lookup(master_path: Path, alias_path: Path) -> dict[str, dict[str, str]]:
    masters = json.loads(master_path.read_text(encoding="utf-8"))
    aliases = json.loads(alias_path.read_text(encoding="utf-8"))
    return build_ingredient_lookup(masters, aliases)


def _build_shelf_life_rules(masters: Iterable[Mapping[str, object]]) -> list[dict[str, object]]:
    seen: set[tuple[str, str]] = set()
    rules: list[dict[str, object]] = []
    for master in masters:
        key = (str(master["category"]), str(master["default_storage_type"]))
        if key in seen:
            continue
        seen.add(key)
        sample = classify_ingredient_name(str(master["standard_name"]))
        rules.append(
            {
                "category": key[0],
                "storage_type": key[1],
                "shelf_life_days": sample["shelf_life_days"],
                "share_threshold_days": sample["share_threshold_days"],
            }
        )
    return sorted(rules, key=lambda item: (item["category"], item["storage_type"]))
