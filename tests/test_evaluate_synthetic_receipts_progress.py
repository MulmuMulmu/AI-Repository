from __future__ import annotations

import json
from pathlib import Path

from scripts.evaluate_synthetic_receipts import write_partial_report


def test_write_partial_report_persists_summary_and_progress(tmp_path: Path) -> None:
    report_path = tmp_path / "partial.json"
    write_partial_report(
        report_path=report_path,
        dataset_name="receipt-synthetic-v1",
        manifest_path=Path(r"C:\dataset\manifest.json"),
        results=[
            {
                "file_name": "a.png",
                "layout_type": "convenience_pos",
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
            }
        ],
        failures=[],
        processed_count=1,
        total_count=300,
        use_qwen=False,
    )

    saved = json.loads(report_path.read_text(encoding="utf-8"))
    assert saved["dataset_name"] == "receipt-synthetic-v1"
    assert saved["progress"]["processed_count"] == 1
    assert saved["progress"]["total_count"] == 300
    assert saved["summary"]["image_count"] == 1
    assert saved["summary"]["item_name_f1_avg"] == 1.0
