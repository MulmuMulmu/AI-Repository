from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ocr_qwen.qwen import NoopQwenProvider, build_default_qwen_provider
from ocr_qwen.receipts import ReceiptParser
from ocr_qwen.services import PaddleOcrBackend, ReceiptParseService
from ocr_qwen.silver_dataset import compare_silver_annotation, safe_annotation_stem


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate current OCR outputs against a silver receipt dataset.")
    parser.add_argument("--manifest", required=True, help="Path to manifest.json")
    parser.add_argument("--use-qwen", action="store_true", help="Use the currently configured Qwen provider.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    annotations_dir = manifest_path.parent / "annotations"

    qwen_provider = build_default_qwen_provider() if args.use_qwen else NoopQwenProvider()
    service = ReceiptParseService(
        ocr_backend=PaddleOcrBackend(),
        parser=ReceiptParser(),
        qwen_provider=qwen_provider,
    )
    service.ocr_backend.warm_up()

    results = []
    for image_entry in manifest.get("images", []):
        file_name = image_entry.get("file_name")
        source_path = image_entry.get("source_path")
        if not file_name or not source_path:
            continue
        annotation_path = annotations_dir / f"{safe_annotation_stem(file_name)}.json"
        if not annotation_path.exists():
            print(f"[skip] missing annotation for {file_name}")
            continue

        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        parsed = service.parse({"receipt_image_url": source_path})
        metrics = compare_silver_annotation(annotation=annotation, parsed=parsed)
        metrics["file_name"] = file_name
        results.append(metrics)
        print(f"[eval] {file_name} -> item_f1={metrics['item_name_f1']}")

    summary = _summarize(results)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def _summarize(results: list[dict]) -> dict:
    if not results:
        return {
            "image_count": 0,
            "vendor_name_accuracy": 0.0,
            "purchased_at_accuracy": 0.0,
            "payment_amount_accuracy": 0.0,
            "item_name_f1_avg": 0.0,
        }

    image_count = len(results)
    return {
        "image_count": image_count,
        "vendor_name_accuracy": round(sum(1 for item in results if item["vendor_name_match"]) / image_count, 4),
        "purchased_at_accuracy": round(sum(1 for item in results if item["purchased_at_match"]) / image_count, 4),
        "payment_amount_accuracy": round(sum(1 for item in results if item["payment_amount_match"]) / image_count, 4),
        "item_name_f1_avg": round(sum(float(item["item_name_f1"]) for item in results) / image_count, 4),
    }


if __name__ == "__main__":
    main()
