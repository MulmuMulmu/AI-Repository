from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any


VALID_RECEIPT_EXTENSIONS = {".jpg", ".jpeg", ".png"}
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
    expected_name_groups = _extract_item_name_groups(expected_items)
    actual_name_groups = _extract_item_name_groups(actual_items)

    matched_actual_indices: set[int] = set()
    tp = 0
    for expected_names in expected_name_groups:
        for actual_index, actual_names in enumerate(actual_name_groups):
            if actual_index in matched_actual_indices:
                continue
            if expected_names & actual_names:
                matched_actual_indices.add(actual_index)
                tp += 1
                break

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


def compare_silver_annotation(
    *,
    annotation: dict[str, Any],
    parsed: dict[str, Any],
) -> dict[str, Any]:
    expected = annotation.get("expected", {})
    expected_totals = expected.get("totals", {}) if isinstance(expected, dict) else {}
    parsed_totals = parsed.get("totals", {}) if isinstance(parsed, dict) else {}

    item_metrics = compute_item_name_f1(
        expected_items=expected.get("items", []) if isinstance(expected, dict) else [],
        actual_items=parsed.get("items", []) if isinstance(parsed, dict) else [],
    )

    expected_payment_amount = expected_totals.get("payment_amount")
    actual_payment_amount = parsed_totals.get("payment_amount")

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
    }


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
    return re.sub(r"\s+", "", value).strip().lower()


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
