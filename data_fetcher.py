"""
식품명·레시피 데이터 수집 모듈 (공공데이터 전용)

6가지 공공 데이터에서 식품·식재료·레시피 데이터를 수집하여 JSON으로 저장한다.
  1) 식품의약품안전처 - 식품영양성분 DB API  (data.go.kr)
  2) 식품안전나라     - 조리식품 레시피 API  (COOKRCP01)
  3) EPIS(농림수산식품교육문화정보원) - 레시피 기본/재료/과정 DB
  4) 보성군           - 차 음식 및 디저트 정보  (data.go.kr CSV)
  5) 세계김치연구소   - 김치콘텐츠통합플랫폼 레시피  (data.go.kr + 스크래핑)
  6) 식품의약품안전처 - 식품영양성분DB 통합 자료집 (data.go.kr)
     → 548개 표준 레시피 기반 조리식품의 상세 영양성분 데이터

저작권이 있는 외부 레시피(만개의레시피 등)는 자동으로 필터링하여
공공기관 제공 레시피만 보존한다.

사용법:
  python data_fetcher.py --all                      # 전체 수집 + 병합
  python data_fetcher.py --mfds                     # 식약처 식품 DB만
  python data_fetcher.py --recipe-api               # 식품안전나라 레시피만
  python data_fetcher.py --epis                     # EPIS 레시피만
  python data_fetcher.py --boseong                  # 보성군 차 음식/디저트만
  python data_fetcher.py --kimchi                   # 세계김치연구소 김치 레시피만
  python data_fetcher.py --nutrition                # 식품영양성분DB 통합자료집만
  python data_fetcher.py --normalize                # 전체 레시피 정규화 + 중복 제거
  python data_fetcher.py --merge                    # 수집 결과 → 통합 라벨 생성
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Set

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

BASE_DIR = Path(__file__).resolve().parent
LABEL_DIR = BASE_DIR / "data" / "labels"
RECIPE_DIR = BASE_DIR / "data" / "recipes"
LABEL_DIR.mkdir(parents=True, exist_ok=True)
RECIPE_DIR.mkdir(parents=True, exist_ok=True)

# ─── 공통 유틸 ────────────────────────────────────────────

_CLEAN_RE = re.compile(r"[0-9.,()\[\]~·※●▶★☆\s]+$")
_PAREN_RE = re.compile(r"\(.*?\)")
_UNIT_RE = re.compile(
    r"\s*\d+[\s]*[gGmMlLkK㎏㎖㎘개입봉지팩컵장캔병알ea]*\s*$"
)
_DESC_SUFFIXES = re.compile(
    r"(추가\s*무관|생략\s*가능|취향껏|취향것|기준|또는.*|작은것|큰것|센티|정도|약간)$"
)


def _clean_name(name: str) -> str:
    """식품명에서 용량·괄호·기호·설명 등을 제거해 핵심 이름만 남긴다."""
    name = name.strip()
    name = _PAREN_RE.sub("", name)
    name = _UNIT_RE.sub("", name)
    name = _CLEAN_RE.sub("", name)
    name = _DESC_SUFFIXES.sub("", name)
    name = name.strip(" ·,.")
    return name


def _save_json(data: Any, path: Path) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path)


# ═══════════════════════════════════════════════════════════
# 1) 식품의약품안전처 - 식품영양성분 DB (공공데이터포털)
#    엔드포인트: FoodNtrCpntDbInfo02 (data.go.kr ID: 15127578)
# ═══════════════════════════════════════════════════════════

MFDS_API_URL = "http://apis.data.go.kr/1471000/FoodNtrCpntDbInfo02/getFoodNtrCpntDbInq02"
MFDS_PAGE_SIZE = 500


def fetch_mfds_foods(api_key: str, max_pages: int = 600) -> List[Dict[str, str]]:
    """
    식약처 식품영양성분 DB에서 식품명과 식품분류를 수집한다.
    API 키: https://www.data.go.kr/data/15127578/openapi.do 에서 발급
    """
    print("\n[1/2] 식품의약품안전처 API 수집 시작...")
    all_items: List[Dict[str, str]] = []
    seen: Set[str] = set()

    for page in range(1, max_pages + 1):
        params = {
            "serviceKey": api_key,
            "pageNo": str(page),
            "numOfRows": str(MFDS_PAGE_SIZE),
            "type": "json",
        }

        try:
            resp = requests.get(MFDS_API_URL, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  페이지 {page} 실패: {e}")
            break

        body = data.get("body", {})
        total = int(body.get("totalCount", 0))
        rows = body.get("items", [])

        if not rows:
            break

        for row in rows:
            raw_name = (row.get("FOOD_NM_KR") or "").strip()
            cat1 = (row.get("FOOD_CAT1_NM") or "").strip()
            cat2 = (row.get("FOOD_CAT2_NM") or "").strip()
            maker = (row.get("MAKER_NM") or "").strip()

            name = _clean_name(raw_name)
            if not name or len(name) < 2:
                continue
            if name in seen:
                continue
            seen.add(name)

            all_items.append({
                "name": name,
                "name_raw": raw_name,
                "group": cat1,
                "sub_group": cat2,
                "maker": maker,
                "source": "mfds",
            })

        print(f"  페이지 {page}: {len(rows)}건 (누적 {len(all_items)}, 전체 {total})")

        if page * MFDS_PAGE_SIZE >= total:
            break

        if page % 30 == 0:
            _save_json(all_items, LABEL_DIR / "mfds_foods.json")
            print(f"    중간 저장: {len(all_items)}건")

        time.sleep(0.3)

    path = _save_json(all_items, LABEL_DIR / "mfds_foods.json")
    print(f"  -> 저장 완료: {path} ({len(all_items)}건)")
    return all_items


# ═══════════════════════════════════════════════════════════
# 2) 식품안전나라 - 조리식품 레시피 DB (COOKRCP01)
#    http://openapi.foodsafetykorea.go.kr/api/{KEY}/COOKRCP01/json/1/1000
#    약 1,200건의 공공 레시피 (제목, 재료, 20단계 조리법, 이미지 등)
# ═══════════════════════════════════════════════════════════

RECIPE_API_BASE = "http://openapi.foodsafetykorea.go.kr/api"
RECIPE_API_SERVICE = "COOKRCP01"
RECIPE_PAGE_SIZE = 1000

# ── 저작권 레시피 필터링 ──────────────────────────────────
# 만개의레시피, 해먹남녀 등 상업적 저작권이 있는 출처 키워드
_COPYRIGHTED_SOURCES = re.compile(
    r"만개의\s*레시피|10000recipe|mangae|만개레시피"
    r"|해먹남녀|haemuknamnyeo"
    r"|쿡쿡TV|CookCookTV"
    r"|올리브채널|올리브TV"
    r"|집밥\s*백선생|백종원의"
    r"|냉장고를\s*부탁해"
    r"|삼시\s*세끼"
    r"|편스토랑|신상출시"
    r"|살림\s*9단\s*만물상"
    r"|수미네\s*반찬"
    r"|알토란\s*(레시피|에서|방송)",
    re.IGNORECASE,
)

_COPYRIGHTED_IMAGE_DOMAINS = re.compile(
    r"10000recipe\.com|mangae\.co|haemuk|wtable\.co\.kr",
    re.IGNORECASE,
)


def _is_copyrighted_recipe(row: Dict[str, Any]) -> bool:
    """상업적 저작권이 있는 레시피인지 판별한다."""
    fields_to_check = [
        row.get("RCP_NM", ""),
        row.get("HASH_TAG", ""),
        row.get("RCP_NA_TIP", ""),
        row.get("RCP_PARTS_DTLS", ""),
    ]
    for i in range(1, 21):
        fields_to_check.append(row.get(f"MANUAL{i:02d}", "") or "")

    combined = " ".join(str(f) for f in fields_to_check if f)

    if _COPYRIGHTED_SOURCES.search(combined):
        return True

    image_fields = [
        row.get("ATT_FILE_NO_MAIN", ""),
        row.get("ATT_FILE_NO_MK", ""),
    ]
    for i in range(1, 21):
        image_fields.append(row.get(f"MANUAL_IMG{i:02d}", "") or "")

    for url in image_fields:
        if url and _COPYRIGHTED_IMAGE_DOMAINS.search(str(url)):
            return True

    return False


_INGREDIENT_SPLIT = re.compile(r"[,\n·•|]")
_QUANTITY_RE = re.compile(
    r"\s*\d+[\s/~.]*\d*\s*"
    r"[gGmMlLkK㎏㎖컵큰술작은술숟갈T스푼줄기쪽통알개장봉근모cm약간적당량조금소량]*\s*$"
)


def _parse_ingredient_names(parts_text: str) -> List[str]:
    """RCP_PARTS_DTLS 필드에서 개별 재료명만 추출한다."""
    ingredients: List[str] = []
    chunks = _INGREDIENT_SPLIT.split(parts_text)
    for chunk in chunks:
        chunk = chunk.strip()
        chunk = _PAREN_RE.sub("", chunk)
        chunk = _QUANTITY_RE.sub("", chunk)
        chunk = re.sub(r"^[가-힣]*:", "", chunk)
        chunk = chunk.strip(" ·,.")
        if chunk and 1 < len(chunk) <= 20:
            ingredients.append(chunk)
    return ingredients


def _build_steps(row: Dict[str, Any]) -> List[Dict[str, Any]]:
    """MANUAL01~MANUAL20 필드에서 조리 단계를 구성한다."""
    steps = []
    for i in range(1, 21):
        key = f"MANUAL{i:02d}"
        img_key = f"MANUAL_IMG{i:02d}"
        text = (row.get(key) or "").strip()
        if not text:
            continue
        text = re.sub(r"^\d+[\.\)]\s*", "", text)
        step = {"step": len(steps) + 1, "description": text}
        img = (row.get(img_key) or "").strip()
        if img:
            step["image_url"] = img
        steps.append(step)
    return steps


def fetch_recipes(api_key: str | None = None) -> List[Dict[str, Any]]:
    """
    식품안전나라 COOKRCP01 API에서 전체 레시피를 수집하여
    data/recipes/recipes_public.json 과
    data/labels/recipe_api_ingredients.json 에 저장한다.

    api_key가 없으면 공개 sample 엔드포인트를 사용한다.
    """
    key = api_key or "sample"
    print("\n[2/2] 식품안전나라 레시피 API (COOKRCP01) 수집 시작...")
    if key == "sample":
        print("  ※ API 키 미설정 → 공개 sample 엔드포인트 사용")
    print("  ※ 저작권 레시피(만개의레시피 등) 자동 필터링 적용")

    all_recipes: List[Dict[str, Any]] = []
    all_ingredient_names: Set[str] = set()
    total_filtered = 0

    # 먼저 total_count 확인 (5건만 빠르게)
    probe_url = f"{RECIPE_API_BASE}/{key}/{RECIPE_API_SERVICE}/json/1/1"
    try:
        probe_resp = requests.get(probe_url, timeout=30)
        probe_text = probe_resp.text.strip()
        if probe_text.startswith("<") or "인증키" in probe_text:
            print("  [오류] 식품안전나라 인증키가 유효하지 않습니다.")
            print("  발급: https://www.foodsafetykorea.go.kr/api/userApiKey.do")
            return []
        probe_data = probe_resp.json()
        total_count = int(
            probe_data.get(RECIPE_API_SERVICE, {}).get("total_count", "0")
        )
    except Exception as e:
        print(f"  API 접속 실패: {e}")
        return []

    if total_count == 0:
        print("  레시피가 0건입니다.")
        return []

    print(f"  전체 레시피 수: {total_count}건")
    page = 0

    while True:
        page += 1
        start = (page - 1) * RECIPE_PAGE_SIZE + 1
        end = min(page * RECIPE_PAGE_SIZE, total_count)
        url = f"{RECIPE_API_BASE}/{key}/{RECIPE_API_SERVICE}/json/{start}/{end}"

        try:
            resp = requests.get(url, timeout=60)
            resp.raise_for_status()
            text = resp.text.strip()
            if text.startswith("<") or "인증키" in text:
                print("  [오류] API 인증 실패")
                break
            data = resp.json()
        except requests.exceptions.JSONDecodeError:
            print("  [오류] API 응답이 JSON이 아닙니다.")
            break
        except Exception as e:
            print(f"  페이지 {page} 실패: {e}")
            break

        result = data.get(RECIPE_API_SERVICE, {})
        if "RESULT" in result and result["RESULT"].get("CODE") != "INFO-000":
            code = result["RESULT"].get("CODE", "")
            msg = result["RESULT"].get("MSG", "")
            print(f"  API 오류: {code} - {msg}")
            break

        rows = result.get("row", [])
        if not rows:
            break

        filtered_count = 0
        for row in rows:
            if _is_copyrighted_recipe(row):
                filtered_count += 1
                continue

            parts_raw = (row.get("RCP_PARTS_DTLS") or "").strip()
            ingredient_names = _parse_ingredient_names(parts_raw)
            all_ingredient_names.update(ingredient_names)

            steps = _build_steps(row)

            recipe = {
                "id": (row.get("RCP_SEQ") or "").strip(),
                "title": (row.get("RCP_NM") or "").strip(),
                "category": (row.get("RCP_PAT2") or "").strip(),
                "cooking_method": (row.get("RCP_WAY2") or "").strip(),
                "servings": (row.get("INFO_WGT") or "").strip(),
                "calories": (row.get("INFO_ENG") or "").strip(),
                "carbs": (row.get("INFO_CAR") or "").strip(),
                "protein": (row.get("INFO_PRO") or "").strip(),
                "fat": (row.get("INFO_FAT") or "").strip(),
                "sodium": (row.get("INFO_NA") or "").strip(),
                "ingredients_raw": parts_raw,
                "ingredients": ingredient_names,
                "steps": steps,
                "image_url": (row.get("ATT_FILE_NO_MAIN") or "").strip(),
                "image_url_small": (row.get("ATT_FILE_NO_MK") or "").strip(),
                "hash_tag": (row.get("HASH_TAG") or "").strip(),
                "tip": (row.get("RCP_NA_TIP") or "").strip(),
                "source": "식품안전나라(식품의약품안전처)",
            }
            all_recipes.append(recipe)

        total_filtered += filtered_count
        print(
            f"  페이지 {page}: {len(rows)}건 (저작권 필터 {filtered_count}건 제거) "
            f"(누적 레시피 {len(all_recipes)}개, 재료 {len(all_ingredient_names)}개)"
        )

        if end >= total_count:
            break
        time.sleep(0.3)

    # 레시피 전체 저장 (공공기관 데이터만)
    recipe_path = _save_json(all_recipes, RECIPE_DIR / "recipes_public.json")
    print(f"  -> 레시피 저장: {recipe_path} ({len(all_recipes)}건)")
    if total_filtered > 0:
        print(f"  -> 저작권 필터링으로 제거된 레시피: {total_filtered}건")

    # 재료명 라벨 저장
    ingr_items = sorted([
        {"name": name, "source": "recipe_api"}
        for name in all_ingredient_names
    ], key=lambda x: x["name"])
    ingr_path = _save_json(ingr_items, LABEL_DIR / "recipe_api_ingredients.json")
    print(f"  -> 재료명 저장: {ingr_path} ({len(ingr_items)}개)")

    return all_recipes


# ═══════════════════════════════════════════════════════════
# 3) EPIS - 농림수산식품교육문화정보원 레시피 DB
#    http://211.237.50.150:7080/openapi/{KEY}/json/...
#    레시피 기본정보 + 재료정보 + 과정정보 (약 500건)
# ═══════════════════════════════════════════════════════════

EPIS_API_BASE = "http://211.237.50.150:7080/openapi"
EPIS_GRID_RECIPE = "Grid_20150827000000000226_1"
EPIS_GRID_IRDNT = "Grid_20150827000000000227_1"
EPIS_GRID_STEPS = "Grid_20150827000000000228_1"
EPIS_SAMPLE_LIMIT = 5
_EPIS_WORKERS = 20


def _epis_get(api_key: str, grid: str, start: int, end: int,
              params: str = "") -> List[Dict[str, Any]]:
    url = (
        f"{EPIS_API_BASE}/{api_key}/json/{grid}/{start}/{end}"
        + (f"?{params}" if params else "")
    )
    try:
        resp = requests.get(url, timeout=15)
        data = resp.json()
        grid_data = data.get(grid, {})
        result = grid_data.get("result", {})
        if result.get("code") != "INFO-000":
            return []
        return grid_data.get("row", [])
    except Exception:
        return []


def _epis_fetch_all_ids(api_key: str) -> List[int]:
    """모든 유효한 RECIPE_ID를 스캔한다."""
    found_ids: List[int] = []
    id_ranges = list(range(1, 541)) + list(range(180000, 181000))

    def _check(rid: int) -> int | None:
        rows = _epis_get(api_key, EPIS_GRID_RECIPE, 1, 1,
                         f"RECIPE_ID={rid}")
        return rid if rows else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=_EPIS_WORKERS) as ex:
        futures = {ex.submit(_check, rid): rid for rid in id_ranges}
        for fut in concurrent.futures.as_completed(futures):
            result = fut.result()
            if result is not None:
                found_ids.append(result)

    found_ids.sort()
    return found_ids


def _epis_fetch_recipe(api_key: str, rid: int) -> Dict[str, Any] | None:
    """단일 레시피의 기본정보 + 재료 + 과정을 수집한다."""
    basic_rows = _epis_get(api_key, EPIS_GRID_RECIPE, 1, 1,
                           f"RECIPE_ID={rid}")
    if not basic_rows:
        return None
    info = basic_rows[0]

    ingredients: List[Dict[str, str]] = []
    page = 0
    while True:
        page += 1
        start = (page - 1) * EPIS_SAMPLE_LIMIT + 1
        end = page * EPIS_SAMPLE_LIMIT
        rows = _epis_get(api_key, EPIS_GRID_IRDNT, start, end,
                         f"RECIPE_ID={rid}")
        for r in rows:
            ingredients.append({
                "name": (r.get("IRDNT_NM") or "").strip(),
                "amount": (r.get("IRDNT_CPCTY") or "").strip(),
                "type": (r.get("IRDNT_TY_NM") or "").strip(),
            })
        if len(rows) < EPIS_SAMPLE_LIMIT:
            break

    steps: List[Dict[str, Any]] = []
    page = 0
    while True:
        page += 1
        start = (page - 1) * EPIS_SAMPLE_LIMIT + 1
        end = page * EPIS_SAMPLE_LIMIT
        rows = _epis_get(api_key, EPIS_GRID_STEPS, start, end,
                         f"RECIPE_ID={rid}")
        for r in rows:
            steps.append({
                "step": int(r.get("COOKING_NO") or 0),
                "description": (r.get("COOKING_DC") or "").strip(),
                "tip": (r.get("STEP_TIP") or "").strip(),
            })
        if len(rows) < EPIS_SAMPLE_LIMIT:
            break
    steps.sort(key=lambda s: s["step"])

    return {
        "id": str(info.get("RECIPE_ID", "")),
        "title": (info.get("RECIPE_NM_KO") or "").strip(),
        "summary": (info.get("SUMRY") or "").strip(),
        "nation": (info.get("NATION_NM") or "").strip(),
        "category": (info.get("TY_NM") or "").strip(),
        "cooking_time": (info.get("COOKING_TIME") or "").strip(),
        "calories": (info.get("CALORIE") or "").strip(),
        "servings": (info.get("QNT") or "").strip(),
        "difficulty": (info.get("LEVEL_NM") or "").strip(),
        "ingredient_category": (info.get("IRDNT_CODE") or "").strip(),
        "price_range": (info.get("PC_NM") or "").strip(),
        "ingredients": ingredients,
        "ingredient_names": [i["name"] for i in ingredients if i["name"]],
        "steps": steps,
        "source": "EPIS(농림수산식품교육문화정보원)",
    }


def fetch_epis_recipes(api_key: str | None = None) -> List[Dict[str, Any]]:
    """
    EPIS 레시피 3종 API(기본정보·재료·과정)를 수집하여
    data/recipes/recipes_epis.json 에 저장한다.
    """
    key = api_key or "sample"
    print("\n[EPIS] 농림수산식품교육문화정보원 레시피 수집 시작...")
    if key == "sample":
        print("  ※ API 키 미설정 → 공개 sample 엔드포인트 사용 (개별 ID 조회)")

    print("  1단계: 유효 레시피 ID 스캔...")
    recipe_ids = _epis_fetch_all_ids(key)
    print(f"  -> {len(recipe_ids)}개 레시피 ID 발견")

    if not recipe_ids:
        print("  [오류] 레시피를 찾을 수 없습니다.")
        return []

    print(f"  2단계: 레시피 상세 수집 (기본정보 + 재료 + 과정)...")
    all_recipes: List[Dict[str, Any]] = []
    all_ingredient_names: Set[str] = set()
    done = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = {
            ex.submit(_epis_fetch_recipe, key, rid): rid
            for rid in recipe_ids
        }
        for fut in concurrent.futures.as_completed(futures):
            recipe = fut.result()
            done += 1
            if recipe:
                all_recipes.append(recipe)
                all_ingredient_names.update(recipe["ingredient_names"])
            if done % 50 == 0 or done == len(recipe_ids):
                print(
                    f"    진행: {done}/{len(recipe_ids)} "
                    f"(레시피 {len(all_recipes)}개, "
                    f"재료 {len(all_ingredient_names)}개)"
                )

    all_recipes.sort(key=lambda r: int(r["id"]))

    recipe_path = _save_json(all_recipes, RECIPE_DIR / "recipes_epis.json")
    print(f"  -> 레시피 저장: {recipe_path} ({len(all_recipes)}건)")

    ingr_items = sorted([
        {"name": name, "source": "epis_recipe"}
        for name in all_ingredient_names
    ], key=lambda x: x["name"])
    ingr_path = _save_json(ingr_items, LABEL_DIR / "epis_ingredients.json")
    print(f"  -> 재료명 저장: {ingr_path} ({len(ingr_items)}개)")

    return all_recipes


# ═══════════════════════════════════════════════════════════
# 4) 보성군 차 음식 및 디저트 정보 (data.go.kr 파일 데이터)
#    https://www.data.go.kr/data/15111850/fileData.do
#    390건의 차(녹차·홍차) 활용 음식·디저트 레시피
# ═══════════════════════════════════════════════════════════

BOSEONG_CSV_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do"
    "?atchFileId=FILE_000000002682012&fileDetailSn=1&insertDataPrcus=N"
)

_STEP_SPLIT_RE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭⑮]")


def _parse_boseong_steps(text: str) -> List[Dict[str, Any]]:
    """조리법 텍스트를 단계별로 분리한다."""
    parts = _STEP_SPLIT_RE.split(text)
    steps = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        steps.append({"step": len(steps) + 1, "description": part})
    if not steps and text.strip():
        steps.append({"step": 1, "description": text.strip()})
    return steps


def fetch_boseong_tea() -> List[Dict[str, Any]]:
    """
    보성군 차 음식 및 디저트 CSV를 다운로드하여
    data/recipes/recipes_boseong_tea.json 에 저장한다.
    """
    import csv
    import io

    print("\n[보성군] 차 음식 및 디저트 정보 수집 시작...")

    try:
        resp = requests.get(BOSEONG_CSV_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [오류] 다운로드 실패: {e}")
        return []

    raw = resp.content
    for enc in ("euc-kr", "cp949", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        print("  [오류] CSV 인코딩을 판별할 수 없습니다.")
        return []

    reader = csv.DictReader(io.StringIO(text))
    all_recipes: List[Dict[str, Any]] = []
    all_ingredient_names: Set[str] = set()

    for idx, row in enumerate(reader, start=1):
        title = (row.get("요리명") or "").strip()
        if not title:
            continue

        main_raw = (row.get("주재료") or "").strip()
        sub_raw = (row.get("부재료") or "").strip()
        cook_raw = (row.get("조리법") or row.get("조리법 ") or "").strip()
        desc = (row.get("상세설명") or "").strip()

        main_names = [
            _clean_name(n) for n in _INGREDIENT_SPLIT.split(main_raw) if n.strip()
        ]
        sub_names = [
            _clean_name(n) for n in _INGREDIENT_SPLIT.split(sub_raw) if n.strip()
        ]
        all_names = [n for n in main_names + sub_names if n and len(n) >= 2]
        all_ingredient_names.update(all_names)

        steps = _parse_boseong_steps(cook_raw)

        recipe = {
            "id": f"boseong_{idx}",
            "title": title,
            "category": "차 음식/디저트",
            "ingredients_main_raw": main_raw,
            "ingredients_sub_raw": sub_raw,
            "ingredients": all_names,
            "steps": steps,
            "description": desc,
            "source": "전라남도 보성군(공공데이터포털)",
        }
        all_recipes.append(recipe)

    recipe_path = _save_json(all_recipes, RECIPE_DIR / "recipes_boseong_tea.json")
    print(f"  -> 레시피 저장: {recipe_path} ({len(all_recipes)}건)")

    ingr_items = sorted([
        {"name": name, "source": "boseong_tea"}
        for name in all_ingredient_names
    ], key=lambda x: x["name"])
    ingr_path = _save_json(ingr_items, LABEL_DIR / "boseong_tea_ingredients.json")
    print(f"  -> 재료명 저장: {ingr_path} ({len(ingr_items)}개)")

    return all_recipes


# ═══════════════════════════════════════════════════════════
# 5) 세계김치연구소 - 김치콘텐츠통합플랫폼 레시피 (data.go.kr)
#    https://www.data.go.kr/data/15035943/fileData.do
#    116건 김치·김치응용요리 레시피 (재료+조리법 상세 스크래핑)
# ═══════════════════════════════════════════════════════════

KIMCHI_CSV_URL = (
    "https://www.data.go.kr/cmm/cmm/fileDownload.do"
    "?atchFileId=FILE_000000003110873&fileDetailSn=1&insertDataPrcus=N"
)


def _scrape_kimchi_recipe(link: str) -> Dict[str, Any]:
    """wikim.re.kr 레시피 상세 페이지에서 재료와 조리법을 추출한다."""
    result: Dict[str, Any] = {"ingredients": [], "steps": []}
    try:
        resp = requests.get(link, timeout=15)
        html = resp.text
    except Exception:
        return result

    names = re.findall(
        r'<strong\s+class="name">(.*?)</strong>', html, re.DOTALL
    )
    amounts = re.findall(
        r'<span\s+class="num">(.*?)</span>', html, re.DOTALL
    )
    for name_html, amt_html in zip(names, amounts):
        name = re.sub(r"<[^>]+>", "", name_html).strip()
        amt = re.sub(r"<[^>]+>", "", amt_html).strip()
        if name:
            result["ingredients"].append({"name": name, "amount": amt})

    step_block = re.search(
        r'class="con-box\s+step">(.*?)(?:</div>\s*</div>|<div\s+class="con-box)',
        html, re.DOTALL,
    )
    if step_block:
        step_texts = re.findall(r"<li[^>]*>(.*?)</li>", step_block.group(1), re.DOTALL)
        for idx, st in enumerate(step_texts, 1):
            text = re.sub(r"<[^>]+>", " ", st).strip()
            text = re.sub(r"\s+", " ", text).strip()
            if text and text != "완성":
                result["steps"].append({"step": idx, "description": text})

    return result


def fetch_kimchi_recipes() -> List[Dict[str, Any]]:
    """
    세계김치연구소 김치콘텐츠통합플랫폼 레시피 CSV를 다운로드하고
    각 레시피 상세 페이지에서 재료·조리법을 스크래핑하여
    data/recipes/recipes_kimchi.json 에 저장한다.
    """
    import csv
    import io

    print("\n[김치연구소] 김치콘텐츠통합플랫폼 레시피 수집 시작...")

    try:
        resp = requests.get(KIMCHI_CSV_URL, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [오류] CSV 다운로드 실패: {e}")
        return []

    raw = resp.content
    for enc in ("euc-kr", "cp949", "utf-8-sig", "utf-8"):
        try:
            text = raw.decode(enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    else:
        print("  [오류] CSV 인코딩을 판별할 수 없습니다.")
        return []

    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    print(f"  CSV 로드: {len(rows)}건")

    all_recipes: List[Dict[str, Any]] = []
    all_ingredient_names: Set[str] = set()

    print("  상세 페이지 스크래핑 중...")

    def _fetch_one(row: Dict[str, str]) -> Dict[str, Any] | None:
        title = (row.get("레시피 제목") or "").strip()
        link = (row.get("링크") or "").strip()
        keywords = (row.get("키워드") or "").strip()
        if not title:
            return None
        detail = _scrape_kimchi_recipe(link) if link else {
            "ingredients": [], "steps": []
        }
        return {
            "title": title,
            "link": link,
            "keywords": keywords,
            "source_org": (row.get("제작기관") or "").strip(),
            "ingredients": detail["ingredients"],
            "ingredient_names": [
                i["name"] for i in detail["ingredients"] if i["name"]
            ],
            "steps": detail["steps"],
            "source": "세계김치연구소(김치콘텐츠통합플랫폼)",
        }

    done = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        futures = {ex.submit(_fetch_one, row): row for row in rows}
        for fut in concurrent.futures.as_completed(futures):
            recipe = fut.result()
            done += 1
            if recipe:
                recipe["id"] = f"kimchi_{len(all_recipes) + 1}"
                all_recipes.append(recipe)
                all_ingredient_names.update(recipe["ingredient_names"])
            if done % 20 == 0 or done == len(rows):
                print(
                    f"    진행: {done}/{len(rows)} "
                    f"(레시피 {len(all_recipes)}개, "
                    f"재료 {len(all_ingredient_names)}개)"
                )

    all_recipes.sort(key=lambda r: r["id"])

    recipe_path = _save_json(all_recipes, RECIPE_DIR / "recipes_kimchi.json")
    print(f"  -> 레시피 저장: {recipe_path} ({len(all_recipes)}건)")

    ingr_items = sorted([
        {"name": name, "source": "kimchi_wikim"}
        for name in all_ingredient_names
    ], key=lambda x: x["name"])
    ingr_path = _save_json(ingr_items, LABEL_DIR / "kimchi_ingredients.json")
    print(f"  -> 재료명 저장: {ingr_path} ({len(ingr_items)}개)")

    return all_recipes


# ═══════════════════════════════════════════════════════════
# 6) 식품의약품안전처 - 식품영양성분DB 통합 자료집
#    data.go.kr API: FoodNtrCpntDbInfo02 (ID 15127578)
#    548개 표준 레시피 기반 조리식품의 상세 영양성분 (157개 성분)
# ═══════════════════════════════════════════════════════════

_NUTRITION_FIELD_MAP: Dict[str, Dict[str, str]] = {
    "AMT_NUM1":  {"name": "에너지", "unit": "kcal"},
    "AMT_NUM2":  {"name": "수분", "unit": "g"},
    "AMT_NUM3":  {"name": "단백질", "unit": "g"},
    "AMT_NUM4":  {"name": "지방", "unit": "g"},
    "AMT_NUM5":  {"name": "회분", "unit": "g"},
    "AMT_NUM6":  {"name": "탄수화물", "unit": "g"},
    "AMT_NUM7":  {"name": "당류", "unit": "g"},
    "AMT_NUM8":  {"name": "식이섬유", "unit": "g"},
    "AMT_NUM9":  {"name": "칼슘", "unit": "mg"},
    "AMT_NUM10": {"name": "철", "unit": "mg"},
    "AMT_NUM11": {"name": "인", "unit": "mg"},
    "AMT_NUM12": {"name": "칼륨", "unit": "mg"},
    "AMT_NUM13": {"name": "나트륨", "unit": "mg"},
    "AMT_NUM14": {"name": "비타민A", "unit": "μg RAE"},
    "AMT_NUM15": {"name": "레티놀", "unit": "μg"},
    "AMT_NUM16": {"name": "베타카로틴", "unit": "μg"},
    "AMT_NUM17": {"name": "티아민", "unit": "mg"},
    "AMT_NUM18": {"name": "리보플라빈", "unit": "mg"},
    "AMT_NUM19": {"name": "니아신", "unit": "mg"},
    "AMT_NUM20": {"name": "비타민C", "unit": "mg"},
    "AMT_NUM21": {"name": "비타민D", "unit": "μg"},
    "AMT_NUM22": {"name": "콜레스테롤", "unit": "mg"},
    "AMT_NUM23": {"name": "포화지방산", "unit": "g"},
    "AMT_NUM24": {"name": "트랜스지방산", "unit": "g"},
}

_NUTRITION_SUMMARY_KEYS = [
    "AMT_NUM1", "AMT_NUM3", "AMT_NUM4", "AMT_NUM6",
    "AMT_NUM7", "AMT_NUM8", "AMT_NUM13", "AMT_NUM22",
    "AMT_NUM23", "AMT_NUM24",
]


def _parse_nutrition(item: Dict[str, Any]) -> Dict[str, Any]:
    """API 응답 1건을 정제된 영양성분 dict로 변환한다."""
    nutrients: Dict[str, Any] = {}
    for key, meta in _NUTRITION_FIELD_MAP.items():
        raw = (item.get(key) or "").strip().replace(",", "")
        if not raw:
            continue
        try:
            nutrients[meta["name"]] = {
                "value": float(raw),
                "unit": meta["unit"],
            }
        except ValueError:
            pass

    summary = {}
    for key in _NUTRITION_SUMMARY_KEYS:
        raw = (item.get(key) or "").strip().replace(",", "")
        if raw:
            try:
                meta = _NUTRITION_FIELD_MAP[key]
                summary[meta["name"]] = f"{float(raw)}{meta['unit']}"
            except ValueError:
                pass

    food_name = (item.get("FOOD_NM_KR") or "").strip()
    base_name = food_name.split("_")[0] if "_" in food_name else food_name
    sub_name = food_name.split("_", 1)[1] if "_" in food_name else ""

    return {
        "food_code": (item.get("FOOD_CD") or "").strip(),
        "title": food_name,
        "base_name": base_name,
        "sub_name": sub_name,
        "category": (item.get("FOOD_CAT1_NM") or "").strip(),
        "sub_category": (item.get("FOOD_REF_NM") or "").strip(),
        "serving_size": (item.get("SERVING_SIZE") or "").strip(),
        "food_weight": (item.get("Z10500") or "").strip(),
        "data_source": (item.get("SUB_REF_NAME") or "").strip(),
        "analysis_method": (item.get("CRT_MTH_NM") or "").strip(),
        "nutrients": nutrients,
        "nutrition_summary": summary,
        "source": "식품의약품안전처(식품영양성분DB 통합자료집)",
    }


def fetch_nutrition_recipes(api_key: str) -> List[Dict[str, Any]]:
    """
    식품영양성분DB 통합 자료집 데이터를 수집한다.

    '가정식(분석 함량)' + '품목대표' 항목만 필터링하여
    표준 레시피 기반 조리식품 ~500건의 상세 영양성분을 저장한다.
    """
    print("\n[영양성분DB] 식품영양성분DB 통합 자료집 수집 시작...")
    url = MFDS_API_URL
    all_items: List[Dict[str, Any]] = []
    all_food_names: Set[str] = set()

    page = 0
    found_target = False

    while True:
        page += 1
        params = {
            "serviceKey": api_key,
            "pageNo": str(page),
            "numOfRows": str(MFDS_PAGE_SIZE),
            "type": "json",
        }
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  페이지 {page} 실패: {e}")
            break

        body = data.get("body", {})
        rows = body.get("items", [])
        if not rows:
            break

        target_rows = [
            r for r in rows
            if r.get("FOOD_OR_NM") == "가정식(분석 함량)"
            and r.get("DB_CLASS_NM") == "품목대표"
        ]

        if target_rows:
            found_target = True
        elif found_target:
            break

        for row in target_rows:
            parsed = _parse_nutrition(row)
            if not parsed["title"]:
                continue
            all_items.append(parsed)
            name = _clean_name(parsed["title"])
            if name and len(name) >= 2:
                all_food_names.add(name)

        print(
            f"  페이지 {page}: {len(rows)}건 중 통합자료집 {len(target_rows)}건 "
            f"(누적 {len(all_items)}건)"
        )

        if not target_rows and not found_target:
            print("  경고: 통합자료집 항목을 찾을 수 없습니다.")
            break

        time.sleep(0.3)

    recipe_path = _save_json(all_items, RECIPE_DIR / "recipes_nutrition.json")
    print(f"  -> 저장 완료: {recipe_path} ({len(all_items)}건)")

    cats = {}
    for item in all_items:
        cat = item["category"]
        cats[cat] = cats.get(cat, 0) + 1
    print("  식품군별 현황:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"    {cat}: {cnt}건")

    if all_food_names:
        food_items = sorted([
            {"name": name, "source": "nutrition_db"}
            for name in all_food_names
        ], key=lambda x: x["name"])
        ingr_path = _save_json(food_items, LABEL_DIR / "nutrition_food_names.json")
        print(f"  -> 식품명 저장: {ingr_path} ({len(food_items)}개)")

    return all_items


# ═══════════════════════════════════════════════════════════
# 정규화 + 중복 제거: 모든 레시피 → 통합 스키마
# ═══════════════════════════════════════════════════════════

_CATEGORY_MAP: Dict[str, str] = {
    "밥": "밥류",
    "밥류": "밥류",
    "국": "국/탕류",
    "국&찌개": "국/탕류",
    "국 및 탕류": "국/탕류",
    "찌개 및 전골류": "찌개/전골류",
    "찌개/전골/스튜": "찌개/전골류",
    "반찬": "반찬",
    "밑반찬/김치": "반찬",
    "만두/면류": "면/만두류",
    "면 및 만두류": "면/만두류",
    "나물/생채/샐러드": "나물/무침류",
    "생채·무침류": "나물/무침류",
    "나물·숙채류": "나물/무침류",
    "볶음류": "볶음류",
    "볶음": "볶음류",
    "구이": "구이류",
    "구이류": "구이류",
    "찜": "찜류",
    "찜류": "찜류",
    "조림류": "조림류",
    "조림": "조림류",
    "전·적 및 부침류": "전/부침류",
    "부침": "전/부침류",
    "튀김/커틀릿": "튀김류",
    "튀김류": "튀김류",
    "빵 및 과자류": "빵/과자류",
    "빵/과자": "빵/과자류",
    "후식": "후식/디저트",
    "차 음식/디저트": "후식/디저트",
    "떡/한과": "후식/디저트",
    "김치류": "김치류",
    "장아찌·절임류": "장아찌/젓갈류",
    "젓갈류": "장아찌/젓갈류",
    "죽 및 스프류": "죽/스프류",
    "음료": "음료/차류",
    "음료 및 차류": "음료/차류",
    "일품": "일품요리",
    "그라탕/리조또": "일품요리",
    "양식": "일품요리",
    "피자": "일품요리",
    "샌드위치/햄버거": "일품요리",
    "양념장": "양념/소스류",
    "도시락/간식": "도시락/간식",
    "수·조·어·육류": "반찬",
    "기타": "기타",
}

_TITLE_NORM_RE = re.compile(r"[\s_·\-]+")


def _normalize_title(title: str) -> str:
    """비교용 제목 정규화 (공백·밑줄·가운데점 제거, 소문자)."""
    return _TITLE_NORM_RE.sub("", title).strip().lower()


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    s = str(val).strip().replace(",", "").rstrip("Kcalkcalg㎉ ")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def _richness_score(recipe: Dict[str, Any]) -> int:
    """레시피의 데이터 풍부도 점수 (중복 시 더 풍부한 쪽을 선택)."""
    score = 0
    ingr = recipe.get("ingredients", [])
    score += len(ingr) * 2
    steps = recipe.get("steps", [])
    score += len(steps) * 3
    for s in steps:
        score += len(s.get("description", "")) // 50
    if recipe.get("nutrition"):
        score += len(recipe["nutrition"]) * 1
    if recipe.get("image_url"):
        score += 5
    if recipe.get("tip"):
        score += 2
    if recipe.get("cooking_time"):
        score += 1
    if recipe.get("servings"):
        score += 1
    return score


def _normalize_public(r: Dict[str, Any]) -> Dict[str, Any]:
    """recipes_public.json (COOKRCP01) → 통합 스키마."""
    ingredients = []
    for name_str in r.get("ingredients", []):
        cleaned = _clean_name(name_str)
        if cleaned and len(cleaned) >= 2:
            ingredients.append({"name": cleaned, "amount": "", "type": ""})

    steps = []
    for s in r.get("steps", []):
        entry: Dict[str, Any] = {
            "step": s.get("step", 0),
            "description": s.get("description", ""),
        }
        if s.get("image_url"):
            entry["image_url"] = s["image_url"]
        steps.append(entry)

    nutrition: Dict[str, Any] = {}
    for field, name, unit in [
        ("calories", "에너지", "kcal"), ("carbs", "탄수화물", "g"),
        ("protein", "단백질", "g"), ("fat", "지방", "g"),
        ("sodium", "나트륨", "mg"),
    ]:
        v = _safe_float(r.get(field))
        if v is not None:
            nutrition[name] = {"value": v, "unit": unit}

    tags = [t.strip() for t in (r.get("hash_tag") or "").split(",") if t.strip()]

    return {
        "title": (r.get("title") or "").strip(),
        "category": (r.get("category") or "").strip(),
        "cooking_method": (r.get("cooking_method") or "").strip(),
        "cooking_time": "",
        "servings": (r.get("servings") or "").strip(),
        "difficulty": "",
        "ingredients": ingredients,
        "ingredients_raw": (r.get("ingredients_raw") or "").strip(),
        "steps": steps,
        "nutrition": nutrition,
        "image_url": (r.get("image_url") or "").strip(),
        "tags": tags,
        "tip": (r.get("tip") or "").strip(),
        "description": "",
        "sources": ["식품안전나라(COOKRCP01)"],
        "source_ids": {"public": (r.get("id") or "").strip()},
    }


def _normalize_epis(r: Dict[str, Any]) -> Dict[str, Any]:
    """recipes_epis.json → 통합 스키마."""
    ingredients = []
    for i in r.get("ingredients", []):
        name = (i.get("name") or "").strip()
        if name:
            ingredients.append({
                "name": name,
                "amount": (i.get("amount") or "").strip(),
                "type": (i.get("type") or "").strip(),
            })

    steps = []
    for s in r.get("steps", []):
        entry: Dict[str, Any] = {
            "step": s.get("step", 0),
            "description": (s.get("description") or "").strip(),
        }
        tip = (s.get("tip") or "").strip()
        if tip:
            entry["tip"] = tip
        steps.append(entry)

    nutrition: Dict[str, Any] = {}
    cal = _safe_float(r.get("calories"))
    if cal is not None:
        nutrition["에너지"] = {"value": cal, "unit": "kcal"}

    title = (r.get("title") or "").strip()
    cat = (r.get("category") or "").strip()

    if cat == "반찬":
        if _KIMCHI_PURE_RE.search(title):
            cat = "김치류"

    return {
        "title": title,
        "category": cat,
        "cooking_method": "",
        "cooking_time": (r.get("cooking_time") or "").strip(),
        "servings": (r.get("servings") or "").strip(),
        "difficulty": (r.get("difficulty") or "").strip(),
        "ingredients": ingredients,
        "ingredients_raw": "",
        "steps": steps,
        "nutrition": nutrition,
        "image_url": "",
        "tags": [],
        "tip": "",
        "description": (r.get("summary") or "").strip(),
        "sources": ["EPIS(농림수산식품교육문화정보원)"],
        "source_ids": {"epis": (r.get("id") or "").strip()},
    }


def _normalize_boseong(r: Dict[str, Any]) -> Dict[str, Any]:
    """recipes_boseong_tea.json → 통합 스키마."""
    ingredients = []
    for name_str in r.get("ingredients", []):
        if name_str and len(name_str) >= 2:
            ingredients.append({"name": name_str, "amount": "", "type": ""})

    return {
        "title": (r.get("title") or "").strip(),
        "category": (r.get("category") or "차 음식/디저트").strip(),
        "cooking_method": "",
        "cooking_time": "",
        "servings": "",
        "difficulty": "",
        "ingredients": ingredients,
        "ingredients_raw": " / ".join(
            filter(None, [r.get("ingredients_main_raw", ""),
                          r.get("ingredients_sub_raw", "")])
        ),
        "steps": r.get("steps", []),
        "nutrition": {},
        "image_url": "",
        "tags": [],
        "tip": "",
        "description": (r.get("description") or "").strip(),
        "sources": ["전라남도 보성군(공공데이터포털)"],
        "source_ids": {"boseong": (r.get("id") or "").strip()},
    }


_KIMCHI_PURE_RE = re.compile(
    r"^(?:배추|총각|열무|갓|깻잎|부추|파|오이|고들빼기|나박|백|동치미|보쌈|섞박지"
    r"|장|깍두기|고추|미나리|씀바귀|돌산갓|콩잎|무청|겉절이|물?김치|석류|해초)?"
    r"\s*(?:김치|깍두기|동치미|장아찌|젓갈|절임|피클|겉절이|장$|지$|짠지)$"
    r"|갓지$|쌀겨갓지|오그락지|통지$"
    r"|해물반지$"
)
_KIMCHI_DISH_CAT_RE: List[tuple] = [
    (re.compile(r"볶음밥|주먹밥|덮밥|리조또|필라프|리소토"), "밥류"),
    (re.compile(r"파에야|파엘라"), "밥류"),
    (re.compile(r"국수|면|우동|파스타|라면|냉면|소바"), "면/만두류"),
    (re.compile(r"만두|교자"), "면/만두류"),
    (re.compile(r"국|탕|스프|스튜|차우더|찌개|전골"), "국/탕류"),
    (re.compile(r"찜"), "찜류"),
    (re.compile(r"볶음"), "볶음류"),
    (re.compile(r"전$|전병|부침|빈대떡|오코노미"), "전/부침류"),
    (re.compile(r"샌드위치|버거|롤|햄버거|핫도그|타코|쌈"), "일품요리"),
    (re.compile(r"피자|그라탕|라자냐|소세지|윙$"), "일품요리"),
    (re.compile(r"튀김|프라이|칩|까스"), "튀김류"),
    (re.compile(r"샐러드|슬로우"), "나물/무침류"),
    (re.compile(r"빵|케이크|파이|쿠키|머핀"), "빵/과자류"),
    (re.compile(r"구이|구운|그릴|바비큐|BBQ|스테이크"), "구이류"),
    (re.compile(r"조림"), "조림류"),
    (re.compile(r"소스|잼|드레싱|양념"), "양념/소스류"),
]


_KIMCHI_JANG_RE = re.compile(
    r"^(?:막장|즙장|집장|뜸북장|뽁작장|청국장|고추장|쌈장|된장)$"
)


def _infer_kimchi_category(title: str) -> str:
    """김치연구소 레시피의 실제 카테고리를 추론한다."""
    if _KIMCHI_JANG_RE.search(title):
        return "양념/소스류"
    if _KIMCHI_PURE_RE.search(title):
        return "김치류"
    for pattern, cat in _KIMCHI_DISH_CAT_RE:
        if pattern.search(title):
            return cat
    return "김치류"


def _normalize_kimchi(r: Dict[str, Any]) -> Dict[str, Any]:
    """recipes_kimchi.json → 통합 스키마."""
    ingredients = []
    for i in r.get("ingredients", []):
        name = (i.get("name") or "").strip()
        if name:
            ingredients.append({
                "name": name,
                "amount": (i.get("amount") or "").strip(),
                "type": "",
            })

    tags = [t.strip() for t in (r.get("keywords") or "").split(",") if t.strip()]
    title = (r.get("title") or "").strip()

    return {
        "title": title,
        "category": _infer_kimchi_category(title),
        "cooking_method": "",
        "cooking_time": "",
        "servings": "",
        "difficulty": "",
        "ingredients": ingredients,
        "ingredients_raw": "",
        "steps": r.get("steps", []),
        "nutrition": {},
        "image_url": "",
        "tags": tags,
        "tip": "",
        "description": "",
        "sources": ["세계김치연구소(김치콘텐츠통합플랫폼)"],
        "source_ids": {"kimchi": (r.get("id") or "").strip()},
    }


def _normalize_nutrition(r: Dict[str, Any]) -> Dict[str, Any]:
    """recipes_nutrition.json → 통합 스키마."""
    title = (r.get("title") or "").strip()
    if "_" in title:
        title = title.replace("_", " ")

    return {
        "title": title,
        "category": (r.get("category") or "").strip(),
        "cooking_method": "",
        "cooking_time": "",
        "servings": (r.get("serving_size") or "").strip(),
        "difficulty": "",
        "ingredients": [],
        "ingredients_raw": "",
        "steps": [],
        "nutrition": r.get("nutrients", {}),
        "image_url": "",
        "tags": [],
        "tip": "",
        "description": "",
        "sources": ["식품의약품안전처(식품영양성분DB 통합자료집)"],
        "source_ids": {"nutrition": (r.get("food_code") or "").strip()},
    }


# ── 조리방법 자동 추론 ─────────────────────────────────────

_COOKING_METHOD_SCHEMA: Dict[str, Dict[str, str]] = {
    "끓이기": {"code": "BOIL", "en": "Boiling/Simmering",
               "desc": "물이나 육수에 재료를 넣고 끓여 조리"},
    "굽기":   {"code": "GRILL", "en": "Grilling/Baking",
               "desc": "직화, 오븐, 팬 등으로 표면에 열을 가해 조리"},
    "볶기":   {"code": "STIRFRY", "en": "Stir-frying",
               "desc": "소량의 기름에 센 불로 빠르게 볶아 조리"},
    "찌기":   {"code": "STEAM", "en": "Steaming",
               "desc": "증기로 재료를 익혀 조리"},
    "튀기기": {"code": "DEEPFRY", "en": "Deep-frying",
               "desc": "다량의 기름에 재료를 넣어 튀겨 조리"},
    "부치기": {"code": "PANFRY", "en": "Pan-frying",
               "desc": "팬에 얇게 기름을 두르고 반죽·재료를 펴서 익힘"},
    "무치기": {"code": "SEASONING", "en": "Seasoning/Mixing",
               "desc": "양념장으로 재료를 버무려 조리"},
    "조리기": {"code": "BRAISE", "en": "Braising",
               "desc": "양념장을 넣고 약한 불에 졸여 조리"},
    "절이기": {"code": "PICKLE", "en": "Pickling/Fermenting",
               "desc": "소금·양념에 재료를 절여 발효·숙성"},
    "삶기":   {"code": "BLANCH", "en": "Blanching/Boiling",
               "desc": "끓는 물에 재료를 넣어 익히거나 데침"},
    "기타":   {"code": "ETC", "en": "Other",
               "desc": "위 분류에 해당하지 않는 조리법 (비가열, 혼합 등)"},
}


_COOKING_METHODS: List[Dict[str, Any]] = [
    {
        "name": "끓이기",
        "title_kw": ["국밥", "국수", "수제비", "칼국수", "라면"],
        "title_re": re.compile(
            r"(?:된장|김치|순두부|부대|해물|참치)?\s*(?:국|탕|찌개|전골|죽|스프|수프)"
            r"|(?:매운탕|갈비탕|설렁탕|곰탕|삼계탕|육개장|미역국|떡국|만둣국)"
        ),
        "step_kw": ["끓인", "끓여", "끓이", "끓을", "팔팔", "육수",
                     "냄비에", "물을 붓", "끓는 물"],
        "weight": 1.0,
    },
    {
        "name": "볶기",
        "title_kw": ["볶음", "볶음밥", "잡채"],
        "title_re": re.compile(r"볶음|볶은"),
        "step_kw": ["볶아", "볶은", "볶다", "볶으", "센불", "팬에.*볶"],
        "weight": 1.0,
    },
    {
        "name": "굽기",
        "title_kw": ["구이", "스테이크", "피자", "토스트", "그라탕"],
        "title_re": re.compile(
            r"구이|구운|그릴|빵|케이크|쿠키|머핀|스콘|타르트|파이|마카롱"
            r"|크로와상|베이글|와플|브라우니|피낭시에|마들렌|샤브레|파운드"
        ),
        "step_kw": ["구워", "구운", "굽는", "굽다", "오븐", "그릴", "석쇠",
                     "노릇"],
        "weight": 1.0,
    },
    {
        "name": "찌기",
        "title_kw": ["찜", "만두"],
        "title_re": re.compile(r"찜|쪄서|찐"),
        "step_kw": ["찜", "쪄서", "찐", "찌다", "증기", "김이.*오르",
                     "찜기", "찜솥"],
        "weight": 1.0,
    },
    {
        "name": "튀기기",
        "title_kw": ["튀김", "커틀릿", "돈까스", "탕수"],
        "title_re": re.compile(r"튀김|튀긴|까스|커틀릿|프라이"),
        "step_kw": ["튀겨", "튀긴", "튀기", "기름에.*넣", "딥프라이",
                     "170", "180"],
        "weight": 1.0,
    },
    {
        "name": "부치기",
        "title_kw": ["부침", "부침개", "파전", "김치전", "빈대떡", "녹두전"],
        "title_re": re.compile(
            r"(?:김치|해물|파|녹두|감자|호박|배추|부추|동태|생선|깻잎|고추|메밀)\s*전$"
            r"|전병|부침|부침개|빈대떡|지짐이?"
        ),
        "step_kw": ["부쳐", "부치", "지져", "지진", "팬에.*기름.*넓게",
                     "얇게.*부"],
        "weight": 1.0,
    },
    {
        "name": "무치기",
        "title_kw": ["샐러드"],
        "title_re": re.compile(
            r"무침|나물|겉절이|비빔|콩나물$|시금치$|숙채|냉채|샐러드"
        ),
        "step_kw": ["무쳐", "무치", "버무려", "버무리", "비벼", "비빈",
                     "양념.*섞", "참기름.*깨", "골고루.*섞", "넣고.*섞"],
        "weight": 1.0,
    },
    {
        "name": "조리기",
        "title_kw": [],
        "title_re": re.compile(r"조림|조린|장조림|졸인"),
        "step_kw": ["조려", "조린", "조리", "졸여", "졸인", "윤기.*나게",
                     "양념.*졸"],
        "weight": 1.0,
    },
    {
        "name": "절이기",
        "title_kw": ["장아찌", "젓갈", "피클", "절임"],
        "title_re": re.compile(
            r"(?:배추|총각|열무|갓|깻잎|부추|파|오이|고들빼기|나박|백|보쌈|섞박지"
            r"|깍두기|고추|미나리|씀바귀|돌산갓|콩잎|무청|해초)??"
            r"(?:김치|깍두기|동치미)$"
            r"|장아찌$|젓갈$|절임$|피클$|겉절이$"
        ),
        "step_kw": ["절여", "절이", "담가", "담그", "삭히", "숙성",
                     "소금.*뿌려.*절"],
        "weight": 1.0,
    },
    {
        "name": "삶기",
        "title_kw": ["수육", "편육", "족발"],
        "title_re": re.compile(r"삶은|수육|편육|족발"),
        "step_kw": ["삶아", "삶은", "데쳐", "데치", "삶다"],
        "weight": 0.8,
    },
]

_CATEGORY_METHOD_FALLBACK: Dict[str, str] = {
    "국/탕류": "끓이기",
    "찌개/전골류": "끓이기",
    "죽/스프류": "끓이기",
    "볶음류": "볶기",
    "구이류": "굽기",
    "빵/과자류": "굽기",
    "찜류": "찌기",
    "튀김류": "튀기기",
    "전/부침류": "부치기",
    "나물/무침류": "무치기",
    "조림류": "조리기",
    "김치류": "절이기",
    "장아찌/젓갈류": "절이기",
}


_TITLE_METHOD_OVERRIDES: List[tuple] = [
    (re.compile(r"전골$"), "끓이기"),
    (re.compile(r"탕수육|탕수(?:어|새우|돼지)"), "튀기기"),
    (re.compile(r"라조[기육]"), "튀기기"),
    (re.compile(r"그라탕|그라땡"), "굽기"),
    (re.compile(r"떡국|만두국$|떡만두국"), "끓이기"),
    (re.compile(r"떡케이크"), "찌기"),
    (re.compile(r"찐\s*빵"), "찌기"),
    (re.compile(r"편육|수육|족발"), "삶기"),
    (re.compile(r"불고기"), "굽기"),
    (re.compile(r"냉면|비빔(?:국수|쌀국수)"), "무치기"),
    (re.compile(r"냉국$|냉채$"), "무치기"),
    (re.compile(r"육회|강회"), "무치기"),
    (re.compile(r"김치꽁치조림"), "조리기"),
    (re.compile(r"김치전골"), "끓이기"),
    (re.compile(r"계란말이|달걀말이|장어계란말이"), "부치기"),
    (re.compile(r"산적$"), "굽기"),
    (re.compile(r"어묵꼬치$"), "끓이기"),
    (re.compile(r"꼬치$"), "굽기"),
    (re.compile(r"오코노미야키"), "부치기"),
    (re.compile(r"부각$"), "튀기기"),
    (re.compile(r"닭볶음탕"), "끓이기"),
    (re.compile(r"두부김치$"), "볶기"),
    (re.compile(r"화양적$"), "굽기"),
    (re.compile(r"고등어튀김케첩조림"), "조리기"),
    (re.compile(r"가죽나물무침$"), "무치기"),
    (re.compile(r"간장게장$"), "절이기"),
    (re.compile(r"클램차우더"), "끓이기"),
    (re.compile(r"김치꽁치조림"), "조리기"),
    # 밥류
    (re.compile(r"^(?:기장|보리|수수|현미|잡곡|차조|잎차|차|녹차)?\s*밥$"), "끓이기"),
    (re.compile(r"솥밥$|영양밥$"), "끓이기"),
    (re.compile(r"자장밥|짬뽕밥|카레밥"), "끓이기"),
    (re.compile(r"김밥|주먹밥|초밥|삼각밥"), "무치기"),
    (re.compile(r"쌈밥$"), "무치기"),
    (re.compile(r"알밥$"), "끓이기"),
    # 후식
    (re.compile(r"시루떡|인절미|송편|절편|경단"), "찌기"),
    (re.compile(r"강정$"), "끓이기"),
    (re.compile(r"화채$"), "무치기"),
    # 양념/소스
    (re.compile(r"쌈장$"), "끓이기"),
    # 면류
    (re.compile(r"간자장$"), "끓이기"),
    (re.compile(r"소바정식$"), "끓이기"),
]


def _infer_cooking_method(recipe: Dict[str, Any]) -> str:
    """제목·조리법 텍스트·카테고리를 분석하여 조리방법을 추론한다."""
    title = recipe.get("title", "")
    category = recipe.get("category", "")
    steps_text = " ".join(
        s.get("description", "") for s in recipe.get("steps", [])
    )

    for pattern, method in _TITLE_METHOD_OVERRIDES:
        if pattern.search(title):
            return method

    scores: Dict[str, float] = {}

    for method in _COOKING_METHODS:
        name = method["name"]
        score = 0.0

        for kw in method["title_kw"]:
            if kw in title:
                score += 10.0
                break

        if method["title_re"].search(title):
            score += 8.0

        if steps_text:
            hit = 0
            for kw in method["step_kw"]:
                if re.search(kw, steps_text):
                    hit += 1
            score += hit * method["weight"]

        if score > 0:
            scores[name] = score

    if scores:
        best = max(scores, key=lambda k: scores[k])
        if scores[best] >= 1.0:
            return best

    fallback = _CATEGORY_METHOD_FALLBACK.get(category)
    if fallback:
        return fallback

    return "기타"


_METHOD_TO_CATEGORY: Dict[str, str] = {
    "굽기": "구이류",
    "튀기기": "튀김류",
    "부치기": "전/부침류",
}

_FIXABLE_CATS = {"볶음류", "튀김류", "전/부침류", "구이류", "나물/무침류"}


def _fix_category_method_conflict(recipe: Dict[str, Any]) -> None:
    """조리방법이 확실한데 카테고리가 맞지 않을 때 카테고리를 보정한다."""
    cat = recipe.get("category", "")
    method = recipe.get("cooking_method", "")
    title = recipe.get("title", "")

    if cat == "김치류" and _KIMCHI_PURE_RE.search(title) and method != "절이기":
        recipe["cooking_method"] = "절이기"
        return

    if cat == "찌개/전골류" and method == "조리기" and "조림" in title:
        recipe["category"] = "조림류"
        return

    if cat not in _FIXABLE_CATS:
        return

    if cat == "볶음류" and method == "굽기" and "불고기" in title:
        recipe["category"] = "구이류"
    elif cat == "볶음류" and method == "무치기" and "무침" in title:
        recipe["category"] = "나물/무침류"
    elif cat == "튀김류" and method == "굽기":
        recipe["category"] = "구이류"
    elif cat == "구이류" and method == "찌기":
        recipe["category"] = "찜류"
    elif cat == "전/부침류" and method == "볶기":
        pass
    elif cat == "나물/무침류" and method not in ("무치기", "볶기"):
        recipe["category"] = "반찬"
    elif cat == "국/탕류" and method == "굽기":
        recipe["category"] = "구이류"


def _merge_recipes(base: Dict[str, Any], other: Dict[str, Any]) -> Dict[str, Any]:
    """두 정규화 레시피를 병합한다. 각 필드마다 더 풍부한 쪽을 채택."""
    merged = dict(base)

    if not merged["category"] and other.get("category"):
        merged["category"] = other["category"]
    if not merged["cooking_method"] and other.get("cooking_method"):
        merged["cooking_method"] = other["cooking_method"]
    if not merged["cooking_time"] and other.get("cooking_time"):
        merged["cooking_time"] = other["cooking_time"]
    if not merged["servings"] and other.get("servings"):
        merged["servings"] = other["servings"]
    if not merged["difficulty"] and other.get("difficulty"):
        merged["difficulty"] = other["difficulty"]
    if not merged["description"] and other.get("description"):
        merged["description"] = other["description"]
    if not merged["tip"] and other.get("tip"):
        merged["tip"] = other["tip"]
    if not merged["image_url"] and other.get("image_url"):
        merged["image_url"] = other["image_url"]

    if len(other.get("ingredients", [])) > len(merged.get("ingredients", [])):
        merged["ingredients"] = other["ingredients"]
    if not merged["ingredients_raw"] and other.get("ingredients_raw"):
        merged["ingredients_raw"] = other["ingredients_raw"]

    if len(other.get("steps", [])) > len(merged.get("steps", [])):
        merged["steps"] = other["steps"]

    base_nutr = merged.get("nutrition", {})
    other_nutr = other.get("nutrition", {})
    if len(other_nutr) > len(base_nutr):
        combined = dict(other_nutr)
        for k, v in base_nutr.items():
            if k not in combined:
                combined[k] = v
        merged["nutrition"] = combined
    else:
        combined = dict(base_nutr)
        for k, v in other_nutr.items():
            if k not in combined:
                combined[k] = v
        merged["nutrition"] = combined

    other_tags = other.get("tags", [])
    existing = set(merged.get("tags", []))
    for t in other_tags:
        if t not in existing:
            merged["tags"].append(t)
            existing.add(t)

    merged["sources"] = list(
        dict.fromkeys(merged.get("sources", []) + other.get("sources", []))
    )
    src_ids = dict(merged.get("source_ids", {}))
    src_ids.update(other.get("source_ids", {}))
    merged["source_ids"] = src_ids

    return merged


# ── 재료 8대 카테고리 분류 ──────────────────────────────────
_INGR_CATEGORIES: List[tuple] = [
    # (카테고리, 키워드 리스트, 정규식)  — 순서대로 매칭, 먼저 매칭되면 확정
    ("정육/계란", None, re.compile(
        r"소고기|쇠고기|소불고기|한우|갈비|등심|안심|목살|차돌박이|사태|양지|우둔|채끝"
        r"|돼지고기|돼기고기|돈까스|삼겹살|항정살|앞다리|뒷다리|갈매기살|제육|수육"
        r"|닭고기|닭가슴살|닭다리|닭날개|닭봉|닭안심|치킨|닭볶음|닭$"
        r"|오리고기|오리$|양고기|양갈비|램$"
        r"|계란|달걀|메추리알|노른자|흰자|알$|란$"
        r"|다짐육|다진\s*고기|소시지용\s*고기|간\s*고기"
        r"|베이컨|곱창|대창|막창|간$|염통|허파|족발|편육|내장"
        r"|통삼겹|닭다릿살|사골|도가니|양$"
    )),
    ("해산물", None, re.compile(
        r"새우|꽃게|게살|대게|킹크랩|랍스터|가재|꽃게살"
        r"|오징어|문어|낙지|주꾸미|꼴뚜기|한치"
        r"|멸치|꽁치|고등어|갈치|삼치|참치|연어|광어|우럭|도미|농어|방어|전어"
        r"|대구|아귀|복어|장어|미꾸라지|메기|잉어|송어|붕어|민어|병어|가자미|꽃치"
        r"|조개|바지락|모시조개|홍합|굴$|전복|소라|꼬막|가리비|키조개|관자"
        r"|미역|다시마|김$|톳$|파래|해초|매생이|우뭇가사리|한천|청각$"
        r"|해파리|성게|해삼|멍게|미더덕|개불"
        r"|어묵|맛살|게맛살|크래미"
        r"|젓갈|새우젓|멸치액젓|액젓|까나리액젓|어간장|피시소스|굴소스"
        r"|참치캔|꽁치캔|골뱅이|골뱅이캔"
        r"|건새우|마른\s*새우|건오징어|마른\s*오징어|쥐포|건멸치|잔멸치|볶음멸치"
        r"|북어|황태|대구포|명태|동태|코다리"
        r"|가다랑어포|가쓰오부시|가다랑이"
        r"|쭈꾸미|대하$|조기$|생선살|흰살생선|패주|명란젓|엔초비|조갯살|생태$"
    )),
    ("유제품", None, re.compile(
        r"우유|저지방\s*우유|탈지\s*우유|전유|두유|스팀밀크|밀크$"
        r"|생크림|휘핑크림|크림$"
        r"|버터|무염버터|가염버터"
        r"|치즈|모짜렐라|체다|파르메산|크림치즈|리코타|고르곤졸라|마스카포네|그뤼에르"
        r"|요거트|요구르트|플레인\s*요거트|그릭\s*요거트|발효유"
        r"|연유|사워크림"
    )),
    ("쌀/면/빵", None, re.compile(
        r"^쌀$|현미|찹쌀$|멥쌀|흑미|보리쌀|잡곡|오곡|기장|수수|차조|율무|보리$"
        r"|^밥$|밥$|누룽지|귀리"
        r"|밀가루|박력분|중력분|강력분|전분|녹말|감자전분|옥수수전분|타피오카"
        r"|찹쌀가루|쌀가루|녹말가루|빵가루|튀김가루|부침가루|콩가루|날콩가루|미숫가루"
        r"|국수|소면|당면|쌀국수|우동면|파스타|스파게티|펜네|마카로니|라면|냉면|메밀면|칼국수면"
        r"|식빵|모닝빵|바게트|크루아상|또띠아|난$|피타|핫도그빵"
        r"|떡$|떡국떡|가래떡|인절미|찹쌀떡|경단|백설기|시루떡|송편|떡볶이떡"
        r"|만두피|교자피|춘권피|라이스페이퍼"
        r"|오트밀|시리얼|콘플레이크"
        r"|팥$|팥앙금|팥배기|녹두$|콩$|검은콩|흰콩|병아리콩|강낭콩|렌틸콩|서리태"
        r"|불린\s*쌀|백미$|핫케이크가루|퀴노아|푸실리|쫄면"
        r"|백앙금|적앙금|앙금$|비스킷|카스텔라"
    )),
    ("소스/조미료/오일", None, re.compile(
        r"간장|저염간장|진간장|양조간장|국간장|조선간장|타마리"
        r"|된장|고추장|쌈장|청국장|미소$"
        r"|소금|천일염|꽃소금|맛소금|소금적당량"
        r"|설탕|흑설탕|황설탕|슈가파우더|분당|시럽|스테비아"
        r"|식초|현미식초|발사믹|레드와인\s*식초|백초|홍초$"
        r"|참기름|들기름|식용유|올리브유|올리브오일|포도씨유|카놀라유|콩기름|해바라기유|현미유"
        r"|튀김기름|기름$"
        r"|고춧가루|후춧가루|후추$|흰후추|통후추|검은후추|산초|초피"
        r"|후추\s*적당량|후추적당량"
        r"|맛술|미림|청주|요리주|정종|맥주|레드와인|화이트와인|럼주|소주"
        r"|카레가루|카레분|겨자|와사비|머스타드|머스터드"
        r"|마요네즈|케첩|토마토소스|칠리소스|타바스코|우스타소스|핫소스"
        r"|꿀$|매실액|올리고당|조청|물엿|아가베"
        r"|통깨|참깨|깨소금|흑임자|검은깨|아몬드가루|들깻?가루|들깨가루"
        r"|계피|시나몬|바닐라|넛맥|정향|오레가노|타임|로즈마리|바질|파슬리|딜"
        r"|강황가루|강황$|울금|백년초가루|녹차가루|녹차파우더|말차가루|가루녹차"
        r"|육수$|다시다|멸치다시|치킨스톡|비프스톡|콘소메"
        r"|베이킹파우더|베이킹소다|이스트|드라이이스트|생이스트"
        r"|젤라틴|한천가루|펙틴|코코아파우더|초콜릿$|다크초콜릿|화이트초콜릿|초코칩"
        r"|레몬즙|레몬주스|생강즙|유자청|배즙"
        r"|물$|얼음|탄산수"
        r"|월계수잎|찹쌀풀|견과류|에스프레소"
        r"|녹차$|녹차잎|녹차티백|말차파우더|그린티파우더|마차가루|녹차파우더"
        r"|검정깨|깨$|들깨$|헤이즐넛|해바라기씨|카카오닙스"
        r"|두반장|피클링스파이스|잣가루|계핏가루|로즈메리|차이브"
        r"|레몬제스트|레몬껍질|커민|페페론치노"
        r"|조미술|요리당|케찹|스리라차소스|카라멜소스|초코소스"
        r"|코코넛\s*오일|알룰로스|타가토스|스테비아"
        r"|분유$|천연조미료|제빵개량제"
        r"|막걸리|생막걸리|사이다$|식혜$|치자$|치자가루"
        r"|보성홍차|보성녹차|홍차|우전$|세작$"
        r"|코코아가루|홍차라떼파우더|초코라떼파우더"
        r"|석류원액|오미자원액|뽕잎가루|백년초가루"
        r"|올리브$|블랙올리브"
        r"|오일$|생수$"
    )),
    ("가공식품", None, re.compile(
        r"두부|순두부|연두부|유부|비지"
        r"|햄$|스팸|소시지|핫도그|비엔나"
        r"|어묵"
        r"|김치$|깍두기|배추김치|열무김치|총각김치|묵은지|동치미"
        r"|단무지|피클$|절임$|장아찌"
        r"|통조림|캔$"
        r"|묵$|도토리묵|청포묵|메밀묵"
        r"|콩나물|숙주$|숙주나물"
        r"|곤약|실곤약|건조곤약"
        r"|총각무김치|숙주<br>"
    )),
    ("채소/과일", None, re.compile(
        r"양파|대파|쪽파|실파|부추|마늘|다진\s*마늘|다진마늘|생강|파다진것|파$"
        r"|당근|감자|고구마|무$|연근|우엉|토란|마$|더덕|도라지|순무"
        r"|배추|배춧잎|양배추|청경채|치커리|깻잎|상추|양상추|로메인|루꼴라|겨자잎"
        r"|시금치|근대|미나리|셀러리|샐러리|아스파라거스|브로콜리|브로컬리|콜리플라워"
        r"|호박|애호박|단호박|주키니|가지|오이|피망|청피망|파프리카"
        r"|토마토|방울토마토|체리토마토"
        r"|고추|청고추|홍고추|청양고추|꽈리고추|풋고추|건고추|마른고추"
        r"|쑥갓|무순|비트|케일|적채|달래|새싹|어린잎|새싹채소|어린잎채소|갓$"
        r"|죽순|고사리|취나물|냉이|씀바귀|두릅|원추리|참나물|방풍|수삼|인삼"
        r"|함초|식용꽃|레디쉬|아보카도|래디쉬"
        r"|아욱|콜라비|컬리플라워|레드어니언|워터크레스|베이비채소|당귀잎|영콘"
        r"|무청|우거지|시래기|쑥$|쑥가루|봄동|고들빼기|무말랭이"
        r"|석류|애플민트|민트$|페퍼민트|홍시"
        r"|느타리버섯|표고버섯|새송이버섯|양송이버섯|양송이$|팽이버섯|목이버섯|송이버섯|만가닥버섯|버섯$"
        r"|사과|배$|딸기|포도|귤|감$|수박|참외|멜론|바나나|키위|망고|파인애플"
        r"|블루베리|라즈베리|크랜베리|체리|살구|자두|복숭아|매실|대추|밤$|은행"
        r"|호두|잣$|아몬드|캐슈넛|피스타치오|땅콩|피칸|마카다미아"
        r"|레몬$|라임|오렌지|자몽|유자$|금귤|한라봉|홍시|감귤|귤$"
        r"|건포도|건자두|건살구|무화과|오미자$"
        r"|옥수수"
    )),
]


_INGR_JUNK_RE = re.compile(
    r"^\d+[gG]?$|^\d+ml$|^\d+cc$|^\d+인분|<br>|기준"
    r"|^적당량$|^약간$|^조금$|^적량$|^소량$"
    r"|^\d+[장마리개큰술작은술T]|^물\s*\d|^꿀\s*\d|^잣\s*\d"
    r"|^녹차\s*\d|^녹차\s*[½¼]|^ICED|^재료\s|^주재료$|^고명$|^소스$"
    r"|^토핑:|^노랑\s*각"
)


def _classify_ingredient(name: str) -> str:
    """재료명을 8대 카테고리 중 하나로 분류한다."""
    cleaned = re.sub(r'\s+', '', name.strip())
    if not cleaned or _INGR_JUNK_RE.search(cleaned):
        return "기타"
    for cat, _, pattern in _INGR_CATEGORIES:
        if pattern.search(cleaned):
            return cat
    return "기타"


def normalize_and_deduplicate() -> List[Dict[str, Any]]:
    """
    모든 레시피 파일을 통합 스키마로 정규화하고 중복을 제거한다.

    1단계: 각 소스 파일을 통합 스키마로 변환
    2단계: 소스 내 제목 중복 → 풍부도 점수가 높은 쪽 유지
    3단계: 소스 간 제목 중복 → 데이터 병합 (두 소스의 장점 합산)
    4단계: ID 부여 후 data/recipes/recipes_all.json 저장
    """
    print("\n[정규화] 전체 레시피 정규화 + 중복 제거 시작...")

    normalizers: Dict[str, Any] = {
        "public": (RECIPE_DIR / "recipes_public.json", _normalize_public),
        "epis": (RECIPE_DIR / "recipes_epis.json", _normalize_epis),
        "boseong": (RECIPE_DIR / "recipes_boseong_tea.json", _normalize_boseong),
        "kimchi": (RECIPE_DIR / "recipes_kimchi.json", _normalize_kimchi),
        "nutrition": (RECIPE_DIR / "recipes_nutrition.json", _normalize_nutrition),
    }

    # ── 1단계: 정규화 ──
    all_normalized: Dict[str, List[Dict[str, Any]]] = {}
    total_raw = 0

    for src_name, (path, normalizer) in normalizers.items():
        if not path.exists():
            print(f"  {src_name}: 파일 없음 → 건너뜀")
            continue
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        normalized = [normalizer(r) for r in raw_data]
        all_normalized[src_name] = normalized
        total_raw += len(normalized)
        print(f"  {src_name}: {len(raw_data)}건 정규화 완료")

    print(f"  → 전체 원본: {total_raw}건")

    # ── 2단계: 소스 내 중복 제거 ──
    total_intra_dup = 0
    for src_name, recipes in all_normalized.items():
        seen: Dict[str, Dict[str, Any]] = {}
        for r in recipes:
            key = _normalize_title(r["title"])
            if not key:
                continue
            if key in seen:
                existing = seen[key]
                if _richness_score(r) > _richness_score(existing):
                    seen[key] = r
                total_intra_dup += 1
            else:
                seen[key] = r
        all_normalized[src_name] = list(seen.values())

    print(f"  → 소스 내 중복 제거: {total_intra_dup}건")

    # ── 3단계: 소스 간 중복 병합 ──
    merged_map: Dict[str, Dict[str, Any]] = {}
    source_priority = ["public", "epis", "kimchi", "boseong", "nutrition"]

    for src_name in source_priority:
        for r in all_normalized.get(src_name, []):
            key = _normalize_title(r["title"])
            if not key:
                continue
            if key in merged_map:
                merged_map[key] = _merge_recipes(merged_map[key], r)
            else:
                merged_map[key] = r

    inter_dup = total_raw - total_intra_dup - len(merged_map)

    # ── 4단계: ID 부여 + 카테고리 정규화 + 조리방법 추론 + 최종 정리 ──
    inferred_count = 0
    final: List[Dict[str, Any]] = []
    for idx, (_, recipe) in enumerate(
        sorted(merged_map.items(), key=lambda x: x[0]), start=1
    ):
        recipe["id"] = f"R{idx:05d}"

        raw_cat = recipe.get("category", "").strip()
        recipe["category"] = _CATEGORY_MAP.get(raw_cat, raw_cat or "기타")

        recipe["ingredients"] = [
            {
                "name": i["name"],
                "amount": i.get("amount", ""),
                "category": _classify_ingredient(i["name"]),
            }
            for i in recipe.get("ingredients", [])
            if i.get("name") and not _INGR_JUNK_RE.search(
                re.sub(r'\s+', '', i["name"].strip())
            )
        ]

        recipe["steps"] = [
            s for s in recipe.get("steps", [])
            if (s.get("description") or "").strip()
        ]
        for si, s in enumerate(recipe["steps"], 1):
            s["step"] = si

        if not recipe.get("cooking_method") or recipe["cooking_method"] == "기타":
            new_method = _infer_cooking_method(recipe)
            if new_method != "기타" or not recipe.get("cooking_method"):
                recipe["cooking_method"] = new_method
                inferred_count += 1

        _fix_category_method_conflict(recipe)

        method_name = recipe.get("cooking_method", "기타")
        schema = _COOKING_METHOD_SCHEMA.get(method_name, _COOKING_METHOD_SCHEMA["기타"])
        recipe["cooking_method"] = method_name
        recipe["cooking_method_code"] = schema["code"]
        recipe["cooking_method_en"] = schema["en"]

        ordered: Dict[str, Any] = {
            "id": recipe["id"],
            "title": recipe.get("title", ""),
            "category": recipe.get("category", ""),
            "cooking_method": recipe["cooking_method"],
            "cooking_method_code": recipe["cooking_method_code"],
            "cooking_method_en": recipe["cooking_method_en"],
            "ingredients": recipe.get("ingredients", []),
            "ingredients_raw": recipe.get("ingredients_raw", ""),
            "steps": recipe.get("steps", []),
            "nutrition": recipe.get("nutrition", {}),
            "tags": recipe.get("tags", []),
            "tip": recipe.get("tip", ""),
            "description": recipe.get("description", ""),
            "image_url": recipe.get("image_url", ""),
            "cooking_time": recipe.get("cooking_time", ""),
            "servings": recipe.get("servings", ""),
            "difficulty": recipe.get("difficulty", ""),
            "sources": recipe.get("sources", []),
        }

        final.append(ordered)

    path = _save_json(final, RECIPE_DIR / "recipes_all.json")

    # ── 통계 ──
    print(f"\n  ┌─────────────────────────────────────")
    print(f"  │ 정규화 + 중복 제거 결과")
    print(f"  ├─────────────────────────────────────")
    print(f"  │ 원본 전체       : {total_raw:>6}건")
    print(f"  │ 소스 내 중복제거 : -{total_intra_dup:>5}건")
    print(f"  │ 소스 간 중복병합 : -{inter_dup:>5}건")
    print(f"  │ 최종 통합 레시피 : {len(final):>6}건")
    print(f"  └─────────────────────────────────────")
    print(f"  → 저장: {path}")

    cats: Dict[str, int] = {}
    with_steps = 0
    with_ingredients = 0
    with_nutrition = 0
    multi_source = 0
    for r in final:
        cat = r.get("category") or "(미분류)"
        cats[cat] = cats.get(cat, 0) + 1
        if r.get("steps"):
            with_steps += 1
        if r.get("ingredients"):
            with_ingredients += 1
        if r.get("nutrition"):
            with_nutrition += 1
        if len(r.get("sources", [])) > 1:
            multi_source += 1

    print(f"\n  데이터 충실도:")
    print(f"    조리법(steps) 포함 : {with_steps:>5}건 ({with_steps/len(final)*100:.1f}%)")
    print(f"    재료 목록 포함      : {with_ingredients:>5}건 ({with_ingredients/len(final)*100:.1f}%)")
    print(f"    영양성분 포함       : {with_nutrition:>5}건 ({with_nutrition/len(final)*100:.1f}%)")
    print(f"    다중 소스 병합      : {multi_source:>5}건 ({multi_source/len(final)*100:.1f}%)")
    print(f"    조리방법 자동추론   : {inferred_count:>5}건")

    method_dist: Dict[str, int] = {}
    for r in final:
        m = r.get("cooking_method") or "기타"
        method_dist[m] = method_dist.get(m, 0) + 1
    print(f"\n  조리방법 분포 ({len(method_dist)}개):")
    for m, cnt in sorted(method_dist.items(), key=lambda x: -x[1]):
        pct = cnt / len(final) * 100
        bar = "█" * int(pct / 2)
        print(f"    {m:8s} {cnt:>5}건 ({pct:5.1f}%) {bar}")

    print(f"\n  식품군별 현황 ({len(cats)}개):")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])[:15]:
        print(f"    {cat}: {cnt}건")
    if len(cats) > 15:
        print(f"    ... 외 {len(cats) - 15}개")

    # ── 통합 재료 라벨 생성 ──
    ingr_map: Dict[str, str] = {}
    for r in final:
        for i in r.get("ingredients", []):
            name = _clean_name(i.get("name", ""))
            if name and len(name) >= 2:
                ingr_map[name] = i.get("category", _classify_ingredient(name))

    ingr_items = sorted([
        {"name": n, "category": c}
        for n, c in ingr_map.items()
    ], key=lambda x: x["name"])
    ingr_path = _save_json(ingr_items, LABEL_DIR / "unified_ingredients.json")
    print(f"\n  → 통합 재료명: {ingr_path} ({len(ingr_items)}개)")

    ingr_cat_dist: Dict[str, int] = {}
    for item in ingr_items:
        c = item["category"]
        ingr_cat_dist[c] = ingr_cat_dist.get(c, 0) + 1
    print(f"  재료 카테고리 분포:")
    for c, cnt in sorted(ingr_cat_dist.items(), key=lambda x: -x[1]):
        print(f"    {c}: {cnt}개")

    method_meta = []
    for name, info in _COOKING_METHOD_SCHEMA.items():
        cnt = method_dist.get(name, 0)
        method_meta.append({
            "name": name,
            "code": info["code"],
            "name_en": info["en"],
            "description": info["desc"],
            "count": cnt,
        })
    method_meta.sort(key=lambda x: -x["count"])
    method_path = _save_json(method_meta, LABEL_DIR / "cooking_methods.json")
    print(f"  → 조리방법 메타: {method_path} ({len(method_meta)}개)")

    return final


# ═══════════════════════════════════════════════════════════
# 통합 병합: 수집 결과 → 통합 라벨 JSON
# ═══════════════════════════════════════════════════════════

def merge_all_labels() -> Dict[str, Any]:
    """
    data/labels/ 아래 수집된 JSON 파일들을 읽어
    중복 제거 후 통합 식품명 라벨 파일을 생성한다.
    """
    print("\n[병합] 수집 데이터 통합 중...")
    all_names: Set[str] = set()
    source_stats: Dict[str, int] = {}

    for json_file in LABEL_DIR.glob("*.json"):
        if json_file.name == "merged_food_labels.json":
            continue
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                items = json.load(f)
        except Exception:
            continue

        if not isinstance(items, list):
            continue

        source = json_file.stem
        count = 0
        for item in items:
            name = item.get("name", "").strip()
            if name and len(name) >= 2:
                all_names.add(name)
                count += 1
        source_stats[source] = count

    merged = {
        "total_count": len(all_names),
        "sources": source_stats,
        "names": sorted(all_names),
    }

    path = _save_json(merged, LABEL_DIR / "merged_food_labels.json")
    print(f"  소스별 현황:")
    for src, cnt in source_stats.items():
        print(f"    {src}: {cnt}건")
    print(f"  -> 통합 저장: {path} (중복 제거 후 {len(all_names)}건)")
    return merged


# ═══════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════

def reformat_source_files() -> None:
    """개별 소스 파일을 보성녹차 양식으로 일괄 변환한다."""
    print("\n[정규화] 개별 소스 파일 → 통일 양식 변환")

    def _to_unified(raw: Dict[str, Any], source_name: str) -> Dict[str, Any]:
        """원본 레시피 → 보성녹차 스타일 통일 양식."""
        title = (raw.get("title") or "").strip()

        ingr_list = raw.get("ingredients", [])
        if ingr_list and isinstance(ingr_list[0], dict):
            names = [i.get("name", "").strip() for i in ingr_list if i.get("name")]
            raw_parts = []
            for i in ingr_list:
                n = (i.get("name") or "").strip()
                a = (i.get("amount") or "").strip()
                raw_parts.append(f"{n} {a}".strip() if a else n)
            ingredients_raw = ", ".join(raw_parts)
        elif ingr_list and isinstance(ingr_list[0], str):
            names = [n.strip() for n in ingr_list if n.strip()]
            ingredients_raw = raw.get("ingredients_main_raw", "") or raw.get("ingredients_raw", "")
            sub_raw = raw.get("ingredients_sub_raw", "")
            if sub_raw:
                ingredients_raw = ingredients_raw + " | " + sub_raw if ingredients_raw else sub_raw
        else:
            names = []
            ingredients_raw = raw.get("ingredients_raw", "")

        steps_raw = raw.get("steps", [])
        steps = []
        for idx, s in enumerate(steps_raw, 1):
            if isinstance(s, dict):
                desc = (s.get("description") or "").strip()
                if desc:
                    steps.append({"step": idx, "description": desc})
            elif isinstance(s, str) and s.strip():
                steps.append({"step": idx, "description": s.strip()})

        return {
            "id": raw.get("id", ""),
            "title": title,
            "category": (raw.get("category") or "").strip(),
            "ingredients_raw": ingredients_raw,
            "ingredients": names,
            "steps": steps,
            "description": (raw.get("description") or raw.get("summary") or "").strip(),
            "source": source_name,
        }

    source_configs = [
        ("recipes_public.json", "식품안전나라(COOKRCP01)"),
        ("recipes_epis.json", "EPIS(농림수산식품교육문화정보원)"),
        ("recipes_kimchi.json", "세계김치연구소(김치콘텐츠통합플랫폼)"),
    ]

    for fname, src_name in source_configs:
        path = RECIPE_DIR / fname
        if not path.exists():
            print(f"  ⚠ {fname} 없음, 건너뜀")
            continue
        with open(path, "r", encoding="utf-8") as f:
            raw_data = json.load(f)
        unified = [_to_unified(r, src_name) for r in raw_data]
        _save_json(unified, path)
        print(f"  ✓ {fname}: {len(unified)}건 변환")

    # nutrition — 영양 데이터도 동일 양식 (nutrition 필드만 간소화)
    nut_path = RECIPE_DIR / "recipes_nutrition.json"
    if nut_path.exists():
        with open(nut_path, "r", encoding="utf-8") as f:
            nut_data = json.load(f)
        unified_nut = []
        for r in nut_data:
            nut_raw = r.get("nutrients") or r.get("nutrition", {})
            nut_simple = {}
            for k, v in nut_raw.items():
                if isinstance(v, dict):
                    val = v.get("value")
                    unit = v.get("unit", "")
                    nut_simple[k] = f"{val}{unit}" if val is not None else ""
                else:
                    nut_simple[k] = str(v)
            unified_nut.append({
                "id": r.get("food_code") or r.get("id", ""),
                "title": (r.get("title") or "").strip(),
                "category": (r.get("category") or "").strip(),
                "ingredients_raw": (r.get("ingredients_raw") or ""),
                "ingredients": r.get("ingredients") if r.get("ingredients") else [],
                "steps": r.get("steps") if r.get("steps") else [],
                "nutrition": nut_simple,
                "description": (r.get("description") or "").strip(),
                "source": "식품의약품안전처(식품영양성분DB 통합자료집)",
            })
        _save_json(unified_nut, nut_path)
        print(f"  ✓ recipes_nutrition.json: {len(unified_nut)}건 변환")

    # boseong — 이미 깔끔하지만 필드 순서 통일
    bos_path = RECIPE_DIR / "recipes_boseong_tea.json"
    if bos_path.exists():
        with open(bos_path, "r", encoding="utf-8") as f:
            bos_data = json.load(f)
        unified_bos = []
        for r in bos_data:
            main_raw = r.get("ingredients_main_raw", "")
            sub_raw = r.get("ingredients_sub_raw", "")
            ingr_raw = r.get("ingredients_raw") or main_raw
            if sub_raw and "ingredients_raw" not in r:
                ingr_raw = ingr_raw + " | " + sub_raw if ingr_raw else sub_raw
            names = r.get("ingredients", [])
            if names and isinstance(names[0], dict):
                names = [i.get("name", "") for i in names]
            steps = []
            for idx, s in enumerate(r.get("steps", []), 1):
                desc = s.get("description", "") if isinstance(s, dict) else str(s)
                if desc.strip():
                    steps.append({"step": idx, "description": desc.strip()})
            unified_bos.append({
                "id": r.get("id", ""),
                "title": (r.get("title") or "").strip(),
                "category": (r.get("category") or "").strip(),
                "ingredients_raw": ingr_raw,
                "ingredients": names,
                "steps": steps,
                "description": (r.get("description") or "").strip(),
                "source": r.get("source", "전라남도 보성군(공공데이터포털)"),
            })
        _save_json(unified_bos, bos_path)
        print(f"  ✓ recipes_boseong_tea.json: {len(unified_bos)}건 변환")

    # recipes_all.json — 통합 파일도 동일 양식으로 변환
    all_path = RECIPE_DIR / "recipes_all.json"
    if all_path.exists():
        with open(all_path, "r", encoding="utf-8") as f:
            all_data = json.load(f)
        unified_all = []
        for r in all_data:
            ingr_list = r.get("ingredients", [])
            if ingr_list and isinstance(ingr_list[0], dict):
                names = [i.get("name", "").strip() for i in ingr_list if i.get("name")]
                raw_parts = []
                for i in ingr_list:
                    n = (i.get("name") or "").strip()
                    a = (i.get("amount") or "").strip()
                    raw_parts.append(f"{n} {a}".strip() if a else n)
                ingr_raw = r.get("ingredients_raw") or ", ".join(raw_parts)
            elif ingr_list and isinstance(ingr_list[0], str):
                names = [n.strip() for n in ingr_list if n.strip()]
                ingr_raw = r.get("ingredients_raw", "")
            else:
                names = []
                ingr_raw = r.get("ingredients_raw", "")

            steps = []
            for idx, s in enumerate(r.get("steps", []), 1):
                if isinstance(s, dict):
                    desc = (s.get("description") or "").strip()
                    if desc:
                        steps.append({"step": idx, "description": desc})
                elif isinstance(s, str) and s.strip():
                    steps.append({"step": idx, "description": s.strip()})

            sources = r.get("sources", [])
            source_str = r.get("source", "")
            if sources and not source_str:
                source_str = ", ".join(sources) if isinstance(sources, list) else str(sources)

            unified_all.append({
                "id": r.get("id", ""),
                "title": (r.get("title") or "").strip(),
                "category": (r.get("category") or "").strip(),
                "cooking_method": (r.get("cooking_method") or "").strip(),
                "cooking_method_code": (r.get("cooking_method_code") or "").strip(),
                "cooking_method_en": (r.get("cooking_method_en") or "").strip(),
                "ingredients_raw": ingr_raw,
                "ingredients": names,
                "steps": steps,
                "description": (r.get("description") or "").strip(),
                "source": source_str,
            })
        _save_json(unified_all, all_path)
        print(f"  ✓ recipes_all.json: {len(unified_all)}건 변환")

    print("  완료!\n")


def main():
    parser = argparse.ArgumentParser(description="식품명·레시피 데이터 수집기 (공공데이터)")
    parser.add_argument("--mfds", action="store_true", help="식품의약품안전처 식품 DB 수집")
    parser.add_argument("--recipe-api", action="store_true", help="식품안전나라 COOKRCP01 레시피 수집")
    parser.add_argument("--epis", action="store_true", help="EPIS 농림수산식품교육문화정보원 레시피 수집")
    parser.add_argument("--boseong", action="store_true", help="보성군 차 음식/디저트 레시피 수집")
    parser.add_argument("--kimchi", action="store_true", help="세계김치연구소 김치 레시피 수집")
    parser.add_argument("--nutrition", action="store_true", help="식품영양성분DB 통합자료집 수집")
    parser.add_argument("--normalize", action="store_true", help="전체 레시피 정규화 + 중복 제거")
    parser.add_argument("--reformat", action="store_true", help="개별 소스 파일을 통일 양식으로 변환")
    parser.add_argument("--merge", action="store_true", help="수집 결과 통합 병합")
    parser.add_argument("--all", action="store_true", help="전체 수집 + 병합")
    parser.add_argument("--mfds-key", type=str, default=None,
                        help="식약처 API 키 (또는 MFDS_API_KEY 환경변수)")
    parser.add_argument("--recipe-key", type=str, default=None,
                        help="식품안전나라 API 키 (또는 RECIPE_API_KEY 환경변수)")
    parser.add_argument("--epis-key", type=str, default=None,
                        help="EPIS API 키 (또는 EPIS_API_KEY 환경변수)")

    args = parser.parse_args()

    if not any([args.mfds, args.recipe_api, args.epis, args.boseong, args.kimchi,
                args.nutrition, args.normalize, args.reformat, args.merge, args.all]):
        parser.print_help()
        return

    mfds_key = args.mfds_key or os.getenv("MFDS_API_KEY", "")
    recipe_key = args.recipe_key or os.getenv("RECIPE_API_KEY", "")
    epis_key = args.epis_key or os.getenv("EPIS_API_KEY", "")

    if args.all or args.mfds:
        if not mfds_key:
            print("[오류] 식약처 API 키가 필요합니다.")
            print("  --mfds-key <키> 또는 환경변수 MFDS_API_KEY 설정")
        else:
            fetch_mfds_foods(mfds_key)

    if args.all or args.recipe_api:
        fetch_recipes(recipe_key or None)

    if args.all or args.epis:
        fetch_epis_recipes(epis_key or None)

    if args.all or args.boseong:
        fetch_boseong_tea()

    if args.all or args.kimchi:
        fetch_kimchi_recipes()

    if args.all or args.nutrition:
        if not mfds_key:
            print("[오류] 식약처 API 키가 필요합니다.")
            print("  --mfds-key <키> 또는 환경변수 MFDS_API_KEY 설정")
        else:
            fetch_nutrition_recipes(mfds_key)

    if args.all or args.reformat:
        reformat_source_files()

    if args.all or args.normalize:
        normalize_and_deduplicate()

    if args.all or args.merge:
        merge_all_labels()

    print("\n완료!")


if __name__ == "__main__":
    main()
