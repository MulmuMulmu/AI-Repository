from __future__ import annotations

from pathlib import Path

from ocr_qwen.silver_dataset import (
    build_dataset_manifest,
    build_silver_annotation,
    compare_silver_annotation,
    compute_item_name_f1,
    discover_receipt_images,
)


def test_discover_receipt_images_filters_out_crops_and_non_image_artifacts(tmp_path: Path) -> None:
    for name in (
        "img2.jpg",
        "img3.jpg",
        "SE-123.jpg",
        "img2.items-crop.jpg",
        "sample.qwen.json",
        "OIP.webp",
        "notes.hwpx",
    ):
        (tmp_path / name).write_text("x", encoding="utf-8")

    result = discover_receipt_images(tmp_path)

    assert [path.name for path in result] == [
        "OIP.webp",
        "SE-123.jpg",
        "img2.jpg",
        "img3.jpg",
    ]


def test_build_silver_annotation_uses_current_parse_output_as_expected_schema(tmp_path: Path) -> None:
    image_path = tmp_path / "img2.jpg"
    image_path.write_text("x", encoding="utf-8")

    annotation = build_silver_annotation(
        image_path=image_path,
        parsed={
            "engine_version": "receipt-engine-v2",
            "vendor_name": "GS25",
            "purchased_at": "2023-11-25",
            "ocr_texts": [{"text": "허쉬쿠키앤크림 1 1,600", "confidence": 0.91}],
            "items": [{"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "amount": 1600.0}],
            "totals": {"payment_amount": 24090.0},
            "review_required": True,
            "review_reasons": ["unresolved_items"],
            "diagnostics": {"qwen_used": False},
        },
        dataset_name="jevi-silver-v0",
        generated_at="2026-04-16T00:00:00Z",
    )

    assert annotation["dataset_name"] == "jevi-silver-v0"
    assert annotation["image"]["file_name"] == "img2.jpg"
    assert annotation["label_source"] == "silver-current-engine"
    assert annotation["expected"]["vendor_name"] == "GS25"
    assert annotation["expected"]["purchased_at"] == "2023-11-25"
    assert annotation["expected"]["ocr_texts"][0]["text"] == "허쉬쿠키앤크림 1 1,600"
    assert annotation["expected"]["items"][0]["raw_name"] == "허쉬쿠키앤크림"
    assert annotation["expected"]["totals"]["payment_amount"] == 24090.0


def test_build_dataset_manifest_summarizes_annotations() -> None:
    manifest = build_dataset_manifest(
        dataset_name="jevi-silver-v0",
        input_dir=Path(r"C:\receipts"),
        annotations=[
            {
                "image": {"file_name": "img2.jpg", "source_path": r"C:\receipts\img2.jpg"},
                "expected": {"items": [{"raw_name": "a"}], "review_required": False},
            },
            {
                "image": {"file_name": "img3.jpg", "source_path": r"C:\receipts\img3.jpg"},
                "expected": {"items": [{"raw_name": "b"}, {"raw_name": "c"}], "review_required": True},
            },
        ],
    )

    assert manifest["dataset_name"] == "jevi-silver-v0"
    assert manifest["image_count"] == 2
    assert manifest["total_item_count"] == 3
    assert manifest["review_required_count"] == 1


def test_compute_item_name_f1_returns_precision_recall_and_f1() -> None:
    metrics = compute_item_name_f1(
        expected_items=[
            {"raw_name": "허쉬쿠키앤크림"},
            {"raw_name": "호가든캔330ML"},
        ],
        actual_items=[
            {"raw_name": "허쉬쿠키앤크림"},
            {"raw_name": "아몬드빼빼로"},
        ],
    )

    assert metrics["tp"] == 1
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.5


def test_compute_item_name_f1_matches_items_by_raw_or_normalized_name_without_double_penalty() -> None:
    metrics = compute_item_name_f1(
        expected_items=[
            {"raw_name": "*청양고추"},
            {"raw_name": "햇반200g"},
        ],
        actual_items=[
            {"raw_name": "*청양고추", "normalized_name": "고추"},
            {"raw_name": "햇반200g", "normalized_name": "햇반"},
        ],
    )

    assert metrics["tp"] == 2
    assert metrics["fp"] == 0
    assert metrics["fn"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0


def test_compute_item_name_f1_counts_duplicate_item_occurrences() -> None:
    metrics = compute_item_name_f1(
        expected_items=[
            {"raw_name": "속이편한 누룽지"},
            {"raw_name": "속이편한 누룽지"},
        ],
        actual_items=[
            {"raw_name": "속이편한 누룽지"},
        ],
    )

    assert metrics["tp"] == 1
    assert metrics["fp"] == 0
    assert metrics["fn"] == 1
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 0.5
    assert metrics["f1"] == 0.6667


def test_compare_silver_annotation_reports_core_regression_metrics() -> None:
    metrics = compare_silver_annotation(
        annotation={
            "expected": {
                "vendor_name": "GS25",
                "purchased_at": "2023-11-25",
                "items": [
                    {"raw_name": "허쉬쿠키앤크림"},
                    {"raw_name": "호가든캔330ML"},
                ],
                "totals": {"payment_amount": 5100.0},
            }
        },
        parsed={
            "vendor_name": "GS25",
            "purchased_at": "2023-11-25",
            "items": [
                {"raw_name": "허쉬쿠키앤크림"},
                {"raw_name": "아몬드빼빼로"},
            ],
            "totals": {"payment_amount": 5100.0},
        },
    )

    assert metrics["vendor_name_match"] is True
    assert metrics["purchased_at_match"] is True
    assert metrics["payment_amount_match"] is True
    assert metrics["item_name_f1"] == 0.5


def test_compare_silver_annotation_reports_quantity_amount_and_review_metrics() -> None:
    metrics = compare_silver_annotation(
        annotation={
            "expected": {
                "vendor_name": "GS25",
                "purchased_at": "2023-11-25",
                "items": [
                    {"raw_name": "양파", "quantity": 2.0, "amount": 3000.0},
                    {"raw_name": "대파", "quantity": 1.0, "amount": None},
                ],
                "totals": {"payment_amount": 3000.0},
                "review_required": False,
            }
        },
        parsed={
            "vendor_name": "GS25",
            "purchased_at": "2023-11-25",
            "items": [
                {"raw_name": "양파", "quantity": 2.0, "amount": 3000.0},
                {"raw_name": "대파", "quantity": 3.0, "amount": None},
            ],
            "totals": {"payment_amount": 3000.0},
            "review_required": True,
        },
    )

    assert metrics["quantity_match_rate"] == 0.5
    assert metrics["amount_match_rate"] == 1.0
    assert metrics["review_required_match"] is False


def test_compare_silver_annotation_treats_unmatched_name_as_quantity_and_amount_miss() -> None:
    metrics = compare_silver_annotation(
        annotation={
            "expected": {
                "items": [
                    {"raw_name": "양파", "quantity": 2.0, "amount": 3000.0},
                ],
                "review_required": False,
            }
        },
        parsed={
            "items": [
                {"raw_name": "감자", "quantity": 2.0, "amount": 3000.0},
            ],
            "review_required": False,
        },
    )

    assert metrics["item_name_f1"] == 0.0
    assert metrics["quantity_match_rate"] == 0.0
    assert metrics["amount_match_rate"] == 0.0


def test_compare_silver_annotation_ignores_predicted_items_matching_uncertain_items() -> None:
    metrics = compare_silver_annotation(
        annotation={
            "expected": {
                "items": [
                    {"raw_name": "칠성사이다 제로 500ml", "quantity": 2.0, "amount": 3560.0},
                    {"raw_name": "김치제육삼각", "quantity": 1.0, "amount": 1080.0},
                    {"raw_name": "참치마요 삼각", "quantity": 1.0, "amount": 1080.0},
                ],
                "uncertain_items": [
                    {"raw_name": "라아요 상각"},
                    {"raw_name": "스타벅스키라멜731n"},
                ],
                "review_required": True,
            }
        },
        parsed={
            "items": [
                {"raw_name": "칠성사이다 제로 500ml", "quantity": 2.0, "amount": 3560.0},
                {"raw_name": "김치제육삼각", "quantity": 1.0, "amount": 1080.0},
                {"raw_name": "라아요 상각", "quantity": 1.0, "amount": 1080.0},
                {"raw_name": "참치마요 삼각", "quantity": 1.0, "amount": 1080.0},
                {"raw_name": "스타벅스키라멜731n", "quantity": 1.0, "amount": 2380.0},
            ],
            "review_required": True,
        },
    )

    assert metrics["tp"] == 3
    assert metrics["fp"] == 0
    assert metrics["fn"] == 0
    assert metrics["item_name_f1"] == 1.0
    assert metrics["quantity_match_rate"] == 1.0
    assert metrics["amount_match_rate"] == 1.0


def test_compute_item_name_f1_treats_parenthetical_pack_count_as_same_item_name() -> None:
    metrics = compute_item_name_f1(
        expected_items=[
            {"raw_name": "속이편한 누룽지(5입)"},
            {"raw_name": "속이편한 누룽지(5입)"},
        ],
        actual_items=[
            {"raw_name": "속이편한 누룽지"},
            {"raw_name": "속이편한 누룽지"},
        ],
    )

    assert metrics["tp"] == 2
    assert metrics["fp"] == 0
    assert metrics["fn"] == 0
    assert metrics["precision"] == 1.0
    assert metrics["recall"] == 1.0
    assert metrics["f1"] == 1.0


def test_compute_item_name_f1_does_not_collapse_real_size_variants() -> None:
    metrics = compute_item_name_f1(
        expected_items=[
            {"raw_name": "코카콜라355ml"},
        ],
        actual_items=[
            {"raw_name": "코카콜라500ml"},
        ],
    )

    assert metrics["tp"] == 0
    assert metrics["fp"] == 1
    assert metrics["fn"] == 1
    assert metrics["precision"] == 0.0
    assert metrics["recall"] == 0.0
    assert metrics["f1"] == 0.0
