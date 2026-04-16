from __future__ import annotations

from collections import defaultdict
from typing import Any, Callable
import re


IngredientMatcher = Callable[[str], dict[str, Any] | None]

RULE_BASED_SOURCES = {
    "receipt_rule_product_mapping",
    "receipt_rule_product_mapping_fallback",
}

FALSE_POSITIVE_PATTERNS = (
    re.compile(r"에누리"),
    re.compile(r"s-?point", re.IGNORECASE),
    re.compile(r"\bga\d{4,}", re.IGNORECASE),
    re.compile(r"\byldp", re.IGNORECASE),
    re.compile(r"지점"),
    re.compile(r"보험"),
    re.compile(r"약제비"),
    re.compile(r"본인부담"),
    re.compile(r"종량"),
)


def build_rule_candidate_report(
    parsed_receipts: list[dict[str, Any]],
    ingredient_matcher: IngredientMatcher,
) -> dict[str, Any]:
    alias_candidates: dict[tuple[str, str], dict[str, Any]] = {}
    unmapped_products: dict[str, dict[str, Any]] = {}
    weak_match_products: dict[tuple[str, str], dict[str, Any]] = {}
    false_positive_item_candidates: dict[str, dict[str, Any]] = {}
    item_count = 0

    for receipt in parsed_receipts:
        file_name = str(receipt.get("file_name") or "")
        for item in receipt.get("items", []):
            if not isinstance(item, dict):
                continue

            raw_name = str(item.get("raw_name") or "").strip()
            normalized_name = str(item.get("normalized_name") or raw_name).strip()
            if not raw_name and not normalized_name:
                continue

            item_count += 1
            confidence = _safe_float(item.get("confidence"))
            parse_pattern = str(item.get("parse_pattern") or "").strip()
            product_name = normalized_name or raw_name

            if _normalize_for_compare(raw_name) and _normalize_for_compare(raw_name) != _normalize_for_compare(normalized_name):
                key = (raw_name, normalized_name)
                entry = alias_candidates.setdefault(
                    key,
                    {
                        "raw_name": raw_name,
                        "normalized_name": normalized_name,
                        "count": 0,
                        "sample_files": [],
                        "parse_patterns": defaultdict(int),
                        "confidence_values": [],
                    },
                )
                _update_candidate_entry(
                    entry,
                    file_name=file_name,
                    parse_pattern=parse_pattern,
                    confidence=confidence,
                )

            if _looks_like_false_positive_item(product_name):
                entry = false_positive_item_candidates.setdefault(
                    product_name,
                    {
                        "product_name": product_name,
                        "count": 0,
                        "sample_files": [],
                        "parse_patterns": defaultdict(int),
                        "confidence_values": [],
                    },
                )
                _update_candidate_entry(
                    entry,
                    file_name=file_name,
                    parse_pattern=parse_pattern,
                    confidence=confidence,
                )
                continue

            match = ingredient_matcher(product_name)
            if match is None:
                entry = unmapped_products.setdefault(
                    product_name,
                    {
                        "product_name": product_name,
                        "count": 0,
                        "sample_files": [],
                        "parse_patterns": defaultdict(int),
                        "confidence_values": [],
                    },
                )
                _update_candidate_entry(
                    entry,
                    file_name=file_name,
                    parse_pattern=parse_pattern,
                    confidence=confidence,
                )
                continue

            mapping_source = str(match.get("mapping_source") or "")
            similarity = _safe_float(match.get("similarity"))
            ingredient_name = str(match.get("ingredientName") or "").strip()

            if _is_weak_match(
                product_name=product_name,
                ingredient_name=ingredient_name,
                mapping_source=mapping_source,
                similarity=similarity,
            ):
                key = (product_name, ingredient_name)
                entry = weak_match_products.setdefault(
                    key,
                    {
                        "product_name": product_name,
                        "ingredient_name": ingredient_name,
                        "mapping_source": mapping_source,
                        "similarity": similarity,
                        "count": 0,
                        "sample_files": [],
                        "parse_patterns": defaultdict(int),
                        "confidence_values": [],
                    },
                )
                _update_candidate_entry(
                    entry,
                    file_name=file_name,
                    parse_pattern=parse_pattern,
                    confidence=confidence,
                )

    return {
        "summary": {
            "receipt_count": len(parsed_receipts),
            "item_count": item_count,
            "alias_candidate_count": len(alias_candidates),
            "unmapped_product_count": len(unmapped_products),
            "weak_match_product_count": len(weak_match_products),
            "false_positive_item_candidate_count": len(false_positive_item_candidates),
        },
        "alias_candidates": _finalize_candidates(alias_candidates.values(), sort_keys=("count", "raw_name")),
        "unmapped_products": _finalize_candidates(unmapped_products.values(), sort_keys=("count", "product_name")),
        "weak_match_products": _finalize_candidates(weak_match_products.values(), sort_keys=("count", "product_name")),
        "false_positive_item_candidates": _finalize_candidates(
            false_positive_item_candidates.values(),
            sort_keys=("count", "product_name"),
        ),
    }


def _update_candidate_entry(
    entry: dict[str, Any],
    *,
    file_name: str,
    parse_pattern: str,
    confidence: float | None,
) -> None:
    entry["count"] += 1
    if file_name and file_name not in entry["sample_files"] and len(entry["sample_files"]) < 5:
        entry["sample_files"].append(file_name)
    if parse_pattern:
        entry["parse_patterns"][parse_pattern] += 1
    if confidence is not None:
        entry["confidence_values"].append(confidence)


def _finalize_candidates(entries: Any, *, sort_keys: tuple[str, str]) -> list[dict[str, Any]]:
    finalized: list[dict[str, Any]] = []
    for entry in entries:
        item = dict(entry)
        confidence_values = item.pop("confidence_values", [])
        parse_patterns = item.pop("parse_patterns", {})
        item["avg_confidence"] = round(sum(confidence_values) / len(confidence_values), 4) if confidence_values else None
        item["parse_patterns"] = [
            {"name": name, "count": count}
            for name, count in sorted(parse_patterns.items(), key=lambda pair: (-pair[1], pair[0]))
        ]
        finalized.append(item)

    primary_key, secondary_key = sort_keys
    return sorted(
        finalized,
        key=lambda item: (
            -int(item.get(primary_key, 0)),
            str(item.get(secondary_key, "")),
        ),
    )


def _normalize_for_compare(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip().lower()


def _safe_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_weak_match(
    *,
    product_name: str,
    ingredient_name: str,
    mapping_source: str,
    similarity: float | None,
) -> bool:
    if not product_name or not ingredient_name:
        return False
    if mapping_source in RULE_BASED_SOURCES:
        return False
    if similarity is not None and similarity < 0.85:
        return True
    return _normalize_for_compare(product_name) != _normalize_for_compare(ingredient_name)


def _looks_like_false_positive_item(product_name: str) -> bool:
    normalized = product_name.strip()
    if not normalized:
        return True
    compact = _normalize_for_compare(normalized)
    alpha_count = len(re.findall(r"[가-힣A-Za-z]", normalized))
    if len(compact) <= 1:
        return True
    if any(pattern.search(normalized) for pattern in FALSE_POSITIVE_PATTERNS):
        return True
    digit_count = sum(character.isdigit() for character in normalized)
    if digit_count >= 5 and not re.search(r"[가-힣A-Za-z]{2,}", normalized):
        return True
    if re.search(r"[-+]?\d[\d,]*\s*원?$", normalized) and len(compact) <= 10 and alpha_count < 3:
        return True
    return False
