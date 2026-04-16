"""
규칙 기반 영수증 데이터 구조화 및 정규화 모델

PaddleOCR 결과를 받아 LLM 없이 규칙만으로:
1) 영수증 라인 분류 (상품/가격/헤더/푸터/구분선)
2) OCR 오류 보정 (한글 오타 사전)
3) 상품-가격 페어링
4) 상품명 정규화 (브랜드·용량·기호 제거)
5) 식품 필터링 (비식품 제거)
6) 카테고리 분류
7) 구조화된 JSON 출력

사용법:
  from rule_based_normalizer import RuleBasedNormalizer
  normalizer = RuleBasedNormalizer()
  result = normalizer.process(ocr_result)
"""

from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ═══════════════════════════════════════════════════════════════
#  OCR 오류 보정 사전
#  PaddleOCR이 한글 영수증에서 빈번하게 틀리는 패턴을 수집
# ═══════════════════════════════════════════════════════════════

OCR_CORRECTION_MAP: Dict[str, str] = {
    # ── 받침 혼동 ──
    "깨잎": "깻잎",
    "깨입": "깻잎",
    "깨닢": "깻잎",
    "갯잎": "깻잎",
    "깨앞": "깻잎",
    "감급": "감귤",
    "감굴": "감귤",
    "감골": "감귤",
    "방가루": "빵가루",
    "빵까루": "빵가루",
    "밀까루": "밀가루",
    "밀카루": "밀가루",
    "콩나묾": "콩나물",
    "콩나믈": "콩나물",
    "숙주나묾": "숙주나물",
    "게란": "계란",
    "겨란": "계란",
    "게랑": "계란",
    "겨랑": "계란",
    "겟란": "계란",
    "달갈": "달걀",
    "달갤": "달걀",
    "달결": "달걀",
    "데파": "대파",
    "데퍄": "대파",
    "양퍄": "양파",
    "양따": "양파",
    "감져": "감자",
    "갑자": "감자",
    "갑져": "감자",
    "고구며": "고구마",
    "고규마": "고구마",
    "뱃추": "배추",
    "배츄": "배추",
    "시굼치": "시금치",
    "시금취": "시금치",
    "양배츄": "양배추",
    "당긴": "당근",
    "당귄": "당근",
    "삼겹싸": "삼겹살",
    "삼겹쌀": "삼겹살",
    "삼격살": "삼겹살",
    "삼경살": "삼겹살",
    "목쌀": "목살",
    "항정쌀": "항정살",
    "갈매기쌀": "갈매기살",
    "닭가슴쌀": "닭가슴살",
    "부채쌀": "부채살",
    "차돌백이": "차돌박이",
    "차돌바기": "차돌박이",
    "갈취": "갈치",
    "참취": "참치",

    # ── 유사 자모 혼동 ──
    "오이스터소스": "굴소스",
    "브로꼴리": "브로콜리",
    "아보카또": "아보카도",
    "아보까도": "아보카도",
    "돗마토": "토마토",
    "토마또": "토마토",
    "또마토": "토마토",
    "바내나": "바나나",
    "블루배리": "블루베리",
    "블루배러": "블루베리",
    "딸끼": "딸기",
    "멸치엑젓": "멸치액젓",
    "멸치엑것": "멸치액젓",
    "깍뚜기": "깍두기",
    "깍뚜끼": "깍두기",

    # ── 영수증 특유 변형 ──
    "냉삼": "냉동삼겹살",

    # ── 가공식품 변형 ──
    "리쳄": "리챔",
    "리첌": "리챔",
    "참지캔": "참치캔",
    "참취캔": "참치캔",
    "라몐": "라면",
    "우유우": "우유",
    "요구르뜨": "요구르트",
    "요구르또": "요구르트",
    "요거뜨": "요거트",

    # ── 조미료 ──
    "고춧까루": "고춧가루",
    "고춧카루": "고춧가루",
    "고추까루": "고춧가루",
    "간쟝": "간장",
    "갼장": "간장",
    "된쟝": "된장",
    "고추쟝": "고추장",
    "참기릉": "참기름",
    "들기릉": "들기름",
    "식용류": "식용유",
    "올리브류": "올리브유",
}

# ── 정규식 기반 오류 패턴 (사전 매칭 후 추가 적용) ──
_OCR_REGEX_CORRECTIONS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"(\w)까루"), r"\1가루"),
    (re.compile(r"(\w)쌀$"), r"\1살"),
    (re.compile(r"배츄"), "배추"),
    (re.compile(r"(\w)쟝"), r"\1장"),
    (re.compile(r"(\w)릉$"), r"\1름"),
    (re.compile(r"(\w)묾$"), r"\1물"),
]


# ═══════════════════════════════════════════════════════════════
#  영수증 라인 분류 규칙
# ═══════════════════════════════════════════════════════════════

_SKIP_LINE = re.compile(
    r"사업자|전화|번호|주소|카드|승인|가맹점|계산대"
    r"|합\s*계|소\s*계|부가세|과세|면세|총액|지불|할인"
    r"|상품명|단가|수량|금액|판매일|신용|면세물품|과세물품"
    r"|포인트|적립|잔액|회원|거래|결제"
    r"|영수증|감사합니다|고객|안내|문의"
    r"|[=\-]{3,}"
)
_BARCODE_RE = re.compile(r"^\d{8,}$")
_PURE_PRICE_RE = re.compile(r"^[\d,]+\s*[#\*]?$")
_DATE_RE = re.compile(r"\d{4}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}")
_DATE_COMPACT_RE = re.compile(r"^\d{4}\d{2}\d{2}$")
_ITEM_NO_RE = re.compile(r"^\d{1,3}[)\.\s]+")

_PRICE_IN_LINE_RE = re.compile(r"([\d,]{3,})\s*원?\s*$")
_QUANTITY_PRICE_RE = re.compile(
    r"(\d+)\s*[*xX×]\s*([\d,]+)\s*원?\s*$"
)


class LineType:
    PRODUCT = "product"
    PRICE = "price"
    HEADER = "header"
    FOOTER = "footer"
    SEPARATOR = "separator"
    DATE = "date"
    BARCODE = "barcode"
    UNKNOWN = "unknown"


# ═══════════════════════════════════════════════════════════════
#  비식품 필터
# ═══════════════════════════════════════════════════════════════

_NON_FOOD_RE = re.compile(
    r"비닐|봉투|장바구니|포장|손잡이|에코백"
    r"|화장지|티슈|휴지|물티슈|키친타올"
    r"|세제|세탁|섬유유연|표백|주방세제|식기세척"
    r"|샴푸|린스|컨디셔너|바디워시|치약|칫솔|면도"
    r"|건전지|전구|테이프|접착|쓰레기"
    r"|마스크|반창고|밴드|면봉"
)


# ═══════════════════════════════════════════════════════════════
#  카테고리 분류 사전
# ═══════════════════════════════════════════════════════════════

CATEGORY_RULES: Dict[str, List[str]] = {
    "농산물/과일": [
        "사과", "배", "포도", "딸기", "바나나", "귤", "오렌지", "수박", "참외", "복숭아",
        "감", "단감", "홍시", "키위", "망고", "블루베리", "체리", "자몽", "레몬", "라임",
        "파인애플", "멜론", "자두", "살구", "무화과", "석류", "유자", "한라봉", "천혜향",
        "레드향", "샤인머스캣", "거봉", "청포도", "아보카도", "대추", "감귤",
    ],
    "농산물/채소": [
        "양파", "마늘", "감자", "고구마", "당근", "무", "배추", "양배추", "시금치", "상추",
        "깻잎", "파", "대파", "쪽파", "부추", "고추", "풋고추", "청양고추", "홍고추",
        "피망", "파프리카", "브로콜리", "콩나물", "숙주나물", "오이", "호박", "애호박",
        "단호박", "가지", "토마토", "방울토마토", "셀러리", "연근", "우엉",
        "생강", "옥수수", "미나리", "냉이", "달래", "쑥", "열무",
    ],
    "농산물/버섯": [
        "버섯", "팽이버섯", "새송이버섯", "표고버섯", "느타리버섯", "양송이버섯",
        "목이버섯", "송이버섯",
    ],
    "축산물/소고기": [
        "소고기", "한우", "등심", "안심", "갈비", "차돌박이", "불고기", "채끝",
        "부채살", "살치살", "양지", "사태", "우둔", "꽃등심",
    ],
    "축산물/돼지고기": [
        "삼겹살", "목살", "돼지고기", "대패삼겹", "항정살", "앞다리", "뒷다리",
        "갈매기살", "등갈비", "돼지갈비", "족발", "보쌈",
    ],
    "축산물/닭·오리": [
        "닭고기", "닭가슴살", "닭다리", "닭날개", "닭봉", "닭볶음탕",
        "오리고기", "오리훈제", "훈제오리",
    ],
    "축산물/계란": [
        "계란", "달걀", "유정란", "무항생제란", "메추리알",
    ],
    "수산물/생선": [
        "고등어", "갈치", "삼치", "연어", "참치", "광어", "우럭", "도미", "조기", "꽁치",
        "방어", "대구", "명태", "동태",
    ],
    "수산물/갑각류·패류": [
        "새우", "오징어", "문어", "낙지", "주꾸미", "꽃게", "대게",
        "조개", "바지락", "홍합", "굴", "전복", "가리비", "꼬막",
    ],
    "수산물/해조류·건어물": [
        "멸치", "김", "미역", "다시마", "해초", "어묵", "맛살",
    ],
    "유제품": [
        "우유", "치즈", "버터", "생크림", "요구르트", "요거트", "두유",
    ],
    "곡류·면류": [
        "쌀", "현미", "찹쌀", "잡곡", "보리", "귀리", "오트밀",
        "라면", "국수", "소면", "칼국수", "우동", "냉면", "당면",
        "파스타", "스파게티", "쌀국수",
    ],
    "빵·떡류": [
        "빵", "식빵", "바게트", "크루아상", "베이글",
        "떡", "떡볶이떡", "가래떡", "인절미",
        "밀가루", "부침가루", "튀김가루", "빵가루",
    ],
    "가공식품": [
        "만두", "피자", "햄", "소시지", "스팸", "리챔", "베이컨",
        "참치캔", "골뱅이캔", "즉석밥", "냉동밥",
        "돈까스", "치즈스틱", "감자튀김",
    ],
    "김치·절임": [
        "김치", "배추김치", "깍두기", "총각김치", "열무김치",
        "단무지", "피클", "장아찌",
    ],
    "양념·조미료": [
        "간장", "된장", "고추장", "쌈장", "식초",
        "소금", "설탕", "물엿", "올리고당", "꿀",
        "참기름", "들기름", "식용유", "올리브유",
        "고춧가루", "후추", "카레",
        "케첩", "마요네즈", "굴소스", "데리야끼",
        "다시다", "미원", "맛술", "미림",
        "젓갈", "액젓", "멸치액젓",
    ],
    "두부·콩류": [
        "두부", "순두부", "연두부", "유부",
        "콩", "땅콩", "호두", "아몬드", "캐슈넛", "잣",
    ],
    "음료": [
        "커피", "녹차", "홍차", "보리차",
        "주스", "콜라", "사이다", "탄산수", "생수",
        "에너지드링크", "이온음료", "식혜",
    ],
    "주류": [
        "맥주", "소주", "와인", "막걸리", "위스키", "사케",
    ],
    "과자·간식": [
        "과자", "초콜릿", "사탕", "젤리", "아이스크림",
        "시리얼", "그래놀라",
    ],
}

# 검색 최적화: (키워드, 카테고리) 를 키워드 길이 내림차순으로 정렬
_CATEGORY_INDEX: List[Tuple[str, str]] = []
for _cat, _kws in CATEGORY_RULES.items():
    for _kw in _kws:
        _CATEGORY_INDEX.append((_kw, _cat))
_CATEGORY_INDEX.sort(key=lambda x: -len(x[0]))


# ═══════════════════════════════════════════════════════════════
#  식품명 DB 로드 (매칭용)
# ═══════════════════════════════════════════════════════════════

_LABEL_DIR = Path(__file__).resolve().parent / "data" / "labels"
_DB_DIR = Path(__file__).resolve().parent / "data" / "db"


def _load_food_names() -> set:
    """unified_ingredients.json 에서 알려진 식품명 집합을 로드."""
    path = _LABEL_DIR / "unified_ingredients.json"
    if not path.exists():
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            return {item["name"] for item in json.load(f) if item.get("name")}
    except Exception:
        return set()


def _load_ingredients_db() -> List[Dict[str, str]]:
    """data/db/ingredients.json 에서 DB 재료 목록을 로드."""
    path = _DB_DIR / "ingredients.json"
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════
#  메인 클래스
# ═══════════════════════════════════════════════════════════════

class RuleBasedNormalizer:
    """
    규칙 기반 영수증 데이터 구조화 및 정규화 모델.

    PaddleOCR 결과를 받아 LLM 없이 순수 규칙으로 식품 데이터를 추출한다.

    파이프라인:
      OCR lines → 라인 분류 → OCR 보정 → 상품-가격 페어링
                → 상품명 정규화 → 비식품 필터링 → 카테고리 분류
                → DB 재료 매칭 → 구조화된 JSON 출력
    """

    def __init__(self):
        self._known_foods = _load_food_names()
        self._ingredients_db = _load_ingredients_db()
        self._ingr_name_index: Dict[str, Dict[str, str]] = {}
        for ingr in self._ingredients_db:
            norm = self._normalize_for_match(ingr["ingredientName"])
            self._ingr_name_index[norm] = ingr

    # ─── 텍스트 정규화 유틸 ─────────────────────────────────

    @staticmethod
    def _normalize_for_match(name: str) -> str:
        s = unicodedata.normalize("NFC", name.strip().lower())
        s = re.sub(r"[^\w가-힣]", "", s)
        return s

    # ─── 1단계: OCR 오류 보정 ───────────────────────────────

    @staticmethod
    def correct_ocr_errors(text: str) -> str:
        """OCR 오류 사전 + 정규식 패턴으로 텍스트를 보정한다."""
        corrected = text.strip()

        applied_dict = False
        for wrong, right in OCR_CORRECTION_MAP.items():
            if wrong in corrected:
                corrected = corrected.replace(wrong, right)
                applied_dict = True

        if not applied_dict:
            for pattern, replacement in _OCR_REGEX_CORRECTIONS:
                corrected = pattern.sub(replacement, corrected)

        return corrected

    # ─── 2단계: 영수증 라인 분류 ────────────────────────────

    @staticmethod
    def classify_line(text: str) -> str:
        """OCR 한 줄의 유형을 판별한다."""
        text = text.strip()
        if not text:
            return LineType.UNKNOWN

        if re.match(r"^[=\-·_]{3,}$", text):
            return LineType.SEPARATOR

        if _BARCODE_RE.match(text):
            return LineType.BARCODE

        if _PURE_PRICE_RE.match(text):
            return LineType.PRICE

        if _SKIP_LINE.search(text):
            if _DATE_RE.search(text):
                return LineType.DATE
            return LineType.HEADER

        if _DATE_RE.search(text) or _DATE_COMPACT_RE.match(text):
            return LineType.DATE

        has_korean = any("\uac00" <= c <= "\ud7a3" for c in text)
        if has_korean and len(text) >= 2:
            return LineType.PRODUCT

        if len(text) <= 3 and text.isdigit():
            return LineType.UNKNOWN

        return LineType.UNKNOWN

    # ─── 3단계: 상품-가격 페어링 ────────────────────────────

    def pair_products(
        self, ocr_lines: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        OCR 라인들을 분류하고, 상품명과 가격을 페어링한다.

        Returns:
            [{"product_name_raw": str, "amount_krw": int|None, "line_idx": int}, ...]
        """
        classified: List[Tuple[int, str, str]] = []
        for i, line in enumerate(ocr_lines):
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            line_type = self.classify_line(text)
            classified.append((i, text, line_type))

        pairs: List[Dict[str, Any]] = []

        for idx, (line_idx, text, ltype) in enumerate(classified):
            if ltype != LineType.PRODUCT:
                continue

            inline_price = self._extract_inline_price(text)
            product_text = self._strip_price_from_text(text)

            if not product_text or len(product_text) < 2:
                continue

            amount: Optional[int] = inline_price

            if amount is None:
                for j in range(idx + 1, min(idx + 4, len(classified))):
                    _, next_text, next_type = classified[j]
                    if next_type == LineType.PRICE:
                        amount = self._parse_price(next_text)
                        break
                    if next_type == LineType.PRODUCT:
                        break

            pairs.append({
                "product_name_raw": product_text,
                "amount_krw": amount,
                "line_idx": line_idx,
            })

        return pairs

    @staticmethod
    def _extract_inline_price(text: str) -> Optional[int]:
        """라인 내에 포함된 가격을 추출한다."""
        m = _QUANTITY_PRICE_RE.search(text)
        if m:
            try:
                qty = int(m.group(1))
                unit_price = int(m.group(2).replace(",", ""))
                return qty * unit_price
            except (ValueError, TypeError):
                pass

        m = _PRICE_IN_LINE_RE.search(text)
        if m:
            try:
                return int(m.group(1).replace(",", ""))
            except (ValueError, TypeError):
                pass
        return None

    @staticmethod
    def _strip_price_from_text(text: str) -> str:
        """텍스트 끝의 가격 부분을 제거하여 상품명만 남긴다."""
        text = _QUANTITY_PRICE_RE.sub("", text)
        text = _PRICE_IN_LINE_RE.sub("", text)
        text = text.strip()
        return text

    @staticmethod
    def _parse_price(text: str) -> Optional[int]:
        """가격 문자열을 정수로 파싱한다."""
        cleaned = re.sub(r"[#\*원\s]", "", text).replace(",", "")
        try:
            return int(cleaned)
        except (ValueError, TypeError):
            return None

    # ─── 4단계: 상품명 정규화 ───────────────────────────────

    _LEADING_NUM = re.compile(r"^\d{1,3}[)\.\s]+")
    _BRAND_PAREN = re.compile(r"\(.*?\)")
    _TRAILING_SPEC = re.compile(
        r"\s*[\(\[]?\s*\d+[\s\*xX×]*\d*\s*"
        r"[gGmMlLkKcC개입봉지팩맥단인분세트호]*\s*[\)\]]?\s*$"
    )
    _MISC_SYMBOLS = re.compile(r"[#\*\$\|/\\:]+")
    _MULTI_SPACE = re.compile(r"\s{2,}")

    _ABBREVIATION_MAP: Dict[str, str] = {
        "삼겹": "삼겹살",
        "목심": "목살",
        "닭가슴": "닭가슴살",
        "양송이": "양송이버섯",
        "팽이": "팽이버섯",
        "새송이": "새송이버섯",
        "느타리": "느타리버섯",
        "표고": "표고버섯",
    }

    def normalize_product_name(self, raw_name: str) -> str:
        """상품명에서 번호·용량·기호 등을 제거하고 핵심 이름만 남긴다."""
        name = raw_name.strip()
        name = self._LEADING_NUM.sub("", name)
        name = self._MISC_SYMBOLS.sub(" ", name)
        name = self._TRAILING_SPEC.sub("", name)
        name = self._BRAND_PAREN.sub("", name)
        name = self._MULTI_SPACE.sub(" ", name).strip()

        if name in self._ABBREVIATION_MAP:
            name = self._ABBREVIATION_MAP[name]

        return name if name else raw_name.strip()

    # ─── 5단계: 비식품 필터링 ───────────────────────────────

    @staticmethod
    def is_food_item(name: str) -> bool:
        """식품인지 판별한다. 비식품이면 False."""
        if _NON_FOOD_RE.search(name):
            return False
        if len(name) < 2:
            return False
        if re.match(r"^[\d\s,.]+$", name):
            return False
        return True

    # ─── 6단계: 카테고리 분류 ───────────────────────────────

    @staticmethod
    def classify_category(name: str) -> Dict[str, str]:
        """식품명에서 카테고리를 판별한다 (긴 키워드 우선 매칭)."""
        lower = name.lower()
        for kw, cat in _CATEGORY_INDEX:
            if kw in lower:
                if "/" in cat:
                    major, sub = cat.split("/", 1)
                else:
                    major, sub = cat, ""
                return {"major": major, "sub": sub, "full": cat}
        return {"major": "기타", "sub": "", "full": "기타"}

    # ─── 7단계: DB 재료 매칭 ────────────────────────────────

    def match_to_ingredient(
        self, name: str, threshold: float = 0.5
    ) -> Optional[Dict[str, Any]]:
        """정규화된 식품명을 DB 재료와 매칭한다."""
        norm = self._normalize_for_match(name)

        if norm in self._ingr_name_index:
            ingr = self._ingr_name_index[norm]
            return {
                "ingredientId": ingr["ingredientId"],
                "ingredientName": ingr["ingredientName"],
                "category": ingr["category"],
                "similarity": 1.0,
            }

        for ingr_norm, ingr in self._ingr_name_index.items():
            if norm in ingr_norm or ingr_norm in norm:
                return {
                    "ingredientId": ingr["ingredientId"],
                    "ingredientName": ingr["ingredientName"],
                    "category": ingr["category"],
                    "similarity": 0.9,
                }

        best_score = 0.0
        best_ingr = None
        for ingr_norm, ingr in self._ingr_name_index.items():
            score = SequenceMatcher(None, norm, ingr_norm).ratio()
            if score > best_score:
                best_score = score
                best_ingr = ingr

        if best_ingr and best_score >= threshold:
            return {
                "ingredientId": best_ingr["ingredientId"],
                "ingredientName": best_ingr["ingredientName"],
                "category": best_ingr["category"],
                "similarity": round(best_score, 4),
            }
        return None

    # ─── 매장/날짜 추출 ─────────────────────────────────────

    @staticmethod
    def extract_metadata(
        ocr_lines: List[Dict[str, Any]]
    ) -> Dict[str, Optional[str]]:
        """OCR 전체 텍스트에서 매장명과 구매 날짜를 추출한다."""
        store_name: Optional[str] = None
        purchase_date: Optional[str] = None

        _STORE_KW = re.compile(r"마트|스토어|슈퍼|식자재|하나로|이마트|홈플러스|롯데|농협")
        _DATE_PATTERNS = [
            re.compile(r"(\d{4})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})[일]?"),
            re.compile(r"(\d{4})(\d{2})(\d{2})"),
        ]

        for line in ocr_lines[:15]:
            text = str(line.get("text", "")).strip()
            if not store_name and _STORE_KW.search(text):
                store_name = re.sub(r"^[\(\)주]+", "", text).strip()

        for line in ocr_lines[:25]:
            text = str(line.get("text", "")).strip()
            for dp in _DATE_PATTERNS:
                m = dp.search(text)
                if m:
                    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
                    if 2000 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31:
                        purchase_date = f"{y:04d}-{mo:02d}-{d:02d}"
                        break
            if purchase_date:
                break

        return {"store_name": store_name, "purchase_date": purchase_date}

    # ─── 전체 파이프라인 ────────────────────────────────────

    def process(
        self,
        ocr_result: Dict[str, Any],
        *,
        match_db: bool = True,
    ) -> Dict[str, Any]:
        """
        PaddleOCR 결과(또는 동일 스키마)를 받아 전체 정규화 파이프라인을 실행한다.

        Args:
            ocr_result: {"all_texts": [{"text": str, "confidence": float}, ...], ...}
            match_db: True이면 DB 재료 매칭까지 수행

        Returns:
            {
                "store_name": str | None,
                "purchase_date": str | None,
                "processed_at": str,
                "source_image": str,
                "items": [{
                    "product_name_raw": str,
                    "product_name": str,
                    "category_major": str,
                    "category_sub": str,
                    "amount_krw": int | None,
                    "ingredient_match": {...} | None,
                }],
                "item_count": int,
                "model": "rule_based_v1",
            }
        """
        all_texts = ocr_result.get("all_texts") or []
        meta = self.extract_metadata(all_texts)

        raw_pairs = self.pair_products(all_texts)

        items: List[Dict[str, Any]] = []
        seen: set = set()

        for pair in raw_pairs:
            raw_name = pair["product_name_raw"]

            corrected = self.correct_ocr_errors(raw_name)

            normalized = self.normalize_product_name(corrected)
            if not normalized or len(normalized) < 2:
                continue

            if not self.is_food_item(normalized):
                continue

            dedup_key = self._normalize_for_match(normalized)
            if dedup_key in seen:
                continue
            seen.add(dedup_key)

            cat = self.classify_category(normalized)

            if cat["major"] == "기타" and not self._is_known_food(normalized):
                continue

            item: Dict[str, Any] = {
                "product_name_raw": raw_name,
                "product_name": normalized,
                "category_major": cat["major"],
                "category_sub": cat["sub"],
                "amount_krw": pair["amount_krw"],
                "notes": "",
            }

            if corrected != raw_name:
                item["notes"] = f"OCR 보정: {raw_name} → {corrected}"

            if match_db:
                ingr_match = self.match_to_ingredient(normalized)
                item["ingredient_match"] = ingr_match

            items.append(item)

        return {
            "store_name": meta["store_name"],
            "purchase_date": meta["purchase_date"],
            "processed_at": datetime.now().isoformat(timespec="seconds"),
            "source_image": str(ocr_result.get("image_path", "")),
            "items": items,
            "item_count": len(items),
            "model": "rule_based_v1",
        }

    def _is_known_food(self, name: str) -> bool:
        """식품명 DB에 존재하는 이름인지 확인한다."""
        stripped = re.sub(r"\s+", "", name)
        for label in self._known_foods:
            if label in stripped or stripped in label:
                return True
        return False

    # ─── Qwen 보정 결과와 동일한 포맷으로 변환 ──────────────

    def to_qwen_compatible(
        self, result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """process() 결과를 Qwen 보정 결과와 동일한 스키마로 변환한다."""
        items = []
        for item in result.get("items", []):
            items.append({
                "product_name": item["product_name"],
                "amount_krw": item["amount_krw"],
                "notes": item.get("notes", ""),
            })
        return {
            "items": items,
            "model": "rule_based_v1",
        }


# ═══════════════════════════════════════════════════════════════
#  CLI 진입점
# ═══════════════════════════════════════════════════════════════

def print_result(result: Dict[str, Any]) -> None:
    """정규화 결과를 터미널에 출력한다."""
    print("\n" + "=" * 65)
    print(" 규칙 기반 정규화 결과")
    print("=" * 65)
    if result.get("store_name"):
        print(f"  매장: {result['store_name']}")
    if result.get("purchase_date"):
        print(f"  날짜: {result['purchase_date']}")
    print(f"  모델: {result.get('model', '')}")

    items = result.get("items", [])
    print(f"\n  [상품 목록] ({len(items)}개)")
    print("  " + "-" * 80)
    print(f"  {'상품명':<18s} {'카테고리':<16s} {'금액':>10s} {'DB 매칭':>12s}  비고")
    print("  " + "-" * 80)
    for it in items:
        amt = it.get("amount_krw")
        amt_s = f"{amt:,}원" if isinstance(amt, int) else "-"
        cat = f"{it.get('category_major','')}/{it.get('category_sub','')}"
        match = it.get("ingredient_match")
        match_s = f"{match['similarity']:.0%}" if match else "없음"
        notes = it.get("notes", "")
        print(f"  {it['product_name']:<18s} {cat:<16s} {amt_s:>10s} {match_s:>12s}  {notes}")
    print("=" * 65)


def main():
    import sys

    if len(sys.argv) < 2:
        print("사용법: python rule_based_normalizer.py <영수증_이미지_경로>")
        return

    from receipt_ocr import ReceiptOCR

    image_path = sys.argv[1]
    ocr = ReceiptOCR()
    ocr_result = ocr.analyze_receipt(image_path)

    normalizer = RuleBasedNormalizer()
    result = normalizer.process(ocr_result)
    print_result(result)


if __name__ == "__main__":
    main()
