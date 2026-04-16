"""
영수증 OCR 결과 정규화 및 저장 모듈

PaddleOCR + Qwen 보정 결과를 받아서:
1) 상품명 정규화 (번호·용량·기호 제거, 카테고리 분류)
2) 구조화된 데이터로 변환
3) CSV / JSON 파일로 저장
"""

from __future__ import annotations

import csv
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── 대분류 → 소분류 → 키워드 ──
# 구조: { "대분류/소분류": [키워드, ...] }
# 나중에 식품명 데이터 추가 시 여기에 키워드만 넣으면 됨

CATEGORY_MAP = {
    # ═══ 신선 식재료 ═══

    "신선 식재료/농산물": [
        # 과일
        "사과", "배", "포도", "딸기", "바나나", "귤", "오렌지", "수박", "참외", "복숭아",
        "감", "단감", "홍시", "곶감", "키위", "망고", "블루베리", "체리", "자몽", "레몬",
        "라임", "파인애플", "멜론", "자두", "살구", "무화과", "석류", "유자", "한라봉",
        "천혜향", "레드향", "샤인머스캣", "거봉", "청포도", "아보카도", "대추", "감귤",
        # 채소
        "양파", "마늘", "감자", "고구마", "당근", "무", "배추", "양배추", "시금치", "상추",
        "깻잎", "깨잎", "파", "대파", "쪽파", "부추", "고추", "풋고추", "청양고추", "홍고추",
        "피망", "파프리카", "브로콜리", "콩나물", "숙주나물", "오이", "호박", "애호박",
        "단호박", "가지", "토마토", "방울토마토", "대추토마토", "셀러리", "연근", "우엉",
        "생강", "옥수수", "미나리", "냉이", "달래", "쑥", "열무", "깐마늘",
        # 버섯
        "버섯", "팽이버섯", "새송이", "새송이버섯", "표고버섯", "느타리버섯", "양송이버섯",
        # 두부·콩류
        "두부", "순두부", "연두부", "유부", "콩", "콩나물",
        # 견과
        "땅콩", "호두", "아몬드", "캐슈넛", "잣",
        # 김치·절임
        "김치", "깍두기", "단무지", "피클", "젓갈",
    ],

    "신선 식재료/곡류": [
        "쌀", "현미", "찹쌀", "잡곡", "보리", "귀리", "수수", "기장", "율무", "흑미",
        "찰보리", "오트밀",
    ],

    "신선 식재료/축산물": [
        "소고기", "한우", "등심", "안심", "갈비", "차돌박이", "불고기", "채끝",
        "삼겹살", "목살", "돼지고기", "대패삼겹", "항정살", "앞다리", "뒷다리", "갈매기살",
        "닭고기", "닭가슴살", "닭다리", "닭날개", "닭볶음탕",
        "오리고기", "양고기",
        "곱창", "대창", "막창",
        "계란", "달걀",
    ],

    "신선 식재료/수산물": [
        "고등어", "갈치", "삼치", "연어", "참치", "광어", "우럭", "도미", "조기", "꽁치",
        "새우", "오징어", "문어", "낙지", "주꾸미", "꽃게", "대게", "킹크랩",
        "조개", "바지락", "홍합", "굴", "전복", "가리비",
        "멸치", "김", "미역", "다시마", "해초",
    ],

    # ═══ 가공 식재료 ═══

    "가공 식재료/유가공품": [
        "우유", "저지방우유", "멸균우유", "치즈", "슬라이스치즈", "모짜렐라", "크림치즈",
        "버터", "마가린", "생크림", "휘핑크림",
        "요구르트", "요거트", "요플레", "그릭요거트",
        "두유", "아몬드밀크", "귀리우유",
    ],

    "가공 식재료/육가공품": [
        "소시지", "비엔나소시지", "프랑크소시지", "부어스트",
        "햄", "베이컨", "스팸", "런천미트",
        "족발", "보쌈", "훈제오리",
    ],

    "가공 식재료/수산가공품": [
        "어묵", "맛살", "게맛살", "참치캔", "연어캔", "골뱅이캔",
        "새우김", "김자반", "조미김", "곱창김",
        "젓갈", "액젓", "까나리", "멸치액젓",
    ],

    "가공 식재료/면류": [
        "라면", "컵라면", "국수", "소면", "칼국수", "우동", "냉면", "당면",
        "파스타", "스파게티", "펜네", "마카로니",
        "쌀국수", "메밀국수",
    ],

    "가공 식재료/빵류": [
        "빵", "식빵", "모닝빵", "바게트", "크루아상", "베이글", "도넛",
        "케이크", "머핀", "호떡", "붕어빵",
        "빵가루", "밀가루", "부침가루", "튀김가루",
        "떡", "떡볶이떡", "가래떡", "인절미", "송편",
    ],

    # ═══ 조미 및 양념 ═══

    "조미 및 양념/장류·소스": [
        "간장", "진간장", "국간장", "양조간장", "된장", "고추장", "쌈장", "청국장",
        "식초", "현미식초", "사과식초",
        "케첩", "마요네즈", "머스타드", "칠리소스", "굴소스", "데리야끼",
        "카레", "카레분말", "다시다", "미원", "맛술", "미림",
        "소금", "설탕", "물엿", "올리고당", "꿀",
    ],

    "조미 및 양념/유지류·분말": [
        "식용유", "카놀라유", "포도씨유", "올리브유", "해바라기유", "아보카도오일",
        "참기름", "들기름", "깨기름",
        "고춧가루", "후추", "통후추", "카레가루", "생강가루", "마늘분",
        "계피", "겨자", "와사비",
    ],
}

_MERGED_LABEL_PATH = Path(__file__).resolve().parent / "data" / "labels" / "merged_food_labels.json"


def _load_merged_labels() -> set:
    """data/labels/merged_food_labels.json 에서 수집된 식품명 목록을 불러온다."""
    if not _MERGED_LABEL_PATH.exists():
        return set()
    try:
        with open(_MERGED_LABEL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("names", []))
    except Exception:
        return set()


EXTRA_FOOD_NAMES: set = _load_merged_labels()

_ITEM_NO_PREFIX = re.compile(r"^\d{2,3}\s*")
_BRAND_PAREN = re.compile(r"^[\(\)주초푸삼립농심팔도크라운CJ오뚜기]+\)")
_TRAILING_SPEC = re.compile(
    r"\s*[\(\[]?\s*\d+[\s\*xX×]*\d*\s*"
    r"[gGmMlLkKcC개입봉지팩맥단인분세트호]*\s*[\)\]]?\s*$"
)
_LEADING_NUM = re.compile(r"^\d{1,3}[)\.\s]+")
_MISC_SYMBOLS = re.compile(r"[#\*\$\|/\\:]+")
_MULTI_SPACE = re.compile(r"\s{2,}")
_JUNK_LINE = re.compile(
    r"^[\d\s/\-\.\:,]+$"
    r"|^[가-힣]{0,2}:.*$"
    r"|사업자|대표|주소|전화|번호|계산대|토요일|일요일|월요일|화요일|수요일|목요일|금요일"
    r"|합계|소계|부가세|과세|면세|카드|승인|할인|거스름|영수증|감사합니다"
    r"|^[/\-=]+$",
    re.IGNORECASE,
)


def _is_junk(text: str) -> bool:
    """매장 메타데이터, 구분선 등 비상품 텍스트인지 판별한다."""
    return bool(_JUNK_LINE.search(text))


def normalize_product_name(raw_name: str) -> str:
    """상품명에서 번호, 용량, 기호 등을 제거하고 핵심 이름만 남긴다."""
    name = raw_name.strip()
    name = _LEADING_NUM.sub("", name)
    name = _ITEM_NO_PREFIX.sub("", name)
    name = _BRAND_PAREN.sub("", name)
    name = _MISC_SYMBOLS.sub(" ", name)
    name = _TRAILING_SPEC.sub("", name)
    name = re.sub(r"\(.*?\)", "", name)
    name = _MULTI_SPACE.sub(" ", name).strip()
    return name if name else raw_name.strip()


def classify_category(product_name: str) -> Dict[str, str]:
    """
    상품명으로부터 카테고리를 판별한다 (긴 키워드 우선 매칭).

    Returns:
        {"major": "대분류", "sub": "소분류", "full": "대분류/소분류"}
    """
    lower = product_name.lower()
    best_full = "기타"
    best_len = 0
    for category, keywords in CATEGORY_MAP.items():
        for kw in keywords:
            if kw in lower and len(kw) > best_len:
                best_full = category
                best_len = len(kw)

    if best_full == "기타" and EXTRA_FOOD_NAMES:
        stripped = re.sub(r"\s+", "", product_name)
        for label in EXTRA_FOOD_NAMES:
            if label in stripped or stripped in label:
                best_full = "미분류 식품"
                break

    if "/" in best_full:
        major, sub = best_full.split("/", 1)
    else:
        major, sub = best_full, ""

    return {"major": major, "sub": sub, "full": best_full}


def extract_store_and_date(all_texts: List[Dict[str, Any]]) -> Dict[str, Optional[str]]:
    """OCR 전체 텍스트에서 매장명과 날짜를 추출한다."""
    store_name = None
    purchase_date = None

    for item in all_texts[:10]:
        text = item.get("text", "")
        if not store_name and ("마트" in text or "식자재" in text or "스토어" in text or "슈퍼" in text):
            cleaned = re.sub(r"^[\(\)주]+", "", text).strip()
            store_name = cleaned

    date_patterns = [
        re.compile(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})[일]?"),
        re.compile(r"(\d{4})(\d{2})(\d{2})"),
    ]
    for item in all_texts[:20]:
        text = item.get("text", "")
        for dp in date_patterns:
            m = dp.search(text)
            if m:
                y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                    purchase_date = f"{y:04d}-{mo:02d}-{d:02d}"
                    break
        if purchase_date:
            break

    return {"store_name": store_name, "purchase_date": purchase_date}


def normalize_receipt_data(
    ocr_result: Dict[str, Any],
    qwen_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    OCR 결과(+ 선택적 Qwen 보정 결과)를 정규화된 구조로 변환한다.

    Returns:
        {
            "store_name": str | None,
            "purchase_date": str | None,
            "processed_at": str (ISO 형식),
            "source_image": str,
            "items": [
                {
                    "product_name_raw": str,
                    "product_name": str (정규화),
                    "category_major": str (대분류),
                    "category_sub": str (소분류),
                    "amount_krw": int | None,
                    "notes": str,
                },
                ...
            ],
            "item_count": int,
        }
    """
    all_texts = ocr_result.get("all_texts") or []
    meta = extract_store_and_date(all_texts)

    if qwen_result and qwen_result.get("items"):
        raw_items = qwen_result["items"]
    else:
        raw_items = []
        for fi in ocr_result.get("food_items") or []:
            raw_items.append({
                "product_name": fi.get("name", ""),
                "amount_krw": None,
                "notes": "",
            })

    items: List[Dict[str, Any]] = []
    seen_names: set = set()
    for it in raw_items:
        raw = str(it.get("product_name", "")).strip()
        if not raw:
            continue

        if _is_junk(raw):
            continue

        normalized = normalize_product_name(raw)
        if not normalized or len(normalized) < 2:
            continue

        if _is_junk(normalized):
            continue

        dedup_key = re.sub(r"\s+", "", normalized.lower())
        if dedup_key in seen_names:
            continue
        seen_names.add(dedup_key)

        cat = classify_category(normalized)

        if cat["major"] == "기타" and not qwen_result:
            continue

        amt = it.get("amount_krw")
        if amt is not None:
            try:
                amt = int(str(amt).replace(",", ""))
            except (TypeError, ValueError):
                amt = None

        items.append({
            "product_name_raw": raw,
            "product_name": normalized,
            "category_major": cat["major"],
            "category_sub": cat["sub"],
            "amount_krw": amt,
            "notes": str(it.get("notes", "")).strip(),
        })

    return {
        "store_name": meta["store_name"],
        "purchase_date": meta["purchase_date"],
        "processed_at": datetime.now().isoformat(timespec="seconds"),
        "source_image": str(ocr_result.get("image_path", "")),
        "items": items,
        "item_count": len(items),
    }


def save_as_json(data: Dict[str, Any], output_path: str) -> str:
    """정규화된 데이터를 JSON 파일로 저장한다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return str(path)


def save_as_csv(data: Dict[str, Any], output_path: str) -> str:
    """정규화된 데이터를 CSV 파일로 저장한다. 한 행 = 한 상품."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = [
        "store_name", "purchase_date", "processed_at", "source_image",
        "product_name_raw", "product_name", "category_major", "category_sub",
        "amount_krw", "notes",
    ]
    file_exists = path.exists() and path.stat().st_size > 0

    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()

        common = {
            "store_name": data.get("store_name") or "",
            "purchase_date": data.get("purchase_date") or "",
            "processed_at": data.get("processed_at") or "",
            "source_image": data.get("source_image") or "",
        }
        for item in data.get("items") or []:
            row = {**common, **item}
            writer.writerow(row)

    return str(path)


def print_normalized(data: Dict[str, Any]) -> None:
    """정규화 결과를 터미널에 출력한다."""
    print("\n" + "=" * 60)
    print(" 정규화 결과")
    print("=" * 60)
    if data.get("store_name"):
        print(f"  매장: {data['store_name']}")
    if data.get("purchase_date"):
        print(f"  날짜: {data['purchase_date']}")
    print(f"  처리: {data.get('processed_at', '')}")
    print(f"  이미지: {data.get('source_image', '')}")

    items = data.get("items") or []
    print(f"\n  [상품 목록] ({len(items)}개)")
    print("  " + "-" * 72)
    print(f"  {'상품명':<20s} {'대분류':<14s} {'소분류':<12s} {'금액':>10s}")
    print("  " + "-" * 72)
    for it in items:
        amt = it.get("amount_krw")
        amt_s = f"{amt:,}원" if isinstance(amt, int) else "-"
        major = it.get("category_major", "")
        sub = it.get("category_sub", "")
        print(f"  {it['product_name']:<20s} {major:<14s} {sub:<12s} {amt_s:>10s}")
    print("=" * 60)
