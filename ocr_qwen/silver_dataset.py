from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


VALID_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
EXCLUDED_NAME_MARKERS = ("items-crop",)


def is_receipt_candidate(path: Path) -> bool:
    if not path.is_file():
        return False
    if path.suffix.lower() not in VALID_RECEIPT_EXTENSIONS:
        return False
    lowered_name = path.name.lower()
    if any(marker in lowered_name for marker in EXCLUDED_NAME_MARKERS):
        return False
    return True


def discover_receipt_images(input_dir: Path) -> list[Path]:
    directory = Path(input_dir)
    if not directory.exists():
        raise FileNotFoundError(f"Receipt input directory not found: {directory}")
    return sorted(
        [path for path in directory.iterdir() if is_receipt_candidate(path)],
        key=lambda path: path.name,
    )


def build_silver_annotation(
    *,
    image_path: Path,
    parsed: dict[str, Any],
    dataset_name: str,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or _utc_now_isoformat()
    return {
        "dataset_name": dataset_name,
        "label_source": "silver-current-engine",
        "generated_at": timestamp,
        "image": {
            "file_name": image_path.name,
            "source_path": str(image_path),
        },
        "parser": {
            "engine_version": parsed.get("engine_version", "receipt-engine-v2"),
        },
        "expected": {
            "vendor_name": parsed.get("vendor_name"),
            "purchased_at": parsed.get("purchased_at"),
            "ocr_texts": list(parsed.get("ocr_texts", [])),
            "items": list(parsed.get("items", [])),
            "totals": dict(parsed.get("totals", {})),
            "review_required": bool(parsed.get("review_required", False)),
            "review_reasons": list(parsed.get("review_reasons", [])),
            "diagnostics": dict(parsed.get("diagnostics", {})),
        },
    }


def build_dataset_manifest(
    *,
    dataset_name: str,
    input_dir: Path,
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "dataset_name": dataset_name,
        "input_dir": str(input_dir),
        "image_count": len(annotations),
        "total_item_count": sum(len(annotation.get("expected", {}).get("items", [])) for annotation in annotations),
        "review_required_count": sum(
            1 for annotation in annotations if annotation.get("expected", {}).get("review_required") is True
        ),
        "images": [
            {
                "file_name": annotation.get("image", {}).get("file_name"),
                "source_path": annotation.get("image", {}).get("source_path"),
            }
            for annotation in annotations
        ],
    }


def safe_annotation_stem(path_or_name: str | Path) -> str:
    value = path_or_name.name if isinstance(path_or_name, Path) else str(path_or_name)
    stem = Path(value).stem
    return (
        __import__("re").sub(r"[^a-zA-Z0-9._-]+", "_", stem).strip("_")
        or "receipt"
    )


def compute_item_name_f1(
    *,
    expected_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
) -> dict[str, float | int]:
    expected_name_groups, actual_name_groups, matched_pairs = _match_item_name_groups(
        expected_items=expected_items,
        actual_items=actual_items,
    )

    tp = len(matched_pairs)

    fp = len(actual_name_groups) - tp
    fn = len(expected_name_groups) - tp

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def compute_item_field_match_rates(
    *,
    expected_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
) -> dict[str, float | int]:
    _, _, matched_pairs = _match_item_name_groups(
        expected_items=expected_items,
        actual_items=actual_items,
    )

    quantity_expected = 0
    quantity_matches = 0
    amount_expected = 0
    amount_matches = 0

    for expected_index, expected_item in enumerate(expected_items):
        if not isinstance(expected_item, dict):
            continue
        matched_actual_index = matched_pairs.get(expected_index)
        actual_item = actual_items[matched_actual_index] if matched_actual_index is not None else None

        expected_quantity = _coerce_number(expected_item.get("quantity"))
        if expected_quantity is not None:
            quantity_expected += 1
            actual_quantity = _coerce_number(actual_item.get("quantity")) if isinstance(actual_item, dict) else None
            if actual_quantity is not None and abs(expected_quantity - actual_quantity) < 0.001:
                quantity_matches += 1

        expected_amount = _coerce_number(expected_item.get("amount"))
        if expected_amount is not None:
            amount_expected += 1
            actual_amount = _coerce_number(actual_item.get("amount")) if isinstance(actual_item, dict) else None
            if actual_amount is not None and abs(expected_amount - actual_amount) < 0.001:
                amount_matches += 1

    return {
        "quantity_match_count": quantity_matches,
        "quantity_expected_count": quantity_expected,
        "quantity_match_rate": round(quantity_matches / quantity_expected, 4) if quantity_expected else 0.0,
        "amount_match_count": amount_matches,
        "amount_expected_count": amount_expected,
        "amount_match_rate": round(amount_matches / amount_expected, 4) if amount_expected else 0.0,
    }


def compare_silver_annotation(
    *,
    annotation: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    expected = annotation.get("expected", {})
    expected_totals = expected.get("totals", {}) if isinstance(expected, dict) else {}
    parsed_totals = parsed.get("totals", {}) if isinstance(parsed, dict) else {}
    actual_items = parsed.get("items", []) if isinstance(parsed, dict) else []
    ignored_actual_items = expected.get("uncertain_items", []) if isinstance(expected, dict) else []
    filtered_actual_items = _filter_ignored_actual_items(
        actual_items=actual_items,
        ignored_items=ignored_actual_items,
    )

    item_metrics = compute_item_name_f1(
        expected_items=expected.get("items", []) if isinstance(expected, dict) else [],
        actual_items=filtered_actual_items,
    )
    field_metrics = compute_item_field_match_rates(
        expected_items=expected.get("items", []) if isinstance(expected, dict) else [],
        actual_items=filtered_actual_items,
    )

    expected_payment_amount = expected_totals.get("payment_amount")
    actual_payment_amount = parsed_totals.get("payment_amount")
    expected_review_required = bool(expected.get("review_required", False)) if isinstance(expected, dict) else False
    actual_review_required = bool(parsed.get("review_required", False)) if isinstance(parsed, dict) else False

    return {
        "vendor_name_match": expected.get("vendor_name") == parsed.get("vendor_name"),
        "purchased_at_match": expected.get("purchased_at") == parsed.get("purchased_at"),
        "payment_amount_match": expected_payment_amount == actual_payment_amount,
        "item_name_precision": item_metrics["precision"],
        "item_name_recall": item_metrics["recall"],
        "item_name_f1": item_metrics["f1"],
        "tp": item_metrics["tp"],
        "fp": item_metrics["fp"],
        "fn": item_metrics["fn"],
        "quantity_match_count": field_metrics["quantity_match_count"],
        "quantity_expected_count": field_metrics["quantity_expected_count"],
        "quantity_match_rate": field_metrics["quantity_match_rate"],
        "amount_match_count": field_metrics["amount_match_count"],
        "amount_expected_count": field_metrics["amount_expected_count"],
        "amount_match_rate": field_metrics["amount_match_rate"],
        "review_required_match": expected_review_required == actual_review_required,
    }


def _filter_ignored_actual_items(
    *,
    actual_items: list[dict[str, Any]],
    ignored_items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    ignored_name_groups = _extract_item_name_groups(ignored_items)
    if not ignored_name_groups:
        return list(actual_items)

    filtered: list[dict[str, Any]] = []
    for item in actual_items:
        if not isinstance(item, dict):
            filtered.append(item)
            continue
        item_groups = _extract_item_name_groups([item])
        if item_groups and any(item_groups[0] & ignored_names for ignored_names in ignored_name_groups):
            continue
        filtered.append(item)
    return filtered


def _extract_item_name_groups(items: list[dict[str, Any]]) -> list[set[str]]:
    groups: list[set[str]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        candidates: set[str] = set()
        for field_name in ("normalized_name", "raw_name", "product_name", "name"):
            value = item.get(field_name)
            if not isinstance(value, str):
                continue
            cleaned = _normalize_item_name_for_compare(value)
            if cleaned:
                candidates.add(cleaned)
        if candidates:
            groups.append(candidates)
    return groups


def _normalize_item_name_for_compare(value: str) -> str:
    normalized = re.sub(r"\s+", "", value).strip().lower()
    normalized = re.sub(r"\((?:\d+입|\d+개)\)", "", normalized)
    return normalized


def _match_item_name_groups(
    *,
    expected_items: list[dict[str, Any]],
    actual_items: list[dict[str, Any]],
) -> tuple[list[set[str]], list[set[str]], dict[int, int]]:
    expected_name_groups = _extract_item_name_groups(expected_items)
    actual_name_groups = _extract_item_name_groups(actual_items)

    matched_actual_indices: set[int] = set()
    matched_pairs: dict[int, int] = {}
    for expected_index, expected_names in enumerate(expected_name_groups):
        for actual_index, actual_names in enumerate(actual_name_groups):
            if actual_index in matched_actual_indices:
                continue
            if expected_names & actual_names:
                matched_actual_indices.add(actual_index)
                matched_pairs[expected_index] = actual_index
                break
    return expected_name_groups, actual_name_groups, matched_pairs


def _coerce_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
