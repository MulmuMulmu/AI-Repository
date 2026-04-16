"""recipes_all.json → ERD 4테이블(Recipe, Ingredient, RecipeIngredient, RecipeStep) 변환."""
import json, uuid, re
from pathlib import Path

DATA_DIR = Path("data")
RECIPE_DIR = DATA_DIR / "recipes"
DB_DIR = DATA_DIR / "db"
DB_DIR.mkdir(parents=True, exist_ok=True)

# ── 재료명 정리 패턴 ──
_PREFIX_RE = re.compile(
    r"^[-·•]\s*(?:양념|곁들임|곁들임채소|소스|고명|부재료|토핑|주재료|드레싱|반죽|육수|장식|속재료|튀김옷)\s*[::]\s*"
)
_BRACKET_RE = re.compile(r"^\[.*?\]\s*")
_JUNK_RE = re.compile(
    r"^(약간|적당량|조금|적량|소량)$"
    r"|^\d+[gG]?$|^\d+ml$|^\d+cc$|^\d+인분"
    r"|^재료\s|^주재료$|^고명$|^소스$|^양념장$|^드레싱$"
)

def clean_ingredient_name(name: str) -> str:
    s = _PREFIX_RE.sub("", name).strip()
    s = _BRACKET_RE.sub("", s).strip()
    return s


# ── 수량·단위 파싱 ──
_UNITS = (
    r"g|kg|ml|mL|L|cc|dl"
    r"|컵|큰술|작은술|T|Ts|ts|tsp|tbsp"
    r"|개|마리|줄기|장|모|쪽|뿌리|근|봉지|캔|팩|조각|cm|통|알|포기"
    r"|단|묶음|줌|톨|토막|다발|꼬집|숟가락|스푼|C|cup"
)
_AMT_RE = re.compile(
    rf"(\d+(?:\.\d+)?)\s*/\s*(\d+)\s*({_UNITS})"   # 1/2개
    rf"|(\d+(?:\.\d+)?)\s*({_UNITS})"                # 200g
    rf"|(½|¼|¾|⅓|⅔)\s*({_UNITS})?"                  # ½개
)
_FRAC_MAP = {"½": 0.5, "¼": 0.25, "¾": 0.75, "⅓": 0.333, "⅔": 0.667}
_DESC_RE = re.compile(r"(약간|적당량|조금|적량|소량)")

def parse_amount_unit(segment: str) -> tuple:
    if not segment:
        return 0.0, ""
    m = _AMT_RE.search(segment)
    if m:
        if m.group(1) is not None:
            return round(float(m.group(1)) / float(m.group(2)), 4), m.group(3)
        if m.group(4) is not None:
            return float(m.group(4)), m.group(5)
        if m.group(6) is not None:
            return _FRAC_MAP.get(m.group(6), 0.0), m.group(7) or ""
    m2 = _DESC_RE.search(segment)
    if m2:
        return 0.0, m2.group(1)
    return 0.0, ""

def find_amount_for(name: str, raw_text: str) -> tuple:
    """재료명으로 raw 텍스트에서 수량·단위를 찾는다."""
    if not raw_text or not name:
        return 0.0, ""
    clean = clean_ingredient_name(name)
    if not clean:
        return 0.0, ""
    idx = raw_text.find(clean)
    if idx == -1:
        return 0.0, ""
    after = raw_text[idx + len(clean): idx + len(clean) + 50]
    return parse_amount_unit(after)


# ── 카테고리 사전 로드 ──
cat_path = DATA_DIR / "labels" / "unified_ingredients.json"
ingr_cat_map = {}
if cat_path.exists():
    with open(cat_path, "r", encoding="utf-8") as f:
        for item in json.load(f):
            ingr_cat_map[item["name"]] = item.get("category", "기타")


# ── 메인 변환 ──
def transform():
    with open(RECIPE_DIR / "recipes_all.json", "r", encoding="utf-8") as f:
        recipes_raw = json.load(f)

    recipes = []
    ingredients_map = {}       # clean_name → dict
    recipe_ingredients = []
    recipe_steps = []

    for r in recipes_raw:
        recipe_id = str(uuid.uuid4())

        recipes.append({
            "recipeId": recipe_id,
            "name": r.get("title", "").strip(),
            "category": r.get("category", "").strip(),
            "cookingMethod": r.get("cooking_method", "").strip(),
            "cookingMethodCode": r.get("cooking_method_code", "").strip(),
            "imageUrl": "",
        })

        for s in r.get("steps", []):
            desc = s.get("description", "").strip()
            if not desc:
                continue
            recipe_steps.append({
                "recipeStepId": str(uuid.uuid4()),
                "recipeId": recipe_id,
                "stepOrder": s.get("step", 0),
                "description": desc,
            })

        raw_text = r.get("ingredients_raw", "")
        for ingr_name in r.get("ingredients", []):
            clean = clean_ingredient_name(ingr_name)
            if not clean or _JUNK_RE.match(clean):
                continue

            if clean not in ingredients_map:
                cat = ingr_cat_map.get(ingr_name,
                      ingr_cat_map.get(clean, "기타"))
                ingredients_map[clean] = {
                    "ingredientId": str(uuid.uuid4()),
                    "ingredientName": clean,
                    "category": cat,
                }

            amount, unit = find_amount_for(ingr_name, raw_text)

            recipe_ingredients.append({
                "recipeIngredientId": str(uuid.uuid4()),
                "recipeId": recipe_id,
                "ingredientId": ingredients_map[clean]["ingredientId"],
                "amount": amount,
                "unit": unit,
            })

    def save(data, name):
        p = DB_DIR / name
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"  {name}: {len(data)}건")

    print("\n[변환 결과]")
    save(recipes, "recipes.json")
    save(list(ingredients_map.values()), "ingredients.json")
    save(recipe_ingredients, "recipe_ingredients.json")
    save(recipe_steps, "recipe_steps.json")

    parsed = sum(1 for ri in recipe_ingredients if ri["amount"] > 0 or ri["unit"])
    print(f"\n  수량 파싱 성공: {parsed}/{len(recipe_ingredients)} "
          f"({parsed/len(recipe_ingredients)*100:.1f}%)")


if __name__ == "__main__":
    transform()
