from __future__ import annotations

from ocr_qwen.synthetic_dataset import compare_synthetic_annotation, summarize_synthetic_results


def test_compare_synthetic_annotation_reports_name_quantity_amount_metrics() -> None:
    metrics = compare_synthetic_annotation(
        annotation={
            "expected": {
                "vendor_name": "GS25",
                "purchased_at": "2023-11-24",
                "items": [
                    {"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "quantity": 1.0, "amount": 1600.0},
                    {"raw_name": "호가든캔330ml", "normalized_name": "호가든캔330ml", "quantity": 2.0, "amount": 7000.0},
                ],
                "totals": {"payment_amount": 8600.0},
            }
        },
        parsed={
            "vendor_name": "GS25",
            "purchased_at": "2023-11-24",
            "items": [
                {"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "quantity": 1.0, "amount": 1600.0},
                {"raw_name": "호가든캔330ml", "normalized_name": "호가든캔330ml", "quantity": 1.0, "amount": 7000.0},
                {"raw_name": "아몬드초코볼", "normalized_name": "아몬드초코볼", "quantity": 1.0, "amount": 2000.0},
            ],
            "totals": {"payment_amount": 8600.0},
            "review_required": True,
        },
        processing_seconds=1.23,
    )

    assert metrics["vendor_name_match"] is True
    assert metrics["purchased_at_match"] is True
    assert metrics["payment_amount_match"] is True
    assert metrics["item_name_precision"] == 0.6667
    assert metrics["item_name_recall"] == 1.0
    assert metrics["item_name_f1"] == 0.8
    assert metrics["matched_item_count"] == 2
    assert metrics["quantity_match_rate"] == 0.5
    assert metrics["amount_match_rate"] == 1.0
    assert metrics["review_required"] is True
    assert metrics["processing_seconds"] == 1.23


def test_summarize_synthetic_results_aggregates_core_accuracy() -> None:
    summary = summarize_synthetic_results(
        [
            {
                "vendor_name_match": True,
                "purchased_at_match": True,
                "payment_amount_match": True,
                "item_name_precision": 1.0,
                "item_name_recall": 1.0,
                "item_name_f1": 1.0,
                "quantity_match_rate": 1.0,
                "amount_match_rate": 1.0,
                "review_required": False,
                "processing_seconds": 2.0,
            },
            {
                "vendor_name_match": False,
                "purchased_at_match": True,
                "payment_amount_match": False,
                "item_name_precision": 0.5,
                "item_name_recall": 0.5,
                "item_name_f1": 0.5,
                "quantity_match_rate": 0.0,
                "amount_match_rate": 0.5,
                "review_required": True,
                "processing_seconds": 4.0,
            },
        ]
    )

    assert summary["image_count"] == 2
    assert summary["vendor_name_accuracy"] == 0.5
    assert summary["purchased_at_accuracy"] == 1.0
    assert summary["payment_amount_accuracy"] == 0.5
    assert summary["item_name_f1_avg"] == 0.75
    assert summary["quantity_match_rate_avg"] == 0.5
    assert summary["amount_match_rate_avg"] == 0.75
    assert summary["review_required_rate"] == 0.5
    assert summary["avg_processing_seconds"] == 3.0
