from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field, replace
import os
from pathlib import Path
import re
from statistics import mean
from typing import Mapping

from .ingredient_dictionary import load_ingredient_lookup


LOW_CONFIDENCE_THRESHOLD = 0.80
ROW_GROUP_TOLERANCE = 26.0

DATE_PATTERNS = (
    re.compile(r"(?P<year>20\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
    re.compile(r"(?P<year>\d{2})[./-](?P<month>\d{1,2})[./-](?P<day>\d{1,2})"),
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
COMPACT_BARCODE_ITEM_PATTERN = re.compile(
    r"^(?P<barcode>\*?\d{8,})\s+"
    r"(?:(?P<unit_price>\d{1,3}(?:,\d{3})+|\d+)\s+)?"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:,\d{3})+|\d+)$"
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
NAME_AMOUNT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
NAME_GIFT_PATTERN = re.compile(
    r"^(?P<name>.+?)\s+(?P<quantity>\d+(?:\.\d+)?)\s+증정품$"
)
NUMERIC_DETAIL_ROW_PATTERN = re.compile(
    r"^(?P<unit_price>\d{1,3}(?:[,.]\d{3})+|\d+)\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<amount>\d{1,3}(?:[,.]\d{3})+|\d+)$"
)
PRICE_PATTERN = re.compile(r"^\d{1,3}(?:[,.]\d{3})+$|^\d+$")
COUNT_PATTERN = re.compile(r"^\d+(?:\.\d+)?$")
BARCODE_PATTERN = re.compile(r"^\*?\d{8,}$")
DASH_PATTERN = re.compile(r"^[\-\_=]{3,}$")

TOTAL_KEYWORDS = (
    "합계",
    "총계",
    "결제금액",
    "결제대상액",
    "최종결제",
    "과세물품가액",
    "과세물품",
    "공급가액",
    "부가세",
    "세액",
    "현금",
    "카드결제",
)
PAYMENT_KEYWORDS = ("결제금액", "결제대상액", "최종결제", "현금", "카드결제")
DATE_HINT_KEYWORDS = ("판매일", "구매", "주문", "결제", "거래일")
FOOTER_KEYWORDS = (
    "합계",
    "총계",
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
BRAND_TOKENS = ("서울우유", "비비고", "CJ", "농심", "오뚜기", "매일", "빙그레")
OCR_CANONICAL_ALIASES = {
    "깨잎": "깻잎",
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
    def __init__(self, ingredient_lookup: Mapping[str, Mapping[str, str]] | None = None) -> None:
        self.ingredient_lookup = ingredient_lookup or _load_default_ingredient_lookup()

    def parse_lines(self, lines: list[OcrLine]) -> ReceiptParseResult:
        ordered_lines = self._prepare_lines(lines)
        vendor_name = self._extract_vendor_name(ordered_lines)
        purchased_at = self._extract_purchased_at(ordered_lines)
        totals = self._extract_totals(ordered_lines)
        sections, section_confidence = self._classify_sections(ordered_lines, vendor_name, purchased_at)

        items, consumed_line_ids = self._parse_items(ordered_lines, sections, purchased_at)

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
            if self._looks_like_header(text) or self._looks_like_probable_item_row(text):
                break
            if self._looks_like_date(text) or self._looks_like_footer(text) or self._looks_like_header(text):
                continue
            if self._looks_like_numeric_fragment(text) or self._looks_like_noise(text) or self._looks_like_barcode(text):
                continue
            if any(keyword in text for keyword in VENDOR_BLOCK_KEYWORDS):
                continue
            return text
        return None

    def _extract_purchased_at(self, lines: list[OcrLine]) -> str | None:
        best_candidate: tuple[int, str] | None = None
        for line in lines:
            text = line.text.strip()
            if not text:
                continue
            for pattern in DATE_PATTERNS:
                for match in pattern.finditer(text):
                    candidate = self._format_valid_date_match(match)
                    if candidate is None:
                        continue
                    score = self._date_candidate_score(text)
                    if best_candidate is None or score > best_candidate[0]:
                        best_candidate = (score, candidate)
        return best_candidate[1] if best_candidate else None

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
                sections[line_id] = "payment" if any(keyword in normalized for keyword in PAYMENT_KEYWORDS) else "totals"
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

            columnar_item = self._parse_columnar_item(lines, index, sections, purchased_at)
            if columnar_item is not None:
                item, consumed_count = columnar_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            numeric_detail_item = self._parse_name_then_numeric_detail_item(lines, index, sections, purchased_at)
            if numeric_detail_item is not None:
                item, consumed_count = numeric_detail_item
                items.append(item)
                consumed_line_ids.update(item.source_line_ids)
                index += consumed_count
                continue

            single_line_item = self._build_single_line_item(line, purchased_at)
            if single_line_item is not None:
                items.append(single_line_item)
                consumed_line_ids.update(single_line_item.source_line_ids)
            index += 1

        return items, consumed_line_ids

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
            score = 0
            first_structured_index: int | None = None
            for candidate in lines[start : min(start + 5, len(lines))]:
                if self._looks_like_structured_item_row(candidate.text):
                    score += 1
                    if first_structured_index is None:
                        first_structured_index = candidate.page_order if candidate.page_order is not None else start
                elif self._looks_like_noise(candidate.text) or self._looks_like_pure_noise_line(candidate.text):
                    continue
                elif score > 0:
                    break
            if score >= 2:
                return first_structured_index if first_structured_index is not None else start
        return 0

    def _looks_like_item_like_row(self, text: str) -> bool:
        stripped = self._cleanup_noisy_item_name(text.strip())
        if not self._looks_like_item_candidate(stripped):
            return False
        return bool(
            POS_ITEM_PATTERN.match(stripped)
            or NAME_QTY_AMOUNT_PATTERN.match(stripped)
            or NAME_AMOUNT_PATTERN.match(stripped)
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
            or NAME_GIFT_PATTERN.match(text.strip())
            or COMPACT_BARCODE_ITEM_PATTERN.match(text.strip())
            or COMPACT_BARCODE_INFERRED_QTY_PATTERN.match(text.strip())
        )

    def _looks_like_item_header(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if "합계" in normalized or "총계" in normalized or "결제" in normalized:
            return False
        return any(keyword in normalized for keyword in ("상품명", "단가", "수량", "금액"))

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
        compact_match = COMPACT_BARCODE_ITEM_PATTERN.match(compact_line.text.strip())
        inferred_qty_match = COMPACT_BARCODE_INFERRED_QTY_PATTERN.match(compact_line.text.strip())
        cleaned_name = self._cleanup_noisy_item_name(name_line.text.strip())
        if (
            compact_match is not None
            and self._looks_like_item_candidate(cleaned_name)
        ):
            consumed_count = 2
            if index + 2 < len(lines) and self._looks_like_pure_noise_line(lines[index + 2].text):
                consumed_count += 1
            return (
                self._build_item(
                    raw_name=cleaned_name,
                    confidence_lines=[name_line, compact_line],
                    purchased_at=purchased_at,
                    quantity=float(compact_match.group("quantity")),
                    unit="개",
                    amount=self._extract_last_price(compact_match.group("amount")),
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
            and self._looks_like_item_candidate(cleaned_name)
        ):
            consumed_count = 2
            if index + 2 < len(lines) and self._looks_like_pure_noise_line(lines[index + 2].text):
                consumed_count += 1
            return (
                self._build_item(
                    raw_name=cleaned_name,
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

        consumed_count = 4
        if index + 4 < len(lines) and self._looks_like_pure_noise_line(lines[index + 4].text):
            consumed_count += 1

        item = self._build_item(
            raw_name=name_line.text.strip(),
            confidence_lines=[name_line, barcode_line, quantity_line, amount_line],
            purchased_at=purchased_at,
            quantity=float(quantity_line.text.strip()),
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

        match = NUMERIC_DETAIL_ROW_PATTERN.match(detail_line.text.strip())
        if match is None:
            return None

        amount = self._extract_last_price(match.group("amount"))
        if amount is None:
            return None

        return (
            self._build_item(
                raw_name=cleaned_name,
                confidence_lines=[name_line, detail_line],
                purchased_at=purchased_at,
                quantity=float(match.group("quantity")),
                unit="개",
                amount=amount,
                parse_pattern="name_then_numeric_detail",
                source_line_ids=[name_line.line_id or 0, detail_line.line_id or 0],
            ),
            2,
        )

    def _normalize_ocr_noisy_pos_text(self, text: str) -> str:
        normalized = text.strip()
        normalized = re.sub(r"([0-9])[\*\#\$]+", r"\1", normalized)
        normalized = re.sub(r"^(?P<line>\d{1,3})(?=[가-힣A-Za-z(])", r"\g<line> ", normalized)
        normalized = re.sub(r"^\s+", "", normalized)
        return normalized

    def _cleanup_noisy_item_name(self, text: str) -> str:
        cleaned = text
        cleaned = re.sub(r"^\*?\d{8,}\s*", "", cleaned)
        cleaned = re.sub(r"^\d{1,3}\s*", "", cleaned)
        cleaned = re.sub(r"^\d{1,3}(?=[가-힣A-Za-z])", "", cleaned)
        cleaned = re.sub(r"\b(행사|증정품)\b", " ", cleaned)
        cleaned = re.sub(r"\b1[가-힣A-Za-z]{1,3}$", "", cleaned).strip()
        cleaned = re.sub(r"\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        return cleaned

    def _build_single_line_item(self, line: OcrLine, purchased_at: str | None) -> ReceiptItem | None:
        gift_candidate = line.text.strip()
        gift_candidate = re.sub(r"^\*?\d{8,}\s*", "", gift_candidate)
        gift_candidate = re.sub(r"^\d{1,3}\s*", "", gift_candidate)
        gift_candidate = re.sub(r"^\d{1,3}(?=[가-힣A-Za-z])", "", gift_candidate)
        cleaned_name = self._cleanup_noisy_item_name(line.text.strip())
        if not self._looks_like_item_candidate(cleaned_name):
            return None

        gift_match = NAME_GIFT_PATTERN.match(gift_candidate)
        if gift_match is not None:
            return self._build_item(
                raw_name=gift_match.group("name").strip(),
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=float(gift_match.group("quantity")),
                unit="개",
                amount=None,
                parse_pattern="single_line_gift",
                source_line_ids=[line.line_id or 0],
            )

        qty_amount_match = NAME_QTY_AMOUNT_PATTERN.match(cleaned_name)
        if qty_amount_match is not None:
            amount = self._extract_last_price(qty_amount_match.group("amount"))
            if amount is None:
                return None
            return self._build_item(
                raw_name=qty_amount_match.group("name").strip(),
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=float(qty_amount_match.group("quantity")),
                unit="개",
                amount=amount,
                parse_pattern="single_line_name_qty_amount",
                source_line_ids=[line.line_id or 0],
            )

        amount_match = NAME_AMOUNT_PATTERN.match(cleaned_name)
        if amount_match is not None:
            amount = self._extract_last_price(amount_match.group("amount"))
            if amount is None:
                return None
            return self._build_item(
                raw_name=amount_match.group("name").strip(),
                confidence_lines=[line],
                purchased_at=purchased_at,
                quantity=1.0,
                unit="개",
                amount=amount,
                parse_pattern="single_line_name_amount",
                source_line_ids=[line.line_id or 0],
            )

        quantity, unit = self._extract_quantity(line.text)
        amount = self._extract_last_price(line.text)
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
            needs_review=bool(review_reason),
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
            text = line.text.strip()
            normalized = re.sub(r"\s+", "", text)
            total_key = self._classify_total_key(normalized)
            if total_key is None:
                continue

            amount = self._extract_last_price(text)
            if amount is None and index + 1 < len(lines):
                next_text = lines[index + 1].text.strip()
                if PRICE_PATTERN.match(next_text):
                    amount = self._extract_last_price(next_text)
            if amount is not None:
                totals[total_key] = amount

        if "payment_amount" not in totals and "total" in totals:
            totals["payment_amount"] = totals["total"]
        return totals

    def _classify_total_key(self, normalized_text: str) -> str | None:
        if any(keyword in normalized_text for keyword in PAYMENT_KEYWORDS):
            return "payment_amount"
        if "부가세" in normalized_text or "세액" in normalized_text:
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

    def _normalize_item_name(self, text: str) -> tuple[str | None, str, str | None]:
        candidates = self._candidate_item_names(text)
        for candidate in candidates:
            for pattern, normalized_name, category in ITEM_RULES:
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

        return None, "other", None

    def _looks_like_date(self, text: str) -> bool:
        for pattern in DATE_PATTERNS:
            for match in pattern.finditer(text):
                if self._format_valid_date_match(match) is not None:
                    return True
        return False

    def _looks_like_footer(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return any(keyword in normalized for keyword in FOOTER_KEYWORDS)

    def _looks_like_header(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return any(keyword in normalized for keyword in HEADER_KEYWORDS)

    def _looks_like_noise(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if DASH_PATTERN.match(normalized):
            return True
        if any(keyword in normalized for keyword in STRUCTURAL_NOISE_KEYWORDS):
            return True
        return any(keyword in normalized for keyword in NOISE_KEYWORDS)

    def _looks_like_pure_noise_line(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        return normalized in {"행사", "증정품", "할인", "세일"}

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
        if any(keyword in text for keyword in DATE_HINT_KEYWORDS):
            score += 3
        if re.search(r"\d{1,2}:\d{2}", text):
            score += 1
        if any(keyword in text for keyword in ("사업자", "주소", "대표", "전화")):
            score -= 3
        return score

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
        for token in BRAND_TOKENS:
            cleaned = cleaned.replace(token, "").strip()
        if cleaned and cleaned not in candidates:
            candidates.append(cleaned)

        for candidate in list(candidates):
            for source, target in OCR_CANONICAL_ALIASES.items():
                if source in candidate:
                    replaced = candidate.replace(source, target)
                    if replaced and replaced not in candidates:
                        candidates.append(replaced)

        return [candidate for candidate in candidates if candidate]


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
