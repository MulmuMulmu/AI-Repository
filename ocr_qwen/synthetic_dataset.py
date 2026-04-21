from __future__ import annotations

from typing import Any

from .silver_dataset import compute_item_name_f1


def compare_synthetic_annotation(
    *,
    annotation: dict[str, Any],
    parsed: dict[str, Any],
    processing_seconds: float,
) -> dict[str, Any]:
    expected = annotation.get("expected", {}) if isinstance(annotation, dict) else {}
    expected_items = expected.get("items", []) if isinstance(expected, dict) else []
    actual_items = parsed.get("items", []) if isinstance(parsed, dict) else []
    expected_totals = expected.get("totals", {}) if isinstance(expected, dict) else {}
    actual_totals = parsed.get("totals", {}) if isinstance(parsed, dict) else {}

    item_metrics = compute_item_name_f1(expected_items=expected_items, actual_items=actual_items)
    matched_pairs = _match_items(expected_items=expected_items, actual_items=actual_items)

    quantity_matches = 0
    amount_matches = 0
    for expected_item, actual_item in matched_pairs:
        if _coerce_float(expected_item.get("quantity")) == _coerce_float(actual_item.get("quantity")):
            quantity_matches += 1
        if _coerce_float(expected_item.get("amount")) == _coerce_float(actual_item.get("amount")):
            amount_matches += 1

    matched_item_count = len(matched_pairs)
    quantity_match_rate = round(quantity_matches / matched_item_count, 4) if matched_item_count else 0.0
    amount_match_rate = round(amount_matches / matched_item_count, 4) if matched_item_count else 0.0

    return {
        "vendor_name_match": expected.get("vendor_name") == parsed.get("vendor_name"),
        "purchased_at_match": expected.get("purchased_at") == parsed.get("purchased_at"),
        "payment_amount_match": _coerce_float(expected_totals.get("payment_amount")) == _coerce_float(actual_totals.get("payment_amount")),
        "item_name_precision": item_metrics["precision"],
        "item_name_recall": item_metrics["recall"],
        "item_name_f1": item_metrics["f1"],
        "tp": item_metrics["tp"],
        "fp": item_metrics["fp"],
        "fn": item_metrics["fn"],
        "matched_item_count": matched_item_count,
        "quantity_match_rate": quantity_match_rate,
        "amount_match_rate": amount_match_rate,
        "review_required": bool(parsed.get("review_required", False)),
        "processing_seconds": round(float(processing_seconds), 4),
    }


def summarize_synthetic_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    if not results:
        return {
            "image_count": 0,
            "vendor_name_accuracy": 0.0,
            "purchased_at_accuracy": 0.0,
            "payment_amount_accuracy": 0.0,
            "item_name_precision_avg": 0.0,
            "item_name_recall_avg": 0.0,
            "item_name_f1_avg": 0.0,
            "quantity_match_rate_avg": 0.0,
            "amount_match_rate_avg": 0.0,
            "review_required_rate": 0.0,
            "avg_processing_seconds": 0.0,
        }

    image_count = len(results)
    return {
        "image_count": image_count,
        "vendor_name_accuracy": round(sum(1 for item in results if item["vendor_name_match"]) / image_count, 4),
        "purchased_at_accuracy": round(sum(1 for item in results if item["purchased_at_match"]) / image_count, 4),
        "payment_amount_accuracy": round(sum(1 for item in results if item["payment_amount_match"]) / image_count, 4),
        "item_name_precision_avg": round(sum(float(item["item_name_precision"]) for item in results) / image_count, 4),
        "item_name_recall_avg": round(sum(float(item["item_name_recall"]) for item in results) / image_count, 4),
        "item_name_f1_avg": round(sum(float(item["item_name_f1"]) for item in results) / image_count, 4),
        "quantity_match_rate_avg": round(sum(float(item["quantity_match_rate"]) for item in results) / image_count, 4),
        "amount_match_rate_avg": round(sum(float(item["amount_match_rate"]) for item in results) / image_count, 4),
        "review_required_rate": round(sum(1 for item in results if item["review_required"]) / image_count, 4),
        "avg_processing_seconds": round(sum(float(item["processing_seconds"]) for item in results) / image_count, 4),
    }


def _match_items(
    *,
    expected_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    normalized_actual = [_extract_item_names(item) for item in actual_items]
    used_actual_indices: set[int] = set()
    matches: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for expected_item in expected_items:
        expected_names = _extract_item_names(expected_item)
        if not expected_names:
            continue
        for actual_index, actual_names in enumerate(normalized_actual):
            if actual_index in used_actual_indices:
                continue
            if expected_names & actual_names:
                used_actual_indices.add(actual_index)
                matches.append((expected_item, actual_items[actual_index]))
                break
    return matches


def _extract_item_names(item: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("normalized_name", "raw_name", "product_name", "name"):
        value = item.get(key)
        if isinstance(value, str):
            cleaned = "".join(value.lower().split())
            if cleaned:
                names.add(cleaned)
    return names


def _coerce_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace(",", "").strip()
        if not cleaned:
            return None
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None
