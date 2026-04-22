from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
import json
import os
from pathlib import Path
import re
from statistics import mean
from typing import Mapping

from .ingredient_dictionary import load_ingredient_lookup
from .receipt_rules import NonItemCategoryRule, load_receipt_rules


LOW_CONFIDENCE_THRESHOLD = 0.80
ROW_GROUP_TOLERANCE = 26.0

DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})\s*[./-]\s*(?P<month>\d{1,2})\s*[./-]\s*(?P<day>\d{1,2})"),
    re.compile(r"(?P<year>\d{2})\s*[./-]\s*(?P<month>\d{1,2})\s*[./-]\s*(?P<day>\d{1,2})"),
    re.compile(r"(?P<year>20\d{2})년\s*(?P<month>\d{1,2})월\s*(?P<day>\d{1,2})일"),
)
QUANTITY_PATTERN = re.compile(
    r"(?P<quantity>\d+(?:\.\d+)?)\s*(?P<unit>kg|g|ml|l|L|개|봉|팩|병|캔|묶음)"
)
POS_ITEM_PATTERN = re.compile(
    r"^(?P<line_no>\d{1,2})\s+(?P<name>.+?)\s+"
    r"(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
)
OCR_NOISY_POS_PATTERN = re.compile(
    r"^(?:(?P<barcode_prefix>\*?\d{8,})\s+)?"
    r"(?P<line_no>\d{1,3})\s+"
    r"(?P<name>.+?)\s+"
    r"(?:(?P<barcode_mid>\*?\d{8,})\s+)?"
    r"(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
)
OCR_NOISY_POS_INFERRED_QTY_PATTERN = re.compile(
    r"^(?:(?P<barcode_prefix>\*?\d{8,})\s+)?"
    r"(?P<line_no>\d{1,3})\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
)
LOWRES_CODED_ITEM_PATTERN = re.compile(
    r"^(?P<barcode_prefix>\*?[A-Z0-9]{8,})\s+"
    r"(?P<line_no>\d{1,2})\s+"
    r"(?P<name>.+?)\s+"
    r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d+)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
COMPACT_BARCODE_ITEM_PATTERN = re.compile(
    r"^(?P<barcode>\*?\d{8,})\s+"
    r"(?:(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+)?"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
)
BARCODE_UNIT_PRICE_QTY_PATTERN = re.compile(
    r"^(?P<barcode>\*?\d{8,})\s+"
    r"(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)$"
)
COMPACT_BARCODE_INFERRED_QTY_PATTERN = re.compile(
    r"^(?P<barcode>\*?\d{8,})\s+"
    r"(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+"
    r"(?P<garbage>[^\d\s]+)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
)
NAME_QTY_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<quantity>\d+(?:\.\d+)?)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
NAME_UNIT_PRICE_TIMES_QTY_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+"
    r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+)\s*[x×X]\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
NAME_BARCODE_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<barcode>\*?\d{8,})\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
NAME_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
NAME_QTY_ONLY_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<quantity>\d+(?:\.\d+)?)$"
)
COMPACT_NAME_QTY_ONLY_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<quantity>\d)$"
)
COMPACT_NAME_QTY_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<quantity>\d)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+)$"
)
COMPACT_NAME_QTY_LARGE_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<quantity>\d)(?P<amount>\d{2}[,.]\d{3})$"
)
COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<quantity>\d)(?P<amount>\d{1,3}(?:[,.]\d{3})+)$"
)
COMPACT_NAME_QTY_GIFT_NO_SPACE_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<quantity>\d)\s*증정품$"
)
COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>[가-힣A-Za-z][가-힣A-Za-z\s]+?)(?P<quantity>\d)(?P<amount>\d{3,4})$"
)
COMPACT_UNIT_PRICE_QTY_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<unit_price>\d{1,3}(?:[,.]\d{3})+)(?P<quantity>\d)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+)$"
)
COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<unit_price>\d{1,3}(?:[,.]\d{3})+)(?P<quantity>\d)(?P<amount>\d{1,3}(?:[,.]\d{3})+)$"
)
COMPACT_UNIT_PRICE_QTY_AMOUNT_MIXED_SPACE_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<unit_price>\d{1,3}(?:[,.]\d{3})+)(?P<quantity>\d)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+)$"
)
COMPACT_GIFT_PATTERN = re.compile(
    r"^(?P<name>.+?)(?P<unit_price>\d{2,3}(?:[,.]\d{3})?)(?P<quantity>\d)\s*증정품$"
)
NAME_GIFT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<quantity>\d+(?:\.\d+)?)\s+증정품$"
)
NUMERIC_DETAIL_ROW_PATTERN = re.compile(
    r"^(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d{1,5})\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
CODE_NUMERIC_DETAIL_ROW_PATTERN = re.compile(
    r"^(?P<code>\d{6,})\s+"
    r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d+)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
CODE_PLACEHOLDER_AMOUNT_ROW_PATTERN = re.compile(
    r"^(?P<code>\d{6,})\s+"
    r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d+)\s+"
    r"(?P<placeholder>[-_!|IlTt—–−]+)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
CODE_TIMES_AMOUNT_ROW_PATTERN = re.compile(
    r"^(?P<code>\d{6,})\s+"
    r"1\s*[x×]\s*/?\s*"
    r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d+)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)"
    r"(?:\s+(?P<placeholder>[-_!|IlTt—–−]+))?$"
)
INCOMPLETE_CODE_DETAIL_ROW_PATTERN = re.compile(
    r"^(?P<code>\d{6,})\s+(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d{1,5})\s+(?P<quantity>\d+(?:\.\d+)?)$"
)
PRICE_PATTERN = re.compile(r"^\d{1,3}(?:[,.]\d{3})+$|^\d+$")
COUNT_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
BARCODE_PATTERN = re.compile(r"^\*?\d{8,}$")
DASH_PATTERN = re.compile(r"^[\-\_=]{3,}$")

TOTAL_KEYWORDS = (
    "합계",
    "계",
    "총계",
    "구매금액",
    "결제금액",
    "결제대상액",
    "결제대상금액",
    "최종결제",
    "과세물품가액",
    "과세물품",
    "공급가액",
    "부가세",
    "세액",
    "현금",
    "카드결제",
)
PAYMENT_KEYWORDS = ("구매금액", "결제금액", "결제대상액", "결제대상금", "결제대상금액", "최종결제", "할인총금액", "현금", "카드결제")
DATE_HINT_KEYWORDS = ("판매일", "구매", "주문", "결제", "거래일")
FOOTER_KEYWORDS = (
    "합계",
    "총계",
    "구매금액",
    "부가세",
    "세액",
    "물품가액",
    "카드",
    "카드승인",
    "신용결제",
    "현금",
    "할인",
    "과세",
    "과세합계",
    "과세물품가액",
    "과세물품",
    "공급가액",
    "면세",
    "결제금액",
    "결제대상액",
    "결제대상금액",
    "최종결제",
    "주문번호",
)
HEADER_KEYWORDS = ("상품명", "단가", "수량", "금액", "주문번호", "판매")
NOISE_KEYWORDS = (
    "행사",
    "보증금",
    "할인",
    "승인",
    "안내",
    "감사",
    "교환",
    "환불",
    "사업자",
    "대표",
    "전화",
    "TEL",
    "www",
    "주소",
)
STRUCTURAL_NOISE_KEYWORDS = (
    "쿠폰",
    "코드",
    "봉투",
    "재사용",
    "물품가액",
    "부가세",
    "결제",
    "합계",
    "총계",
    "과세",
    "면세",
)
VENDOR_BLOCK_KEYWORDS = (
    "사업자",
    "대표",
    "주소",
    "전화",
    "계산대",
    "판매일",
    "화번호",
    "자:",
    "소:",
)
STORE_HINT_TOKENS = (
    "마트",
    "마켓",
    "슈퍼",
    "편의점",
    "스토어",
    "카페",
    "커피",
    "베이커리",
    "정육",
    "약국",
    "gs25",
    "cu",
    "세븐일레븐",
    "7-eleven",
    "emart",
    "이마트",
    "롯데마트",
    "홈플러스",
    "re-mart",
)
CANONICAL_VENDOR_ALIASES = {
    "gs25": "GS25",
    "cu": "CU",
    "세븐일레븐": "세븐일레븐",
    "7-eleven": "7-ELEVEN",
    "7eleven": "7-ELEVEN",
    "seveneleven": "7-ELEVEN",
    "emart": "emart",
    "이마트": "이마트",
    "롯데마트": "롯데마트",
    "홈플러스": "홈플러스",
    "homeplus": "홈플러스",
    "re-mart": "re-MART",
}
BRAND_TOKENS = ("서울우유", "비비고", "CJ", "농심", "오뚜기", "매일", "빙그레")
OCR_CANONICAL_ALIASES = {
    "깨잎": "깻잎",
    "했반": "햇반",
    "바널라": "바닐라",
    "속이면한": "속이편한",
    "누룸지": "누룽지",
    "누릉지": "누룽지",
    "누륨지": "누룽지",
    "딸기피지": "딸기피치",
    "코볼": "초코볼",
    "크라우참쌀서과": "크라운참쌀선과",
    "해태구문감자": "해태구운감자",
}
ITEM_RULES = (
    (re.compile(r"우유|밀크"), "우유", "dairy"),
    (re.compile(r"만두"), "만두", "frozen"),
    (re.compile(r"오이"), "오이", "vegetable"),
    (re.compile(r"두부"), "두부", "tofu_bean"),
)
CATEGORY_STORAGE = {
    "vegetable": "room",
    "fruit": "room",
    "dairy": "refrigerated",
    "meat": "refrigerated",
    "seafood": "refrigerated",
    "egg": "refrigerated",
    "tofu_bean": "refrigerated",
    "sauce": "room",
    "beverage": "room",
    "frozen": "frozen",
    "other": "room",
}


@dataclass(frozen=True)
class ReceiptRules:
    footer_keywords: tuple[str, ...]
    payment_keywords: tuple[str, ...]
    date_hint_keywords: tuple[str, ...]
    date_penalty_keywords: tuple[str, ...]
    header_keywords: tuple[str, ...]
    noise_keywords: tuple[str, ...]
    structural_noise_keywords: tuple[str, ...]
    vendor_block_keywords: tuple[str, ...]
    store_hint_tokens: tuple[str, ...]
    canonical_vendor_aliases: dict[str, str]
    brand_tokens: tuple[str, ...]
    ocr_canonical_aliases: dict[str, str]
    item_rules: tuple[tuple[str, str, str], ...]
    non_item_rules: tuple[NonItemCategoryRule, ...] = ()
    product_alias_lookup: dict[str, str] = field(default_factory=dict)
    product_alias_replacements: tuple[tuple[str, str], ...] = ()
    product_to_ingredient: dict[str, str] = field(default_factory=dict)
    compiled_item_rules: tuple[tuple[re.Pattern[str], str, str], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "compiled_item_rules",
            tuple((re.compile(pattern), normalized_name, category) for pattern, normalized_name, category in self.item_rules),
        )


def build_default_receipt_rules() -> ReceiptRules:
    external_rules = None
    try:
        external_rules = load_receipt_rules()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        external_rules = None

    ocr_aliases = dict(OCR_CANONICAL_ALIASES)
    product_alias_lookup: dict[str, str] = {}
    product_alias_replacements: tuple[tuple[str, str], ...] = ()
    non_item_rules: tuple[NonItemCategoryRule, ...] = ()
    product_to_ingredient: dict[str, str] = {}
    if external_rules is not None:
        non_item_rules = external_rules.non_item_rules
        product_alias_lookup = dict(external_rules.product_aliases)
        product_alias_replacements = external_rules.product_alias_replacements
        product_to_ingredient = dict(external_rules.product_to_ingredient)
    return ReceiptRules(
        footer_keywords=FOOTER_KEYWORDS,
        payment_keywords=PAYMENT_KEYWORDS,
        date_hint_keywords=DATE_HINT_KEYWORDS,
        date_penalty_keywords=("사업자", "주소", "대표", "전화", "승인", "전표", "카드"),
        header_keywords=HEADER_KEYWORDS,
        noise_keywords=NOISE_KEYWORDS,
        structural_noise_keywords=STRUCTURAL_NOISE_KEYWORDS,
        vendor_block_keywords=VENDOR_BLOCK_KEYWORDS,
        store_hint_tokens=STORE_HINT_TOKENS,
        canonical_vendor_aliases=CANONICAL_VENDOR_ALIASES,
        brand_tokens=BRAND_TOKENS,
        ocr_canonical_aliases=ocr_aliases,
        item_rules=tuple((pattern.pattern, normalized_name, category) for pattern, normalized_name, category in ITEM_RULES),
        non_item_rules=non_item_rules,
        product_alias_lookup=product_alias_lookup,
        product_alias_replacements=product_alias_replacements,
        product_to_ingredient=product_to_ingredient,
    )


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float
    line_id: int | None = None
    bbox: tuple[tuple[float, float], ...] | None = None
    center: tuple[float, float] | None = None
    page_order: int | None = None

    def __post_init__(self) -> None:
        if self.center is None and self.bbox:
            xs = [point[0] for point in self.bbox]
            ys = [point[1] for point in self.bbox]
            object.__setattr__(self, "center", (sum(xs) / len(xs), sum(ys) / len(ys)))
        if self.page_order is None and self.line_id is not None:
            object.__setattr__(self, "page_order", self.line_id)


@dataclass
class ReceiptItem:
    raw_name: str
    normalized_name: str | None
    category: str
    storage_type: str
    quantity: float | None
    unit: str | None
    amount: float | None
    confidence: float
    match_confidence: float
    parse_pattern: str
    source_line_ids: list[int] = field(default_factory=list)
    needs_review: bool = False
    review_reason: list[str] = field(default_factory=list)


@dataclass
class ReceiptParseResult:
    vendor_name: str | None
    purchased_at: str | None
    items: list[ReceiptItem]
    totals: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0
    review_required: bool = False
    review_reasons: list[str] = field(default_factory=list)
    diagnostics: dict[str, object] = field(default_factory=dict)


class ReceiptParser:
    def __init__(
        self,
        ingredient_lookup: Mapping[str, Mapping[str, str]] | None = None,
        rules: ReceiptRules | None = None,
    ) -> None:
        self.ingredient_lookup = ingredient_lookup or _load_default_ingredient_lookup()
        self.rules = rules or build_default_receipt_rules()

    def parse_lines(self, lines: list[OcrLine]) -> ReceiptParseResult:
        ordered_lines = self._prepare_lines(lines)
        vendor_name = self._extract_vendor_name(ordered_lines)
        purchased_at = self._extract_purchased_at(ordered_lines)
        totals = self._extract_totals(ordered_lines)
        sections, section_confidence = self._classify_sections(ordered_lines, vendor_name, purchased_at)

        items, consumed_line_ids = self._parse_items(ordered_lines, sections, purchased_at)
        items = self._filter_parsed_items(items)
        items = self._prune_summary_like_items(items, lines=ordered_lines, vendor_name=vendor_name, totals=totals)
        consumed_line_ids = {
            line_id
            for item in items
            for line_id in item.source_line_ids
            if isinstance(line_id, int)
        }

        review_reasons = self._collect_global_review_reasons(
            items=items,
            purchased_at=purchased_at,
            totals=totals,
        )
        review_required = bool(review_reasons) or any(item.needs_review for item in items)
        unresolved_groups = sum(1 for item in items if item.needs_review)
        confidence = self._compute_overall_confidence(items, section_confidence)

        diagnostics = {
            "section_confidence": section_confidence,
            "qwen_used": False,
            "unresolved_groups": unresolved_groups,
            "section_map": {str(line_id): section for line_id, section in sections.items()},
            "consumed_line_ids": sorted(consumed_line_ids),
        }

        return ReceiptParseResult(
            vendor_name=vendor_name,
            purchased_at=purchased_at,
            items=items,
            totals=totals,
            confidence=confidence,
            review_required=review_required,
            review_reasons=review_reasons,
            diagnostics=diagnostics,
        )

    def _prepare_lines(self, lines: list[OcrLine]) -> list[OcrLine]:
        resolved_lines = []
        for index, line in enumerate(lines):
            updated = line
            if updated.line_id is None:
                updated = replace(updated, line_id=index)
            if updated.page_order is None:
                updated = replace(updated, page_order=index)
            resolved_lines.append(updated)
        return sorted(resolved_lines, key=self._line_sort_key)

    def _line_sort_key(self, line: OcrLine) -> tuple[float, float, int]:
        if line.center is not None:
            return (round(line.center[1], 3), round(line.center[0], 3), line.page_order or 0)
        return (float(line.page_order or 0), 0.0, line.page_order or 0)

    def _extract_vendor_name(self, lines: list[OcrLine]) -> str | None:
        for line in lines:
            text = line.text.strip()
            if not text:
                continue
            normalized_vendor = self._normalize_vendor_candidate(text)
            if normalized_vendor is not None:
                return normalized_vendor
            if self._looks_like_date(text) or self._looks_like_footer(text) or self._looks_like_header(text):
                continue
            if self._looks_like_numeric_fragment(text) or self._looks_like_noise(text) or self._looks_like_barcode(text):
                continue
            if _contains_any(text, self.rules.vendor_block_keywords):
                continue
            if text.startswith("*") and self._looks_like_item_candidate(text):
                continue
            if self._looks_like_vendor_candidate(text):
                return normalized_vendor or text
            if self._looks_like_probable_item_row(text):
                break
            if self._looks_like_item_candidate(text) and not self._looks_like_marketing_slogan(text):
                break
            if self._looks_like_plausible_vendor_fallback(text):
                return normalized_vendor or text
        return None

    def _looks_like_vendor_candidate(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text).lower()
        if _contains_any(normalized, self.rules.store_hint_tokens):
            return True
        return bool(re.fullmatch(r"(?:[a-z]{3,10}|[a-z]{2,5}\d{1,4})", normalized))

    def _looks_like_plausible_vendor_fallback(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if len(normalized) < 2:
            return False
        if self._looks_like_marketing_slogan(text):
            return False
        if any(char in normalized for char in "[](){}"):
            return False
        if any(char in normalized for char in ":;/\\"):
            return False
        digit_count = sum(char.isdigit() for char in normalized)
        punct_count = sum(not char.isalnum() for char in normalized)
        hangul_count = sum("가" <= char <= "힣" for char in normalized)
        alpha_count = sum(char.isalpha() for char in normalized)
        if hangul_count < 2:
            return False
        if digit_count > max(3, len(normalized) // 4):
            return False
        return punct_count <= 2

    def _looks_like_marketing_slogan(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return any(token in normalized for token in ("세계1등", "1등", "플랫폼", "일상", "lifestyle", "재미있는"))

    def _extract_purchased_at(self, lines: list[OcrLine]) -> str | None:
        best_candidate: tuple[int, int, str] | None = None
        for index, line in enumerate(lines):
            text = line.text.strip()
            if not text:
                continue
            for pattern in DATE_PATTERNS:
                for match in pattern.finditer(text):
                    candidate = self._format_valid_date_match(match)
                    if candidate is None:
                        continue
                    score = self._date_candidate_score(text)
                    candidate_rank = (score, -index, candidate)
                    if best_candidate is None or candidate_rank > best_candidate:
                        best_candidate = candidate_rank
        return best_candidate[2] if best_candidate else None

    def _classify_sections(
        self,
        lines: list[OcrLine],
        vendor_name: str | None,
        purchased_at: str | None,
    ) -> tuple[dict[int, str], float]:
        item_header_indices = [
            index
            for index, line in enumerate(lines)
            if self._looks_like_item_header(line.text)
        ]
        item_block_start = (
            item_header_indices[0] + 1
            if item_header_indices
            else self._infer_item_block_start(lines)
        )
        first_total_index = next(
            (
                index
                for index, line in enumerate(lines)
                if index >= item_block_start and self._looks_like_footer(line.text)
            ),
            len(lines),
        )
        sections: dict[int, str] = {}
        item_candidates = 0

        for index, line in enumerate(lines):
            text = line.text.strip()
            line_id = line.line_id or index
            normalized = re.sub(r"\s+", "", text)
            if not text:
                sections[line_id] = "ignored"
            elif DASH_PATTERN.match(normalized):
                sections[line_id] = "ignored"
            elif index >= item_block_start and self._looks_like_footer(text):
                sections[line_id] = "payment" if _contains_any(normalized, self.rules.payment_keywords) else "totals"
            elif self._looks_like_noise(text):
                sections[line_id] = "ignored"
            elif self._looks_like_header(text):
                sections[line_id] = "header"
            elif vendor_name and text == vendor_name:
                sections[line_id] = "header"
            elif purchased_at and purchased_at in self._normalize_date_text(text):
                sections[line_id] = "header"
            elif self._looks_like_date(text):
                sections[line_id] = "header"
            elif index < item_block_start:
                sections[line_id] = "header"
            elif (
                index < first_total_index
                and line.center is not None
                and not self._looks_like_noise(text)
                and not self._looks_like_footer(text)
                and not self._looks_like_date(text)
            ):
                sections[line_id] = "items"
                item_candidates += 1
            elif index < first_total_index and self._looks_like_item_candidate(text):
                sections[line_id] = "items"
                item_candidates += 1
            elif index < first_total_index:
                sections[line_id] = "header"
            else:
                sections[line_id] = "ignored"

        section_confidence = 0.4
        if vendor_name:
            section_confidence += 0.15
        if purchased_at:
            section_confidence += 0.15
        if first_total_index < len(lines):
            section_confidence += 0.15
        if item_candidates:
            section_confidence += 0.15
        return sections, round(min(section_confidence, 0.99), 4)

    def _parse_items(
        self,
        lines: list[OcrLine],
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[list[ReceiptItem], set[int]]:
        items: list[ReceiptItem] = []
        consumed_line_ids: set[int] = set()
        item_window_start, item_window_end = self._detect_item_window(lines)

        if any(line.bbox for line in lines):
            bbox_items, bbox_consumed = self._parse_bbox_row_items(
                lines,
                sections,
                purchased_at,
                item_window_start,
                item_window_end,
            )
            items.extend(bbox_items)
            consumed_line_ids.update(bbox_consumed)

        index = 0
        while index < len(lines):
            line = lines[index]
            line_id = line.line_id or index
            text = line.text.strip()
            if line_id in consumed_line_ids:
                index += 1
                continue
            if index < item_window_start or index >= item_window_end:
                index += 1
                continue

            if text:
                two_line_item = self._parse_two_line_barcode_item(lines, index, sections, purchased_at)
                if two_line_item is not None:
                    item, consumed_count = two_line_item
                    items.append(item)
                    consumed_line_ids.update(item.source_line_ids)
                    index += consumed_count
                    continue

            if sections.get(line_id) != "items":
                if not self._looks_like_item_like_row(text):
                    index += 1
                    continue
            if not text or self._looks_like_noise(text):
                index += 1
                continue

            pos_item = self._parse_pos_single_line_item(line, purchased_at)
            if pos_item is not None:
                items.append(pos_item)
                consumed_line_ids.update(pos_item.source_line_ids)
                index += 1
                continue

            numeric_detail_item = self._parse_name_then_numeric_detail_item(lines, index, sections, purchased_at)
            if numeric_detail_item is not None:
                item, consumed_count = numeric_detail_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            name_price_stack_item = self._parse_name_price_then_qty_amount_item(lines, index, sections, purchased_at)
            if name_price_stack_item is not None:
                item, consumed_count = name_price_stack_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            name_qty_amount_item = self._parse_name_qty_then_amount_item(lines, index, sections, purchased_at)
            if name_qty_amount_item is not None:
                item, consumed_count = name_qty_amount_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            columnar_item = self._parse_columnar_item(lines, index, sections, purchased_at)
            if columnar_item is not None:
                item, consumed_count = columnar_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            split_gift_item = self._parse_split_gift_item(lines, index, sections, purchased_at)
            if split_gift_item is not None:
                item, consumed_count = split_gift_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            single_line_item = self._build_single_line_item(line, purchased_at)
            if self._should_skip_single_line_candidate(lines, index, single_line_item):
                index += 1
                continue
            if single_line_item is not None:
                items.append(single_line_item)
                consumed_line_ids.update(single_line_item.source_line_ids)
            index += 1

        return items, consumed_line_ids

    def _filter_parsed_items(self, items: list[ReceiptItem]) -> list[ReceiptItem]:
        filtered: list[ReceiptItem] = []
        excluded_categories = {"discount", "packaging", "metadata", "non_food"}
        for item in items:
            candidates = [item.raw_name]
            if item.normalized_name:
                candidates.append(item.normalized_name)
            should_exclude = False
            for candidate in candidates:
                if not candidate:
                    continue
                if not self._matches_non_item_category(candidate, excluded_categories):
                    continue
                if self._matches_non_item_category(candidate, {"packaging"}) and self._looks_like_food_packaging_name(candidate):
                    continue
                should_exclude = True
                break
            if should_exclude:
                continue
            if item.normalized_name is None and self._looks_like_summary_fragment_name(item.raw_name):
                continue
            if item.normalized_name is None and self._looks_like_domain_noise_name(item.raw_name):
                continue
            if item.normalized_name is None and self._looks_like_fragmented_token_noise(item.raw_name):
                continue
            if (
                item.parse_pattern == "single_line"
                and item.amount is None
                and item.unit in {"g", "kg", "ml", "l", "L"}
            ):
                pack_match = re.search(r"(\d+)\s*(g|kg|ml|l|L)\b", item.raw_name)
                if pack_match and item.quantity is not None and abs(float(pack_match.group(1)) - float(item.quantity)) < 0.001:
                    continue
            compact_raw_name = re.sub(r"\s+", "", item.raw_name or "")
            if (
                item.normalized_name is None
                and (item.match_confidence < LOW_CONFIDENCE_THRESHOLD or item.confidence < LOW_CONFIDENCE_THRESHOLD)
                and 1 <= len(compact_raw_name) <= 3
                and all("가" <= char <= "힣" for char in compact_raw_name)
                and (item.amount is None or item.quantity is None or item.parse_pattern == "single_line")
            ):
                continue
            filtered.append(item)
        return filtered

    def _prune_summary_like_items(
        self,
        items: list[ReceiptItem],
        *,
        lines: list[OcrLine],
        vendor_name: str | None,
        totals: dict[str, float],
    ) -> list[ReceiptItem]:
        filtered: list[ReceiptItem] = []
        total_values = {float(value) for value in totals.values()}
        line_index_by_id = {
            (line.line_id if line.line_id is not None else index): index
            for index, line in enumerate(lines)
        }
        for item in items:
            compact_name = re.sub(r"\s+", "", item.raw_name or "")
            if vendor_name and compact_name == re.sub(r"\s+", "", vendor_name):
                continue
            if (
                item.normalized_name is None
                and item.amount is not None
                and float(item.amount) in total_values
                and item.parse_pattern in {
                    "single_line_name_amount",
                    "single_line",
                    "compact_qty_amount",
                    "compact_unit_price_qty_amount",
                }
            ):
                compact_name = re.sub(r"\s+", "", item.raw_name or "")
                if self._looks_like_footer(item.raw_name) or self._looks_like_summary_fragment_name(item.raw_name):
                    continue
                if len(compact_name) <= 4:
                    continue
                last_source_line_id = item.source_line_ids[-1] if item.source_line_ids else None
                source_index = line_index_by_id.get(last_source_line_id)
                if source_index is not None:
                    hangul_only = re.sub(r"[^가-힣]", "", item.raw_name or "")
                    has_digit = bool(re.search(r"\d", item.raw_name or ""))
                    nearby_total_line = any(
                        self._classify_total_key(
                            re.sub(r"\s+", "", self._normalize_spaced_numeric_text(lines[neighbor_index].text.strip()))
                        )
                        is not None
                        for neighbor_index in range(source_index + 1, min(len(lines), source_index + 3))
                    )
                    if nearby_total_line and not has_digit and 1 <= len(hangul_only) <= 6:
                        continue
            if item.normalized_name is None and item.parse_pattern in {"single_line_name_amount", "single_line"}:
                last_source_line_id = item.source_line_ids[-1] if item.source_line_ids else None
                source_index = line_index_by_id.get(last_source_line_id)
                if source_index is not None and source_index + 1 < len(lines):
                    if self._looks_like_footer(lines[source_index + 1].text):
                        continue
            filtered.append(item)
        return filtered

    def _detect_item_window(self, lines: list[OcrLine]) -> tuple[int, int]:
        header_indices = [
            index
            for index, line in enumerate(lines)
            if self._looks_like_item_header(line.text)
        ]
        if header_indices:
            start = header_indices[0] + 1
        else:
            start = self._infer_item_block_start(lines)

        end = len(lines)
        for index in range(start, len(lines)):
            if self._looks_like_footer(lines[index].text):
                end = index
                break
        return start, end

    def _infer_item_block_start(self, lines: list[OcrLine]) -> int:
        for start in range(len(lines)):
            window = lines[start : min(start + 6, len(lines))]
            pair_offsets = [
                offset
                for offset in range(len(window) - 1)
                if self._looks_like_name_then_detail_pair(window, offset)
            ]
            if len(pair_offsets) >= 2:
                first_pair_index = start + pair_offsets[0]
                return lines[first_pair_index].page_order if lines[first_pair_index].page_order is not None else first_pair_index
            if len(pair_offsets) == 1:
                first_pair_offset = pair_offsets[0]
                trailing_window = window[first_pair_offset + 2 :]
                if any(self._looks_like_item_candidate(candidate.text) for candidate in trailing_window):
                    first_pair_index = start + first_pair_offset
                    return lines[first_pair_index].page_order if lines[first_pair_index].page_order is not None else first_pair_index

            score = 0
            first_structured_index: int | None = None
            for offset, candidate in enumerate(window):
                if self._looks_like_structured_item_row(candidate.text):
                    score += 1
                    if first_structured_index is None:
                        first_structured_index = candidate.page_order if candidate.page_order is not None else start + offset
                elif self._looks_like_noise(candidate.text) or self._looks_like_pure_noise_line(candidate.text):
                    continue
                elif score > 0:
                    break
            if score >= 2:
                return first_structured_index if first_structured_index is not None else start
        return 0

    def _looks_like_name_then_detail_pair(self, lines: list[OcrLine], offset: int) -> bool:
        if offset + 1 >= len(lines):
            return False
        name_line = lines[offset]
        detail_line = lines[offset + 1]
        if not self._looks_like_item_candidate(name_line.text):
            return False
        detail_text = self._normalize_spaced_numeric_text(detail_line.text.strip())
        return bool(
            NUMERIC_DETAIL_ROW_PATTERN.match(detail_text)
            or CODE_NUMERIC_DETAIL_ROW_PATTERN.match(detail_text)
            or CODE_PLACEHOLDER_AMOUNT_ROW_PATTERN.match(detail_text)
            or COMPACT_BARCODE_ITEM_PATTERN.match(detail_text)
            or COMPACT_BARCODE_INFERRED_QTY_PATTERN.match(detail_text)
        )

    def _looks_like_item_like_row(self, text: str) -> bool:
        stripped = self._cleanup_noisy_item_name(text.strip())
        if not self._looks_like_item_candidate(stripped):
            return False
        return bool(
            POS_ITEM_PATTERN.match(stripped)
            or NAME_QTY_AMOUNT_PATTERN.match(stripped)
            or NAME_AMOUNT_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_AMOUNT_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN.match(stripped)
            or COMPACT_UNIT_PRICE_QTY_AMOUNT_PATTERN.match(stripped)
            or COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN.match(stripped)
            or COMPACT_GIFT_PATTERN.match(text.strip())
            or NAME_GIFT_PATTERN.match(text.strip())
            or re.search(r"[가-힣]{2,}", stripped)
        )

    def _looks_like_structured_item_row(self, text: str) -> bool:
        stripped = self._cleanup_noisy_item_name(text.strip())
        if not self._looks_like_item_candidate(stripped):
            return False
        return bool(
            POS_ITEM_PATTERN.match(stripped)
            or NAME_QTY_AMOUNT_PATTERN.match(stripped)
            or NAME_AMOUNT_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_AMOUNT_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN.match(stripped)
            or COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN.match(stripped)
            or COMPACT_UNIT_PRICE_QTY_AMOUNT_PATTERN.match(stripped)
            or COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN.match(stripped)
            or COMPACT_GIFT_PATTERN.match(text.strip())
            or NAME_GIFT_PATTERN.match(text.strip())
            or COMPACT_BARCODE_ITEM_PATTERN.match(text.strip())
            or COMPACT_BARCODE_INFERRED_QTY_PATTERN.match(text.strip())
        )

    def _looks_like_item_header(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if "합계" in normalized or "총계" in normalized or "결제" in normalized or "받은금액" in normalized:
            return False
        header_hits = sum(1 for keyword in ("상품명", "단가", "수량", "금액") if keyword in normalized)
        return header_hits >= 2 or ("상품명" in normalized and header_hits >= 1)

    def _parse_bbox_row_items(
        self,
        lines: list[OcrLine],
        sections: dict[int, str],
        purchased_at: str | None,
        item_window_start: int,
        item_window_end: int,
    ) -> tuple[list[ReceiptItem], set[int]]:
        row_groups: list[list[OcrLine]] = []
        for index, line in enumerate(lines):
            if index < item_window_start or index >= item_window_end:
                continue
            if line.center is None or sections.get(line.line_id or -1) != "items":
                continue
            if not row_groups:
                row_groups.append([line])
                continue
            current_y = row_groups[-1][0].center[1] if row_groups[-1][0].center else 0.0
            if abs(line.center[1] - current_y) <= ROW_GROUP_TOLERANCE:
                row_groups[-1].append(line)
            else:
                row_groups.append([line])

        items: list[ReceiptItem] = []
        consumed: set[int] = set()
        for group in row_groups:
            sorted_group = sorted(group, key=lambda line: (line.center[0] if line.center else 0.0))
            item = self._build_bbox_group_item(sorted_group, purchased_at)
            if item is None:
                continue
            items.append(item)
            consumed.update(item.source_line_ids)
        return items, consumed

    def _build_bbox_group_item(
        self,
        group: list[OcrLine],
        purchased_at: str | None,
    ) -> ReceiptItem | None:
        name_line = next(
            (
                line
                for line in group
                if self._looks_like_item_candidate(line.text)
                and not self._looks_like_barcode(line.text)
                and not self._looks_like_numeric_fragment(line.text)
            ),
            None,
        )
        amount_line = next((line for line in reversed(group) if self._looks_like_price(line.text)), None)
        quantity_line = next(
            (
                line
                for line in group
                if line is not amount_line and COUNT_PATTERN.match(line.text.strip())
            ),
            None,
        )

        if name_line is None or amount_line is None or quantity_line is None:
            return None

        amount = self._extract_last_price(amount_line.text)
        if amount is None:
            return None

        return self._build_item(
            raw_name=name_line.text.strip(),
            confidence_lines=[name_line, quantity_line, amount_line],
            purchased_at=purchased_at,
            quantity=float(quantity_line.text.strip()),
            unit="개",
            amount=amount,
            parse_pattern="columnar_bbox",
            source_line_ids=[name_line.line_id or 0, quantity_line.line_id or 0, amount_line.line_id or 0],
        )

    def _parse_columnar_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 3 >= len(lines):
            return None

        product_line = lines[index]
        unit_price_line = lines[index + 1]
        quantity_line = lines[index + 2]
        amount_line = lines[index + 3]
        product_line_id = product_line.line_id or index

        if (
            sections.get(product_line_id) != "items"
            or not self._looks_like_item_candidate(product_line.text)
            or not PRICE_PATTERN.match(unit_price_line.text.strip())
            or not COUNT_PATTERN.match(quantity_line.text.strip())
            or not PRICE_PATTERN.match(amount_line.text.strip())
        ):
            return None

        amount = self._extract_last_price(amount_line.text)
        if amount is None:
            return None

        item = self._build_item(
            raw_name=product_line.text.strip(),
            confidence_lines=[product_line, quantity_line, amount_line],
            purchased_at=purchased_at,
            quantity=float(quantity_line.text.strip()),
            unit="개",
            amount=amount,
            parse_pattern="columnar_stack",
            source_line_ids=[
                product_line.line_id or 0,
                quantity_line.line_id or 0,
                amount_line.line_id or 0,
            ],
        )
        return item, 4

    def _parse_two_line_barcode_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 1 >= len(lines):
            return None

        name_line = lines[index]
        compact_line = lines[index + 1]
        compact_line_text = self._normalize_spaced_numeric_text(compact_line.text.strip())
        barcode_detail_match = BARCODE_UNIT_PRICE_QTY_PATTERN.match(compact_line_text)
        compact_match = COMPACT_BARCODE_ITEM_PATTERN.match(compact_line_text)
        inferred_qty_match = COMPACT_BARCODE_INFERRED_QTY_PATTERN.match(compact_line_text)
        cleaned_name = self._cleanup_noisy_item_name(name_line.text.strip())
        compact_name = self._extract_compact_barcode_name(cleaned_name)
        is_gift_row = "증정품" in re.sub(r"\s+", "", name_line.text)
        stripped_barcode_name = compact_name
        if (
            barcode_detail_match is not None
        ):
            unit_price = self._extract_last_price(barcode_detail_match.group("unit_price"))
            quantity = float(barcode_detail_match.group("quantity"))
            amount = None if is_gift_row else self._extract_last_price(name_line.text)
            expected_amount = (unit_price * quantity) if unit_price is not None else None
            if (
                not is_gift_row
                and expected_amount is not None
                and (amount is None or abs(amount - expected_amount) > 1.0)
            ):
                amount = expected_amount
            if amount is None and not is_gift_row:
                amount = unit_price
                if amount is not None:
                    amount = amount * quantity
            quantity = self._coerce_pack_count_quantity(
                raw_name=cleaned_name,
                quantity=quantity,
                unit_price=unit_price,
                amount=amount,
            )
            compact_name = self._strip_known_barcode_suffix(
                text=cleaned_name,
                unit_price=unit_price,
                quantity=quantity,
                amount=amount,
            )
            stripped_barcode_name = compact_name
            if not self._looks_like_item_candidate(stripped_barcode_name):
                stripped_barcode_name = self._extract_compact_barcode_name(compact_name)
            if not self._looks_like_item_candidate(stripped_barcode_name):
                stripped_barcode_name = self._extract_compact_barcode_name(cleaned_name)
            if (amount is not None or is_gift_row) and self._looks_like_item_candidate(stripped_barcode_name):
                consumed_count = 2
                if index + 2 < len(lines) and self._looks_like_pure_noise_line(lines[index + 2].text):
                    consumed_count += 1
                return (
                    self._build_item(
                        raw_name=stripped_barcode_name,
                        confidence_lines=[name_line, compact_line],
                        purchased_at=purchased_at,
                        quantity=quantity,
                        unit="개",
                        amount=amount,
                        parse_pattern="two_line_barcode_gift" if is_gift_row else "two_line_barcode_inferred_amount",
                        source_line_ids=[
                            name_line.line_id or 0,
                            compact_line.line_id or 0,
                        ],
                    ),
                    consumed_count,
                )
        if (
            compact_match is not None
            and self._looks_like_item_candidate(compact_name)
        ):
            quantity = float(compact_match.group("quantity"))
            amount = self._extract_last_price(compact_match.group("amount"))
            quantity = self._coerce_pack_count_quantity(
                raw_name=compact_name,
                quantity=quantity,
                unit_price=amount,
                amount=amount,
            )
            consumed_count = 2
            if index + 2 < len(lines) and self._looks_like_pure_noise_line(lines[index + 2].text):
                consumed_count += 1
            return (
                self._build_item(
                    raw_name=compact_name,
                    confidence_lines=[name_line, compact_line],
                    purchased_at=purchased_at,
                    quantity=quantity,
                    unit="개",
                    amount=amount,
                    parse_pattern="two_line_barcode",
                    source_line_ids=[
                        name_line.line_id or 0,
                        compact_line.line_id or 0,
                    ],
                ),
                consumed_count,
            )
        if (
            inferred_qty_match is not None
            and self._looks_like_item_candidate(compact_name)
        ):
            consumed_count = 2
            if index + 2 < len(lines) and self._looks_like_pure_noise_line(lines[index + 2].text):
                consumed_count += 1
            return (
                self._build_item(
                    raw_name=compact_name,
                    confidence_lines=[name_line, compact_line],
                    purchased_at=purchased_at,
                    quantity=1.0,
                    unit="개",
                    amount=self._extract_last_price(inferred_qty_match.group("amount")),
                    parse_pattern="two_line_barcode_inferred_qty",
                    source_line_ids=[
                        name_line.line_id or 0,
                        compact_line.line_id or 0,
                    ],
                ),
                consumed_count,
            )

        if index + 3 >= len(lines):
            return None

        name_line = lines[index]
        barcode_line = lines[index + 1]
        quantity_line = lines[index + 2]
        amount_line = lines[index + 3]

        if (
            sections.get(name_line.line_id or index) != "items"
            or not self._looks_like_item_candidate(name_line.text)
            or not self._looks_like_barcode(barcode_line.text)
            or not COUNT_PATTERN.match(quantity_line.text.strip())
            or not PRICE_PATTERN.match(amount_line.text.strip())
        ):
            return None

        amount = self._extract_last_price(amount_line.text)
        if amount is None:
            return None
        unit_price = self._extract_last_price(barcode_line.text)
        quantity = float(quantity_line.text.strip())
        quantity = self._coerce_pack_count_quantity(
            raw_name=name_line.text.strip(),
            quantity=quantity,
            unit_price=unit_price,
            amount=amount,
        )

        consumed_count = 4
        if index + 4 < len(lines) and self._looks_like_pure_noise_line(lines[index + 4].text):
            consumed_count += 1

        item = self._build_item(
            raw_name=name_line.text.strip(),
            confidence_lines=[name_line, barcode_line, quantity_line, amount_line],
            purchased_at=purchased_at,
            quantity=quantity,
            unit="개",
            amount=amount,
            parse_pattern="two_line_barcode",
            source_line_ids=[
                name_line.line_id or 0,
                barcode_line.line_id or 0,
                quantity_line.line_id or 0,
                amount_line.line_id or 0,
            ],
        )
        return item, consumed_count

    def _extract_compact_barcode_name(self, text: str) -> str:
        candidate = re.sub(r"\s+증정품$", "", text).strip()
        compact_patterns = [
            COMPACT_UNIT_PRICE_QTY_AMOUNT_PATTERN,
            COMPACT_UNIT_PRICE_QTY_AMOUNT_MIXED_SPACE_PATTERN,
            COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN,
            COMPACT_NAME_QTY_AMOUNT_PATTERN,
            COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN,
            COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN,
            COMPACT_GIFT_PATTERN,
        ]
        for pattern in compact_patterns:
            match = pattern.match(candidate)
            if match is not None:
                return match.group("name").strip()
        return candidate

    def _parse_pos_single_line_item(self, line: OcrLine, purchased_at: str | None) -> ReceiptItem | None:
        text = line.text.strip()
        match = POS_ITEM_PATTERN.match(text)
        parse_pattern = "pos_single_line"
        quantity: float | None
        if not match:
            normalized_text = self._normalize_ocr_noisy_pos_text(text)
            noisy_match = OCR_NOISY_POS_PATTERN.match(normalized_text)
            if noisy_match:
                match = noisy_match
                text = self._cleanup_noisy_item_name(match.group("name").strip())
                parse_pattern = "ocr_noisy_pos_line"
                quantity = float(match.group("quantity"))
            else:
                inferred_match = OCR_NOISY_POS_INFERRED_QTY_PATTERN.match(normalized_text)
                if not inferred_match:
                    return None
                match = inferred_match
                text = self._cleanup_noisy_item_name(match.group("name").strip())
                parse_pattern = "ocr_noisy_pos_line_inferred_qty"
                quantity = 1.0
        else:
            text = match.group("name").strip()
            quantity = float(match.group("quantity"))

        if parse_pattern.startswith("ocr_noisy_pos"):
            text = re.sub(r"^(?:\*?[A-Z0-9]{8,}\s+)?\d{1,2}\s+", "", text).strip()
            cleaned_text = self._cleanup_noisy_item_name(text)
            text = self._lookup_exact_product_alias(cleaned_text) or cleaned_text

        amount = self._extract_last_price(match.group("amount"))
        if amount is None:
            return None

        return self._build_item(
            raw_name=text,
            confidence_lines=[line],
            purchased_at=purchased_at,
            quantity=quantity,
            unit="개",
            amount=amount,
            parse_pattern=parse_pattern,
            source_line_ids=[line.line_id or 0],
        )

    def _parse_name_then_numeric_detail_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 1 >= len(lines):
            return None

        name_line = lines[index]
        detail_line = lines[index + 1]
        if sections.get(name_line.line_id or index) != "items":
            return None

        cleaned_name = self._cleanup_noisy_item_name(name_line.text.strip())
        if not self._looks_like_item_candidate(cleaned_name):
            return None
        preview_normalized_name, _, _ = self._normalize_item_name(cleaned_name)
        if preview_normalized_name is None and name_line.confidence < 0.75:
            return None

        standalone_item = self._build_single_line_item(name_line, purchased_at)
        if (
            standalone_item is not None
            and standalone_item.amount is not None
            and self._strip_embedded_barcode_noise_tail(name_line.text) is not None
        ):
            return standalone_item, 1

        detail_text = self._normalize_spaced_numeric_text(detail_line.text.strip())
        match = NUMERIC_DETAIL_ROW_PATTERN.match(detail_text)
        parse_pattern = "name_then_numeric_detail"
        source_line_ids = [name_line.line_id or 0, detail_line.line_id or 0]
        quantity = None
        if match is None:
            code_match = CODE_NUMERIC_DETAIL_ROW_PATTERN.match(detail_text)
            if code_match is None:
                code_times_match = CODE_TIMES_AMOUNT_ROW_PATTERN.match(detail_text)
                if code_times_match is not None:
                    match = code_times_match
                    parse_pattern = "name_then_code_times_amount"
                    quantity = 1.0
                else:
                    code_placeholder_match = CODE_PLACEHOLDER_AMOUNT_ROW_PATTERN.match(detail_text)
                    if code_placeholder_match is None:
                        return None
                    match = code_placeholder_match
                    parse_pattern = "name_then_code_amount_inferred_qty"
                    quantity = 1.0
            else:
                match = code_match
                parse_pattern = "name_then_code_numeric_detail"
        if match is None:
            return None
        if quantity is None:
            quantity = float(match.group("quantity"))

        amount = self._extract_last_price(match.group("amount"))
        if amount is None:
            return None
        unit_price = self._extract_last_price(match.group("unit_price")) if "unit_price" in match.groupdict() else None
        if parse_pattern == "name_then_code_times_amount" and quantity == 1.0 and unit_price is not None:
            if abs(amount - unit_price) > 1.0:
                amount = unit_price
        quantity = self._coerce_pack_count_quantity(
            raw_name=cleaned_name,
            quantity=quantity,
            unit_price=unit_price,
            amount=amount,
        )

        return (
            self._build_item(
                raw_name=cleaned_name,
                confidence_lines=[name_line, detail_line],
                purchased_at=purchased_at,
                quantity=quantity,
                unit="개",
                amount=amount,
                parse_pattern=parse_pattern,
                source_line_ids=source_line_ids,
            ),
            2,
        )

    def _parse_name_price_then_qty_amount_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 2 >= len(lines):
            return None

        name_price_line = lines[index]
        quantity_line = lines[index + 1]
        amount_line = lines[index + 2]
        if sections.get(name_price_line.line_id or index) != "items":
            return None
        if not COUNT_PATTERN.match(quantity_line.text.strip()):
            return None
        if not PRICE_PATTERN.match(amount_line.text.strip()):
            return None

        cleaned_name = self._cleanup_noisy_item_name(name_price_line.text.strip())
        match = NAME_AMOUNT_PATTERN.match(cleaned_name)
        if match is None:
            return None
        raw_name = match.group("name").strip()
        if not self._looks_like_item_candidate(raw_name):
            return None

        amount = self._extract_last_price(amount_line.text)
        if amount is None:
            return None

        return (
            self._build_item(
                raw_name=raw_name,
                confidence_lines=[name_price_line, quantity_line, amount_line],
                purchased_at=purchased_at,
                quantity=float(quantity_line.text.strip()),
                unit="개",
                amount=amount,
                parse_pattern="name_price_then_qty_amount",
                source_line_ids=[
                    name_price_line.line_id or 0,
                    quantity_line.line_id or 0,
                    amount_line.line_id or 0,
                ],
            ),
            3,
        )

    def _parse_name_qty_then_amount_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 1 >= len(lines):
            return None

        name_qty_line = lines[index]
        amount_line = lines[index + 1]
        if sections.get(name_qty_line.line_id or index) != "items":
            return None
        if not PRICE_PATTERN.match(amount_line.text.strip()):
            return None

        cleaned_name = self._cleanup_noisy_item_name(name_qty_line.text.strip())
        parsed_name_qty = self._match_name_qty_only(cleaned_name)
        if parsed_name_qty is None:
            return None

        raw_name, quantity = parsed_name_qty

        amount = self._extract_last_price(amount_line.text)
        if amount is None:
            return None

        return (
            self._build_item(
                raw_name=raw_name,
                confidence_lines=[name_qty_line, amount_line],
                purchased_at=purchased_at,
                quantity=quantity,
                unit="개",
                amount=amount,
                parse_pattern="name_qty_then_amount",
                source_line_ids=[name_qty_line.line_id or 0, amount_line.line_id or 0],
            ),
            2,
        )

    def _parse_split_gift_item(
        self,
        lines: list[OcrLine],
        index: int,
        sections: dict[int, str],
        purchased_at: str | None,
    ) -> tuple[ReceiptItem, int] | None:
        if index + 1 >= len(lines):
            return None

        name_qty_line = lines[index]
        gift_line = lines[index + 1]
        if sections.get(name_qty_line.line_id or index) != "items":
            return None
        if re.sub(r"\s+", "", gift_line.text) != "증정품":
            return None

        cleaned_name = self._cleanup_noisy_item_name(name_qty_line.text.strip())
        parsed_name_qty = self._match_name_qty_only(cleaned_name)
        if parsed_name_qty is None:
            return None

        raw_name, quantity = parsed_name_qty

        return (
            self._build_item(
                raw_name=raw_name,
                confidence_lines=[name_qty_line, gift_line],
                purchased_at=purchased_at,
                quantity=quantity,
                unit="개",
                amount=None,
                parse_pattern="split_gift",
                source_line_ids=[name_qty_line.line_id or 0, gift_line.line_id or 0],
            ),
            2,
        )

    def _normalize_ocr_noisy_pos_text(self, text: str) -> str:
        normalized = text.strip()
        normalized = re.sub(r"([0-9])[\*\#\$]+", r"\1", normalized)
        normalized = re.sub(r"^(?P<line>\d{1,3})(?=[가-힣A-Za-z(])", r"\g<line> ", normalized)
        normalized = re.sub(r"^\s+", "", normalized)
        return normalized

    def _normalize_spaced_numeric_text(self, text: str) -> str:
        normalized = text.strip()
        normalized = re.sub(r"(?<=\d)([,.])\s+(?=\d)", r"\1", normalized)
        normalized = re.sub(r"(?<=\d)['’`´](?=[,\d])", "", normalized)
        return normalized

    def _cleanup_noisy_item_name(self, text: str) -> str:
        cleaned = text
        while True:
            updated = re.sub(r"^(?:\*\s+|[×•·※]+\s*)", "", cleaned)
            updated = re.sub(r"^\d{6}\s+(?=[×•·※]?\(?[가-힣A-Za-z])", "", updated)
            updated = re.sub(r"^(?:0\d{2}|\d{3})\s+(?=\*?[A-Z0-9]{8,}\b)", "", updated)
            updated = re.sub(r"^\*?[A-Z0-9]{8,}\s*", "", updated)
            updated = re.sub(r"^(?:0\d{2}|\d{3})\s+(?=(?:\d{1,3}[가-힣A-Za-z]|[가-힣A-Za-z]))", "", updated)
            updated = re.sub(r"^(?:0\d{2}|\d{3})(?=[가-힣A-Za-z])", "", updated)
            if updated == cleaned:
                break
            cleaned = updated
        cleaned = re.sub(r"(행사|증정품)", " ", cleaned)
        cleaned = re.sub(r"\s+행상$", "", cleaned)
        cleaned = re.sub(r"\b1[가-힣A-Za-z]{1,3}$", "", cleaned).strip()
        cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"\^+", " ", cleaned)
        cleaned = cleaned.strip()
        cleaned = re.sub(r"^([가-힣A-Za-z]{2,4})\)(?=\1)", "", cleaned)
        cleaned = re.sub(r"^(?!\*)([가-힣A-Za-z]{2,6})\)\s*", r"\1 ", cleaned)
        cleaned = cleaned.replace("m]", "ml").replace("m1", "ml").replace("M]", "ML").replace("M1", "ML")
        cleaned = cleaned.replace("ML", "ml")
        cleaned = re.sub(r"(?i)(\d+)m\b", r"\1ml", cleaned)
        cleaned = re.sub(r"(?i)(\d+ml)(?:\s*\1)+", r"\1", cleaned)
        cleaned = re.sub(r"[\]}]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        cleaned = self._strip_leading_short_marker_prefix(cleaned)
        cleaned = re.sub(r"^([가-힣A-Za-z]{2,4})\s+(?=\1)", "", cleaned)
        for source, target in self.rules.ocr_canonical_aliases.items():
            cleaned = self._safe_alias_replace(cleaned, source, target)
        return cleaned

    def _strip_leading_short_marker_prefix(self, text: str) -> str:
        candidate = text.strip()
        if not candidate or candidate.startswith("*"):
            return candidate
        stripped = re.sub(r"^\(?[가-힣A-Za-z]{1,4}\)\s*", "", candidate).strip()
        if (
            stripped
            and stripped != candidate
            and any("가" <= char <= "힣" for char in stripped)
            and len(re.sub(r"[^가-힣A-Za-z0-9]", "", stripped)) >= 2
        ):
            return stripped
        return candidate

    def _strip_embedded_barcode_noise_tail(self, text: str) -> str | None:
        candidate = text.strip()
        match = re.match(
            r"^(?P<name>.+?)\s+\*?[A-Z0-9]{8,}(?:\s+[\dA-Z,.\-EIl]+){1,4}\s*$",
            candidate,
        )
        if match is None:
            return None
        stripped = self._cleanup_noisy_item_name(match.group("name").strip())
        if stripped and self._looks_like_item_candidate(stripped):
            return stripped
        return None

    def _extract_tail_unit_price_match(self, prefix: str) -> re.Match[str] | None:
        return re.search(r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d{2,5})\s*$", prefix)

    def _strip_trailing_price_token(self, text: str, price: float | None) -> str | None:
        if price is None:
            return None
        variants = [f"{int(price):,}", str(int(price))]
        for variant in variants:
            if text.endswith(variant):
                candidate = self._cleanup_noisy_item_name(text[: -len(variant)].rstrip())
                if candidate and self._looks_like_item_candidate(candidate):
                    return candidate
        return None

    def _strip_trailing_barcode_token(self, text: str) -> str | None:
        candidate = text.strip()
        match = re.match(r"^(?P<name>.+?)\s+\*?\d{8,}\s*$", candidate)
        if match is None:
            return None
        stripped = self._cleanup_noisy_item_name(match.group("name").strip())
        if stripped and self._looks_like_item_candidate(stripped):
            return stripped
        return None

    def _strip_trailing_orphan_digit(self, text: str) -> str | None:
        candidate = text.strip()
        if not candidate.endswith("1"):
            return None
        if len(re.findall(r"\d", candidate)) != 1:
            return None
        shortened = self._cleanup_noisy_item_name(candidate[:-1].rstrip())
        if shortened and self._looks_like_item_candidate(shortened):
            return shortened
        return None

    def _parse_tail_encoded_single_line_item(
        self,
        *,
        line: OcrLine,
        purchased_at: str | None,
    ) -> ReceiptItem | None:
        raw_text = line.text.strip()
        compact = re.sub(r"\s+", "", raw_text)
        is_gift = compact.endswith("증정품")
        working = re.sub(r"\s*증정품\s*$", "", raw_text).rstrip() if is_gift else raw_text

        quantity_match: re.Match[str] | None
        amount_text: str | None = None
        if is_gift:
            quantity_match = re.search(r"(?P<quantity>\d)\s*$", working)
            if quantity_match is None:
                return None
            prefix = working[: quantity_match.start("quantity")].rstrip()
            price_suffix_match = re.search(r"(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d{3,5})\s*$", prefix)
            stripped_name = None
            if price_suffix_match is not None:
                candidate = self._cleanup_noisy_item_name(prefix[: price_suffix_match.start()].rstrip())
                if self._looks_like_item_candidate(candidate):
                    stripped_name = candidate
            raw_name = stripped_name or self._cleanup_noisy_item_name(prefix)
            if not self._looks_like_item_candidate(raw_name):
                unit_price_match = self._extract_tail_unit_price_match(prefix)
                if unit_price_match is None:
                    return None
                raw_name = self._cleanup_noisy_item_name(prefix[: unit_price_match.start()].rstrip())
            if not self._looks_like_item_candidate(raw_name):
                return None
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=float(quantity_match.group("quantity")),
                unit="개",
                amount=None,
                parse_pattern="compact_gift",
                source_line_ids=[line.line_id or 0],
            )
        else:
            amount_candidates: list[tuple[int, str]] = []
            for start in range(len(working)):
                suffix = working[start:].strip()
                if re.fullmatch(r"\d{1,3}(?:[,.]\d{3})+|\d{3,5}", suffix):
                    amount_candidates.append((start, suffix))

            fallback_item: ReceiptItem | None = None
            for start, amount_text in sorted(amount_candidates, key=lambda value: value[0], reverse=True):
                prefix_with_qty = working[:start].rstrip()
                if not prefix_with_qty or not prefix_with_qty[-1].isdigit():
                    continue
                quantity = float(prefix_with_qty[-1])
                if quantity <= 0:
                    continue
                prefix = prefix_with_qty[:-1].rstrip()
                amount = self._extract_last_price(amount_text)
                if amount is None:
                    continue
                unit_price = amount / quantity
                raw_name = self._strip_trailing_price_token(prefix, unit_price)
                if raw_name is not None:
                    if (
                        " " in raw_text
                        and raw_name.count(" ") >= 2
                        and quantity == 1.0
                        and amount < 5000
                        and not re.search(r"\d|(?:ml|kg|g|l|L)", raw_name)
                    ):
                        continue
                    return self._build_item(
                        raw_name=raw_name,
                        confidence_lines=[line],
                        purchased_at=purchased_at,
                        quantity=quantity,
                        unit="개",
                        amount=amount,
                        parse_pattern="compact_unit_price_qty_amount",
                        source_line_ids=[line.line_id or 0],
                    )

                candidate_name = self._cleanup_noisy_item_name(prefix)
                if not self._looks_like_item_candidate(candidate_name):
                    continue
                if (
                    " " in raw_text
                    and candidate_name.count(" ") >= 2
                    and quantity == 1.0
                    and amount < 5000
                    and not re.search(r"\d|(?:ml|kg|g|l|L)", candidate_name)
                ):
                    continue

                if fallback_item is None:
                    fallback_item = self._build_item(
                        raw_name=candidate_name,
                        confidence_lines=[line],
                        purchased_at=purchased_at,
                        quantity=quantity,
                        unit="개",
                        amount=amount,
                        parse_pattern="compact_unit_price_qty_amount",
                        source_line_ids=[line.line_id or 0],
                    )

            if fallback_item is not None:
                return fallback_item

            return None

    def _strip_known_barcode_suffix(
        self,
        *,
        text: str,
        unit_price: float | None,
        quantity: float | None,
        amount: float | None,
    ) -> str:
        candidate = text.strip()
        if unit_price is None or quantity is None:
            return candidate

        qty_text = str(int(quantity)) if float(quantity).is_integer() else str(quantity)
        unit_price_variants = {f"{int(unit_price):,}", str(int(unit_price))}
        amount_variants = {""}
        if amount is not None:
            amount_variants |= {f"{int(amount):,}", str(int(amount))}

        for unit_price_text in sorted(unit_price_variants, key=len, reverse=True):
            for amount_text in sorted(amount_variants, key=len, reverse=True):
                suffix = (
                    rf"\s*(?:{re.escape(qty_text)}\s*)?{re.escape(unit_price_text)}"
                    rf"\s*(?:[\)\]\|Il!]+\s*)?{re.escape(qty_text)}"
                )
                if amount_text:
                    suffix += rf"\s*{re.escape(amount_text)}"
                match = re.match(rf"^(?P<name>.+?){suffix}\s*$", candidate)
                if match is None:
                    continue
                stripped = self._cleanup_noisy_item_name(match.group("name").strip())
                if self._looks_like_item_candidate(stripped):
                    return stripped
        return candidate

    def _should_skip_single_line_candidate(
        self,
        lines: list[OcrLine],
        index: int,
        item: ReceiptItem | None,
    ) -> bool:
        if item is None:
            return False

        raw_text = lines[index].text.strip()
        preview_normalized_name, _, _ = self._normalize_item_name(item.raw_name)
        if preview_normalized_name is None and lines[index].confidence < 0.75:
            return True

        if item.parse_pattern != "single_line_name_amount":
            return False
        if not re.match(r"^\d{1,3}\s+", raw_text):
            return False
        if index + 1 >= len(lines):
            return False
        next_text = lines[index + 1].text.strip()
        return bool(INCOMPLETE_CODE_DETAIL_ROW_PATTERN.match(next_text))

    def _build_single_line_item(self, line: OcrLine, purchased_at: str | None) -> ReceiptItem | None:
        gift_candidate = line.text.strip()
        gift_candidate = re.sub(r"^\*?\d{8,}\s*", "", gift_candidate)
        gift_candidate = re.sub(r"^\d{1,3}\s*", "", gift_candidate)
        gift_candidate = re.sub(r"^\d{1,3}(?=[가-힣A-Za-z])", "", gift_candidate)
        cleaned_name = self._cleanup_noisy_item_name(line.text.strip())
        normalized_line = self._normalize_spaced_numeric_text(line.text.strip())

        lowres_match = LOWRES_CODED_ITEM_PATTERN.match(normalized_line)
        if lowres_match is not None:
            raw_name = self._cleanup_noisy_item_name(lowres_match.group("name").strip())
            raw_name = self._lookup_exact_product_alias(raw_name) or raw_name
            unit_price = self._extract_last_price(lowres_match.group("unit_price"))
            amount = self._extract_last_price(lowres_match.group("amount"))
            if amount is not None:
                quantity = 1.0
                if unit_price is not None and unit_price > 0:
                    ratio = amount / unit_price
                    rounded_ratio = round(ratio)
                    if 1 <= rounded_ratio <= 9 and abs(ratio - rounded_ratio) <= 0.05:
                        quantity = float(rounded_ratio)
                return self._build_item(
                    raw_name=raw_name,
                    confidence_lines=[line],
                    purchased_at=purchased_at,
                    quantity=quantity,
                    unit="개",
                    amount=amount,
                    parse_pattern="lowres_coded_single_line",
                    source_line_ids=[line.line_id or 0],
                )

        if "증정품" in re.sub(r"\s+", "", line.text) and NAME_GIFT_PATTERN.match(gift_candidate) is None:
            tail_encoded_item = self._parse_tail_encoded_single_line_item(
                line=line,
                purchased_at=purchased_at,
            )
            if tail_encoded_item is not None and tail_encoded_item.amount is None:
                return tail_encoded_item

        compact_item = self._parse_compact_merged_single_line_item(
            line=line,
            gift_candidate=gift_candidate,
            cleaned_name=cleaned_name,
            purchased_at=purchased_at,
        )
        if compact_item is not None:
            return compact_item

        if not self._looks_like_item_candidate(cleaned_name):
            return None

        gift_match = NAME_GIFT_PATTERN.match(gift_candidate)
        if gift_match is not None:
            raw_name = self._cleanup_noisy_item_name(gift_match.group("name").strip())
            trailing_price_match = re.search(r"(?P<price>\d{1,3}(?:[,.]\d{3})+|\d{3,5})\s*$", raw_name)
            if trailing_price_match is not None:
                candidate_name = self._cleanup_noisy_item_name(raw_name[: trailing_price_match.start()].rstrip())
                if self._looks_like_item_candidate(candidate_name):
                    raw_name = candidate_name
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=float(gift_match.group("quantity")),
                unit="개",
                amount=None,
                parse_pattern="single_line_gift",
                source_line_ids=[line.line_id or 0],
            )

        qty_amount_match = NAME_QTY_AMOUNT_PATTERN.match(cleaned_name)
        name_barcode_amount_match = NAME_BARCODE_AMOUNT_PATTERN.match(cleaned_name)
        times_qty_amount_match = NAME_UNIT_PRICE_TIMES_QTY_AMOUNT_PATTERN.match(cleaned_name)
        if times_qty_amount_match is not None:
            amount = self._extract_last_price(times_qty_amount_match.group("amount"))
            if amount is None:
                return None
            raw_name = self._cleanup_noisy_item_name(times_qty_amount_match.group("name").strip())
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=float(times_qty_amount_match.group("quantity")),
                unit="개",
                amount=amount,
                parse_pattern="single_line_unit_price_times_qty_amount",
                source_line_ids=[line.line_id or 0],
            )

        if name_barcode_amount_match is not None:
            amount = self._extract_last_price(name_barcode_amount_match.group("amount"))
            if amount is None:
                return None
            raw_name = self._cleanup_noisy_item_name(name_barcode_amount_match.group("name").strip())
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=1.0,
                unit="개",
                amount=amount,
                parse_pattern="single_line_name_barcode_amount",
                source_line_ids=[line.line_id or 0],
            )

        if qty_amount_match is not None:
            amount = self._extract_last_price(qty_amount_match.group("amount"))
            if amount is None:
                return None
            quantity = float(qty_amount_match.group("quantity"))
            raw_name = qty_amount_match.group("name").strip()
            embedded_barcode_name = self._strip_embedded_barcode_noise_tail(raw_name)
            if embedded_barcode_name is not None:
                raw_name = embedded_barcode_name
            stripped_name = self._strip_trailing_price_token(raw_name, amount / quantity if quantity > 0 else None)
            if stripped_name is not None:
                raw_name = stripped_name
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=quantity,
                unit="개",
                amount=amount,
                parse_pattern="single_line_name_qty_amount",
                source_line_ids=[line.line_id or 0],
            )

        amount_match = NAME_AMOUNT_PATTERN.match(cleaned_name)
        if amount_match is not None:
            amount_token = amount_match.group("amount")
            compact_amount_token = amount_token.replace(",", "").replace(".", "")
            if "," not in amount_token and len(compact_amount_token) < 3:
                amount_match = None
        if amount_match is not None:
            amount = self._extract_last_price(amount_match.group("amount"))
            if amount is None:
                return None
            raw_name = amount_match.group("name").strip()
            stripped_name = self._strip_trailing_price_token(raw_name, amount)
            if stripped_name is not None:
                raw_name = stripped_name
            stripped_barcode_name = self._strip_trailing_barcode_token(raw_name)
            if stripped_barcode_name is not None:
                raw_name = stripped_barcode_name
            orphan_digit_name = self._strip_trailing_orphan_digit(raw_name)
            if orphan_digit_name is not None:
                raw_name = orphan_digit_name
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=1.0,
                unit="개",
                amount=amount,
                parse_pattern="single_line_name_amount",
                source_line_ids=[line.line_id or 0],
            )

        tail_encoded_item = self._parse_tail_encoded_single_line_item(
            line=line,
            purchased_at=purchased_at,
        )
        if tail_encoded_item is not None:
            return tail_encoded_item

        quantity, unit = self._extract_quantity(line.text)
        amount = self._extract_last_price(line.text)
        if quantity is not None and unit is not None:
            numeric_tokens_in_name = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", cleaned_name)
            if len(numeric_tokens_in_name) <= 1:
                amount = None
        return self._build_item(
            raw_name=cleaned_name,
            confidence_lines=[line],
            purchased_at=purchased_at,
            quantity=quantity,
            unit=unit,
            amount=amount,
            parse_pattern="single_line",
            source_line_ids=[line.line_id or 0],
        )

    def _match_name_qty_only(self, cleaned_name: str) -> tuple[str, float] | None:
        amount_match = NAME_AMOUNT_PATTERN.match(cleaned_name)
        if NAME_QTY_AMOUNT_PATTERN.match(cleaned_name):
            return None
        if amount_match is not None:
            amount_token = amount_match.group("amount")
            compact_amount_token = amount_token.replace(",", "").replace(".", "")
            if "," in amount_token or len(compact_amount_token) >= 3:
                return None
        match = NAME_QTY_ONLY_PATTERN.match(cleaned_name)
        if match is not None:
            raw_name = match.group("name").strip()
            if self._looks_like_item_candidate(raw_name):
                return raw_name, float(match.group("quantity"))

        compact_match = COMPACT_NAME_QTY_ONLY_PATTERN.match(cleaned_name)
        if compact_match is None:
            return None

        raw_name = compact_match.group("name").strip()
        if not self._looks_like_item_candidate(raw_name):
            return None
        return raw_name, float(compact_match.group("quantity"))

    def _parse_compact_merged_single_line_item(
        self,
        *,
        line: OcrLine,
        gift_candidate: str,
        cleaned_name: str,
        purchased_at: str | None,
    ) -> ReceiptItem | None:
        raw_text = line.text.strip()
        if " " in raw_text:
            numeric_tokens = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", cleaned_name)
            if len(numeric_tokens) == 1 and NAME_AMOUNT_PATTERN.match(cleaned_name):
                return None
        compact_name_qty_gift_match = COMPACT_NAME_QTY_GIFT_NO_SPACE_PATTERN.match(gift_candidate)
        if compact_name_qty_gift_match is not None:
            raw_name = self._cleanup_noisy_item_name(compact_name_qty_gift_match.group("name").strip())
            if re.search(r"\d{1,3}(?:[,.]\d{3})$", raw_name):
                raw_name = ""
            if self._looks_like_item_candidate(raw_name):
                return self._build_item(
                    raw_name=raw_name,
                    confidence_lines=[line],
                    purchased_at=purchased_at,
                    quantity=float(compact_name_qty_gift_match.group("quantity")),
                    unit="개",
                    amount=None,
                    parse_pattern="compact_gift",
                    source_line_ids=[line.line_id or 0],
                )
        compact_gift_match = COMPACT_GIFT_PATTERN.match(gift_candidate)
        if compact_gift_match is not None:
            raw_name = self._cleanup_noisy_item_name(compact_gift_match.group("name").strip())
            if self._looks_like_item_candidate(raw_name):
                return self._build_item(
                    raw_name=raw_name,
                    confidence_lines=[line],
                    purchased_at=purchased_at,
                    quantity=float(compact_gift_match.group("quantity")),
                    unit="개",
                    amount=None,
                    parse_pattern="compact_gift",
                    source_line_ids=[line.line_id or 0],
                )

        ordered_compact_patterns = []
        if " " in raw_text:
            ordered_compact_patterns.extend(
                [
                    (COMPACT_UNIT_PRICE_QTY_AMOUNT_PATTERN, "compact_unit_price_qty_amount"),
                    (COMPACT_UNIT_PRICE_QTY_AMOUNT_MIXED_SPACE_PATTERN, "compact_unit_price_qty_amount"),
                    (COMPACT_NAME_QTY_LARGE_AMOUNT_PATTERN, "compact_qty_amount"),
                    (COMPACT_NAME_QTY_AMOUNT_PATTERN, "compact_qty_amount"),
                    (COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN, "compact_unit_price_qty_amount"),
                    (COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN, "compact_qty_amount"),
                ]
            )
        else:
            ordered_compact_patterns.extend(
                [
                    (COMPACT_UNIT_PRICE_QTY_AMOUNT_NO_SPACE_PATTERN, "compact_unit_price_qty_amount"),
                    (COMPACT_UNIT_PRICE_QTY_AMOUNT_MIXED_SPACE_PATTERN, "compact_unit_price_qty_amount"),
                    (COMPACT_NAME_QTY_LARGE_AMOUNT_PATTERN, "compact_qty_amount"),
                    (COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN, "compact_qty_amount"),
                ]
            )
        ordered_compact_patterns.extend(
            [
                (COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN, "compact_qty_amount"),
            ]
        )

        for pattern, parse_pattern in ordered_compact_patterns:
            match = pattern.match(cleaned_name)
            if match is None:
                continue
            raw_name = match.group("name").strip()
            quantity = float(match.group("quantity"))
            amount = self._extract_last_price(match.group("amount"))
            if amount is None:
                continue
            if parse_pattern == "compact_unit_price_qty_amount":
                parsed_unit_price = self._extract_last_price(match.group("unit_price"))
                expected_unit_price = amount / quantity if quantity > 0 else None
                if (
                    parsed_unit_price is not None
                    and expected_unit_price is not None
                    and abs(parsed_unit_price - expected_unit_price) > 1.0
                ):
                    continue
                allow_digitless_name = bool(re.fullmatch(r"[가-힣A-Za-z\s]{2,24}", raw_name))
                require_digit_or_unit = " " not in raw_text and not allow_digitless_name
                if not self._looks_like_plausible_compact_name(
                    raw_name,
                    allow_spaces=True,
                    require_digit_or_unit=require_digit_or_unit,
                ):
                    continue
            elif pattern is COMPACT_NAME_QTY_AMOUNT_NO_SPACE_PATTERN:
                if (
                    " " in raw_text
                    and raw_name.count(" ") >= 2
                    and quantity == 1.0
                    and amount < 5000
                    and not re.search(r"\d|(?:ml|kg|g|l|L)", raw_name)
                ):
                    continue
                if not self._looks_like_plausible_compact_name(raw_name, allow_spaces=False, require_digit_or_unit=False):
                    continue
            elif pattern is COMPACT_NAME_QTY_AMOUNT_PATTERN:
                if re.match(r"^.+\s+\d+\s+\d", raw_text):
                    continue
                if not self._looks_like_plausible_compact_name(raw_name, allow_spaces=True, require_digit_or_unit=False):
                    continue
            elif pattern is COMPACT_NAME_QTY_LARGE_AMOUNT_PATTERN:
                if not self._looks_like_plausible_compact_name(raw_name, allow_spaces=True, require_digit_or_unit=False):
                    continue
            elif pattern is COMPACT_NAME_QTY_PLAIN_AMOUNT_PATTERN:
                if not self._looks_like_plausible_compact_name(raw_name, allow_spaces=False, require_digit_or_unit=False):
                    continue
            else:
                if not self._looks_like_plausible_compact_name(raw_name, allow_spaces=False, require_digit_or_unit=False):
                    continue
            if not self._looks_like_item_candidate(raw_name):
                continue
            expected_unit_price = amount / quantity if quantity > 0 else None
            stripped_name = self._strip_trailing_price_token(raw_name, expected_unit_price)
            if stripped_name is not None:
                raw_name = stripped_name
            return self._build_item(
                raw_name=raw_name,
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=quantity,
                unit="개",
                amount=amount,
                parse_pattern=parse_pattern,
                source_line_ids=[line.line_id or 0],
            )

        return None

    def _looks_like_plausible_compact_name(
        self,
        name: str,
        *,
        allow_spaces: bool,
        require_digit_or_unit: bool,
    ) -> bool:
        if not allow_spaces and " " in name:
            return False
        if re.search(r"[^0-9A-Za-z가-힣\s.*]", name):
            return False
        if require_digit_or_unit and not (
            re.search(r"\d", name) or re.search(r"(?:ml|kg|g|l|L)$", name)
        ):
            return False
        return True

    def _build_item(
        self,
        *,
        raw_name: str,
        confidence_lines: list[OcrLine],
        purchased_at: str | None,
        quantity: float | None,
        unit: str | None,
        amount: float | None,
        parse_pattern: str,
        source_line_ids: list[int],
    ) -> ReceiptItem:
        normalized_name, category, storage_override = self._normalize_item_name(raw_name)
        storage_type = storage_override or CATEGORY_STORAGE.get(category, "room")
        match_confidence = round(mean(line.confidence for line in confidence_lines), 4)
        review_reason: list[str] = []
        if match_confidence < LOW_CONFIDENCE_THRESHOLD:
            review_reason.append("low_confidence")
        if purchased_at is None:
            review_reason.append("missing_purchased_at")
        if normalized_name is None:
            review_reason.append("unknown_item")
        if quantity is None or unit is None:
            review_reason.append("missing_quantity_or_unit")
        structural_review_reasons = [reason for reason in review_reason if reason != "unknown_item"]

        return ReceiptItem(
            raw_name=raw_name,
            normalized_name=normalized_name,
            category=category,
            storage_type=storage_type,
            quantity=quantity,
            unit=unit,
            amount=amount,
            confidence=round(confidence_lines[0].confidence, 2),
            match_confidence=match_confidence,
            parse_pattern=parse_pattern,
            source_line_ids=source_line_ids,
            needs_review=bool(structural_review_reasons),
            review_reason=review_reason,
        )

    def _collect_global_review_reasons(
        self,
        *,
        items: list[ReceiptItem],
        purchased_at: str | None,
        totals: dict[str, float],
    ) -> list[str]:
        reasons: list[str] = []
        if purchased_at is None:
            reasons.append("missing_purchased_at")

        item_sum = sum(item.amount or 0.0 for item in items)
        known_total = totals.get("subtotal")
        if known_total is None and totals.get("payment_amount") is not None and totals.get("tax") is not None:
            known_total = float(totals["payment_amount"]) - float(totals["tax"])
        if known_total is None:
            known_total = totals.get("payment_amount") or totals.get("total")
        if known_total is not None and item_sum > 0 and abs(known_total - item_sum) > 1.0:
            reasons.append("total_mismatch")

        if any(item.needs_review for item in items):
            reasons.append("unresolved_items")

        return reasons

    def _compute_overall_confidence(self, items: list[ReceiptItem], section_confidence: float) -> float:
        scores = [section_confidence]
        scores.extend(item.match_confidence for item in items if item.match_confidence)
        return round(mean(scores), 4) if scores else 0.0

    def _extract_totals(self, lines: list[OcrLine]) -> dict[str, float]:
        totals: dict[str, float] = {}
        for index, line in enumerate(lines):
            text = self._normalize_spaced_numeric_text(line.text.strip())
            normalized = re.sub(r"\s+", "", text)
            total_key = self._classify_total_key(normalized)
            if total_key is None:
                continue

            next_text = (
                self._normalize_spaced_numeric_text(lines[index + 1].text.strip())
                if index + 1 < len(lines)
                else ""
            )
            if total_key == "payment_amount" and not self._looks_like_total_amount_line(text):
                if not (next_text and PRICE_PATTERN.match(next_text)):
                    continue

            amount = self._extract_preferred_total_amount(text, total_key=total_key)
            if amount is None and next_text:
                if PRICE_PATTERN.match(next_text):
                    amount = self._extract_preferred_total_amount(next_text, total_key=total_key)
            if amount is not None:
                if (
                    total_key == "total"
                    and total_key in totals
                    and "payment_amount" in totals
                    and float(amount) < float(totals["payment_amount"])
                ):
                    continue
                if (
                    total_key == "payment_amount"
                    and total_key in totals
                ):
                    if "카드결제" in normalized or "일시불" in normalized:
                        continue
                    total_amount = totals.get("total")
                    existing_amount = float(totals[total_key])
                    if total_amount is not None and abs(existing_amount - float(total_amount)) <= abs(float(amount) - float(total_amount)):
                        continue
                totals[total_key] = amount

        self._infer_vertical_totals_block(lines, totals)
        discount_base_total = self._extract_discount_base_total(lines)
        if discount_base_total is not None:
            current_total = totals.get("total")
            if current_total is None or abs(float(current_total) - discount_base_total) > 1.0:
                totals["total"] = discount_base_total
        discounted_payment_amount = self._extract_discount_adjusted_payment_amount(lines, totals=totals)
        if discounted_payment_amount is not None:
            totals["payment_amount"] = discounted_payment_amount
        if "payment_amount" not in totals and "total" in totals:
            totals["payment_amount"] = totals["total"]
        return totals

    def _infer_vertical_totals_block(self, lines: list[OcrLine], totals: dict[str, float]) -> None:
        total_amount = totals.get("total")
        if total_amount is None:
            return
        amount_rows: list[tuple[int, float]] = []
        total_index: int | None = None
        for index, line in enumerate(lines):
            text = self._normalize_spaced_numeric_text(line.text.strip())
            normalized = re.sub(r"\s+", "", text)
            total_key = self._classify_total_key(normalized)
            amount = self._extract_last_price(text)
            if total_key == "total":
                total_index = index
            if amount is None or amount <= 0:
                continue
            if total_key == "payment_amount":
                continue
            amount_rows.append((index, amount))
        if total_index is None:
            return
        preceding_rows = [(index, amount) for index, amount in amount_rows if index < total_index]
        if len(preceding_rows) < 2:
            return
        trailing_candidates = preceding_rows[-4:]
        for length in range(min(4, len(trailing_candidates)), 1, -1):
            window = trailing_candidates[-length:]
            amounts = [amount for _, amount in window]
            if abs(sum(amounts) - float(total_amount)) > 1.0:
                continue
            tax_candidate = min(amounts)
            if tax_candidate >= float(total_amount) * 0.2:
                continue
            subtotal_candidate = max(amounts)
            if "tax" not in totals:
                totals["tax"] = tax_candidate
            if "subtotal" not in totals:
                totals["subtotal"] = subtotal_candidate
            return

    def _extract_discount_adjusted_payment_amount(self, lines: list[OcrLine], *, totals: dict[str, float]) -> float | None:
        total_amount = totals.get("total")
        for index, line in enumerate(lines):
            text = self._normalize_spaced_numeric_text(line.text.strip())
            normalized = re.sub(r"\s+", "", text)
            is_total_anchor = self._classify_total_key(normalized) == "total" or "할인계" in normalized
            if not is_total_anchor:
                continue
            base_amount = self._extract_preferred_total_amount(text, total_key="total")
            if base_amount is None:
                continue
            if index + 2 >= len(lines):
                continue
            discount_text = self._normalize_spaced_numeric_text(lines[index + 1].text.strip())
            final_text = self._normalize_spaced_numeric_text(lines[index + 2].text.strip())
            discount_amount = self._extract_signed_last_price(discount_text)
            final_amount = self._extract_signed_last_price(final_text)
            if discount_amount is None or final_amount is None:
                continue
            if discount_amount >= 0:
                continue
            final_compact = re.sub(r"\s+", "", final_text)
            if not (
                re.fullmatch(r"-?\d{1,3}(?:[,.]\d{3})+|-?\d+", final_compact)
                or "결제대상금액" in final_compact
                or self._looks_like_date(final_text)
            ):
                continue
            resolved_final_amount = abs(float(final_amount))
            if abs((float(base_amount) + discount_amount) - resolved_final_amount) <= 1.0:
                return resolved_final_amount
        return None

    def _extract_discount_base_total(self, lines: list[OcrLine]) -> float | None:
        for line in lines:
            text = self._normalize_spaced_numeric_text(line.text.strip())
            normalized = re.sub(r"\s+", "", text)
            if "할인계" not in normalized:
                continue
            amount = self._extract_max_price(text)
            if amount is None or amount <= 0:
                continue
            return amount
        return None

    def _classify_total_key(self, normalized_text: str) -> str | None:
        hangul_only = re.sub(r"[^가-힣]", "", normalized_text)
        if normalized_text.startswith("계:") or normalized_text == "계":
            return "total"
        if re.fullmatch(r"계[:：]?(?:\d{1,3}(?:[,.]\d{3})+|\d+)(?:원)?", normalized_text):
            return "total"
        if "승인번호" in normalized_text:
            return None
        if _contains_any(normalized_text, self.rules.payment_keywords):
            return "payment_amount"
        if "부가세" in normalized_text or "세액" in normalized_text or "부가세" in hangul_only or "세액" in hangul_only:
            return "tax"
        if "과세물품가액" in normalized_text or "과세물품" in normalized_text or "공급가액" in normalized_text:
            return "subtotal"
        if "합계" in normalized_text or "총계" in normalized_text:
            return "total"
        return None

    def _extract_quantity(self, text: str) -> tuple[float | None, str | None]:
        match = QUANTITY_PATTERN.search(text)
        if not match:
            return None, None

        quantity = float(match.group("quantity"))
        unit = match.group("unit")
        if unit.lower() == "l":
            unit = "L"
        return quantity, unit

    def _extract_last_price(self, text: str) -> float | None:
        matches = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", text)
        if not matches:
            return None
        candidate = matches[-1].replace(",", "").replace(".", "")
        try:
            return float(candidate)
        except ValueError:
            return None

    def _extract_first_price(self, text: str) -> float | None:
        matches = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", text)
        if not matches:
            return None
        candidate = matches[0].replace(",", "").replace(".", "")
        try:
            return float(candidate)
        except ValueError:
            return None

    def _extract_max_price(self, text: str) -> float | None:
        matches = re.findall(r"\d{1,3}(?:[,.]\d{3})+|\d+", text)
        if not matches:
            return None
        prices: list[float] = []
        for token in matches:
            try:
                prices.append(float(token.replace(",", "").replace(".", "")))
            except ValueError:
                continue
        return max(prices) if prices else None

    def _extract_preferred_total_amount(self, text: str, *, total_key: str) -> float | None:
        signed_matches = re.findall(r"-\d{1,3}(?:[,.]\d{3})+|-\d+|\d{1,3}(?:[,.]\d{3})+|\d+", text)
        if total_key == "total" and any(token.startswith("-") for token in signed_matches):
            for token in signed_matches:
                if token.startswith("-"):
                    continue
                candidate = token.replace(",", "").replace(".", "")
                try:
                    return float(candidate)
                except ValueError:
                    continue
        if total_key == "payment_amount":
            compact = re.sub(r"\s+", "", text)
            if any(keyword in compact for keyword in ("할인총금액", "결제대상금액", "결제금액", "구매금액", "최종결제")):
                first_price = self._extract_first_price(text)
                if first_price is not None:
                    return first_price
        return self._extract_last_price(text)

    def _extract_signed_last_price(self, text: str) -> float | None:
        matches = re.findall(r"-\d{1,3}(?:[,.]\d{3})+|-\d+|\d{1,3}(?:[,.]\d{3})+|\d+", text)
        if not matches:
            return None
        token = matches[-1]
        sign = -1.0 if token.startswith("-") else 1.0
        candidate = token.lstrip("-").replace(",", "").replace(".", "")
        try:
            return sign * float(candidate)
        except ValueError:
            return None

    def _coerce_pack_count_quantity(
        self,
        *,
        raw_name: str,
        quantity: float | None,
        unit_price: float | None,
        amount: float | None,
    ) -> float | None:
        if quantity is None or unit_price is None or amount is None:
            return quantity
        compact_name = re.sub(r"\s+", "", raw_name or "")
        if quantity <= 1.0:
            return quantity
        if not re.search(r"\d+\s*입\b", compact_name):
            return quantity
        if abs(unit_price - amount) > 1.0:
            return quantity
        return 1.0

    def _normalize_item_name(self, text: str) -> tuple[str | None, str, str | None]:
        raw_candidates = [
            str(text or "").strip(),
            self._cleanup_noisy_item_name(str(text or "").strip()),
        ]
        normalized_candidates: list[str] = []
        raw_aliases: list[str] = []
        for candidate in raw_candidates:
            aliased = self._lookup_exact_product_alias(candidate)
            if aliased is not None:
                normalized_candidates.append(aliased)
                raw_aliases.append(aliased)

        candidates = list(dict.fromkeys(normalized_candidates + self._candidate_item_names(text)))
        for candidate in candidates:
            aliased = self._lookup_exact_product_alias(candidate)
            if aliased is not None:
                return aliased, "other", None

        for candidate in candidates:
            for pattern, normalized_name, category in self.rules.compiled_item_rules:
                if pattern.search(candidate):
                    return normalized_name, category, None

        for candidate in candidates:
            dictionary_match = self.ingredient_lookup.get(candidate) or self.ingredient_lookup.get(candidate.replace(" ", ""))
            if dictionary_match:
                normalized_name = dictionary_match.get("standard_name")
                category = dictionary_match.get("category")
                storage_type = dictionary_match.get("storage_type")
                if normalized_name and category:
                    return normalized_name, category, storage_type

        if raw_aliases:
            return raw_aliases[0], "other", None

        return None, "other", None

    def _lookup_exact_product_alias(self, text: str) -> str | None:
        candidate = str(text or "").strip()
        if not candidate:
            return None
        keys = [
            candidate,
            re.sub(r"\s+", "", candidate),
            re.sub(r"\s+", "", candidate).casefold(),
        ]
        for key in keys:
            aliased = self.rules.product_alias_lookup.get(key)
            if aliased and aliased != candidate:
                return aliased
        return None

    def _looks_like_date(self, text: str) -> bool:
        for pattern in DATE_PATTERNS:
            for match in pattern.finditer(text):
                if self._format_valid_date_match(match) is not None:
                    return True
        return False

    def _looks_like_footer(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if normalized.startswith("계:") or normalized == "계":
            return True
        if self._matches_non_item_category(text, {"summary", "payment"}):
            return True
        return _contains_any(normalized, self.rules.footer_keywords)

    def _looks_like_header(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if self._matches_non_item_category(text, {"header"}):
            return True
        return _contains_any(normalized, self.rules.header_keywords)

    def _looks_like_noise(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if DASH_PATTERN.match(normalized):
            return True
        if self._looks_like_adjustment_row(text):
            return True
        if self._matches_non_item_category(text, {"discount", "metadata"}):
            return True
        if self._matches_non_item_category(text, {"packaging"}) and not self._looks_like_food_packaging_name(text):
            return True
        if _contains_any(normalized, self.rules.structural_noise_keywords):
            return True
        return _contains_any(normalized, self.rules.noise_keywords)

    def _looks_like_pure_noise_line(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return normalized in {"행사", "증정품", "할인", "세일"}

    def _looks_like_adjustment_row(self, text: str) -> bool:
        stripped = text.strip()
        normalized = re.sub(r"\s+", "", stripped)
        if not re.search(r"-\d{1,3}(?:[,.]\d{3})+|-\d+", normalized):
            return False
        return stripped.startswith(("[", "]", "(", "{", "△", "-"))

    def _looks_like_numeric_fragment(self, text: str) -> bool:
        return bool(PRICE_PATTERN.match(text.strip()))

    def _looks_like_barcode(self, text: str) -> bool:
        return bool(BARCODE_PATTERN.match(text.strip()))

    def _looks_like_price(self, text: str) -> bool:
        return bool(PRICE_PATTERN.match(text.strip()))

    def _looks_like_item_candidate(self, text: str) -> bool:
        stripped = self._cleanup_noisy_item_name(text.strip())
        if not stripped:
            return False
        if self._looks_like_header(stripped) or self._looks_like_footer(stripped):
            return False
        if self._looks_like_noise(stripped) or self._looks_like_barcode(stripped):
            return False
        if self._looks_like_numeric_fragment(stripped):
            return False
        if not any("가" <= char <= "힣" for char in stripped):
            return False
        return True

    def _looks_like_probable_item_row(self, text: str) -> bool:
        stripped = text.strip()
        if POS_ITEM_PATTERN.match(stripped):
            return True
        if NAME_QTY_AMOUNT_PATTERN.match(self._cleanup_noisy_item_name(stripped)):
            return True
        if NAME_AMOUNT_PATTERN.match(self._cleanup_noisy_item_name(stripped)):
            return True
        if re.match(r"^\d{6,}\s+\d{1,3}\s+\S+", stripped):
            return True
        if re.match(r"^\d{1,3}\s+\S+", stripped) and re.search(r"\d{1,3}(?:,\d{3})+", stripped):
            return True
        return False

    def _format_valid_date_match(self, match: re.Match[str]) -> str | None:
        year = int(match.group("year"))
        month = int(match.group("month"))
        day = int(match.group("day"))
        if not 1 <= month <= 12:
            return None
        if not 1 <= day <= 31:
            return None
        if year < 100:
            year += 2000
        if not 2000 <= year <= 2099:
            return None
        return f"{year:04d}-{month:02d}-{day:02d}"

    def _date_candidate_score(self, text: str) -> int:
        score = 0
        if _contains_any(text, self.rules.date_hint_keywords):
            score += 3
        if _contains_any(text, self.rules.date_penalty_keywords):
            score -= 3
        return score

    def _normalize_vendor_candidate(self, text: str) -> str | None:
        normalized = re.sub(r"\s+", "", text).lower()
        normalized_compact = re.sub(r"[^0-9a-z가-힣]+", "", normalized)
        for candidate in (normalized, normalized_compact):
            for token, canonical in self.rules.canonical_vendor_aliases.items():
                if token in candidate:
                    return canonical
        return None

    def _looks_like_total_amount_line(self, text: str) -> bool:
        compact = re.sub(r"\s+", "", text)
        return bool(re.search(r"(?:\d{1,3}(?:[,.]\d{3})+|\d{4,})(?:원)?$", compact))

    def _normalize_date_text(self, text: str) -> str:
        extracted = self._extract_purchased_at([OcrLine(text=text, confidence=1.0)])
        return extracted or text

    def _candidate_item_names(self, text: str) -> list[str]:
        original = QUANTITY_PATTERN.sub("", text)
        original = re.sub(r"\d{1,3}(?:,\d{3})+", "", original)
        original = re.sub(r"\*?\d{8,}", " ", original)
        original = re.sub(r"^\d{1,3}\s*", "", original)
        original = re.sub(r"\([^)]*\)", " ", original)
        original = re.sub(r"\b\d+\b", " ", original)
        original = re.sub(r"[^\w가-힣]+", " ", original)
        original = re.sub(r"\s+", " ", original).strip()

        candidates: list[str] = []
        if original:
            candidates.append(original)

        prefix_stripped = re.sub(r"^[가-힣A-Za-z]{1,4}\)", "", original).strip()
        if prefix_stripped and prefix_stripped not in candidates:
            candidates.append(prefix_stripped)

        cleaned = original
        for token in self.rules.brand_tokens:
            cleaned = cleaned.replace(token, "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        for candidate in list(candidates):
            for source, target in self.rules.ocr_canonical_aliases.items():
                if source in candidate:
                    replaced = self._safe_alias_replace(candidate, source, target)
                    if replaced and replaced not in candidates:
                        candidates.append(replaced)

        for candidate in list(candidates):
            aliased = self._apply_product_aliases(candidate)
            if aliased and aliased not in candidates:
                candidates.append(aliased)

        return [candidate for candidate in candidates if candidate]

    def _matches_non_item_category(self, text: str, categories: set[str]) -> bool:
        for rule in self.rules.non_item_rules:
            if rule.name in categories and rule.matches(text):
                return True
        return False

    def _looks_like_food_packaging_name(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text or "")
        if not normalized or not any("가" <= char <= "힣" for char in normalized):
            return False
        return bool(re.search(r"용기(?:면|죽|밥)", normalized))

    def _looks_like_summary_fragment_name(self, text: str) -> bool:
        compact = re.sub(r"[^가-힣]", "", text or "")
        if not compact or len(compact) > 6:
            return False
        return set(compact) <= set("세품가액물부과합계총결제대상금액")

    def _looks_like_domain_noise_name(self, text: str) -> bool:
        candidate = text or ""
        return bool(re.search(r"(?:www|[a-z0-9-]+\.(?:co\.kr|com|net|kr))", candidate, re.IGNORECASE))

    def _looks_like_fragmented_token_noise(self, text: str) -> bool:
        tokens = [token for token in re.split(r"\s+", text or "") if token]
        if len(tokens) < 3:
            return False
        hangul_singletons = [token for token in tokens if re.fullmatch(r"[가-힣]", token)]
        return len(hangul_singletons) >= 2 and any(re.fullmatch(r"\d+", token) for token in tokens)

    def _apply_product_aliases(self, text: str) -> str:
        updated = text
        for source, target in self.rules.product_alias_replacements:
            if source and source in updated:
                updated = self._safe_alias_replace(updated, source, target)
        return updated

    def _safe_alias_replace(self, text: str, source: str, target: str) -> str:
        if not source or source not in text:
            return text
        if target in text:
            return text
        return text.replace(source, target)


def _load_default_ingredient_lookup() -> dict[str, dict[str, str]]:
    master_override = os.getenv("INGREDIENT_MASTER_PATH")
    alias_override = os.getenv("INGREDIENT_ALIAS_PATH")

    if master_override and alias_override:
        master_path = Path(master_override)
        alias_path = Path(alias_override)
    else:
        data_dir = Path(__file__).resolve().parents[1] / "data"
        master_path = data_dir / "ingredient_master.generated.json"
        alias_path = data_dir / "ingredient_alias.generated.json"

    if not master_path.exists() or not alias_path.exists():
        return {}

    try:
        return load_ingredient_lookup(master_path, alias_path)
    except (OSError, ValueError, TypeError):
        return {}
