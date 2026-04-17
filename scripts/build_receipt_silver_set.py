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
from ocr_qwen.silver_dataset import (
    build_dataset_manifest,
    build_silver_annotation,
    discover_receipt_images,
    safe_annotation_stem,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a silver receipt dataset from current OCR outputs.")
    parser.add_argument("--input-dir", required=True, help="Directory containing receipt images.")
    parser.add_argument("--output-dir", required=True, help="Directory to write silver-set annotations.")
    parser.add_argument("--dataset-name", default="receipt-silver-v0", help="Dataset name to store in annotations.")
    parser.add_argument("--use-qwen", action="store_true", help="Use the currently configured Qwen provider.")
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_dir = Path(args.output_dir).expanduser().resolve()
    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)

    qwen_provider = build_default_qwen_provider() if args.use_qwen else NoopQwenProvider()
    service = ReceiptParseService(
        ocr_backend=PaddleOcrBackend(),
        parser=ReceiptParser(),
        qwen_provider=qwen_provider,
    )
    service.ocr_backend.warm_up()

    annotations: list[dict] = []
    failures: list[dict[str, str]] = []

    for image_path in discover_receipt_images(input_dir):
        try:
            parsed = service.parse({"receipt_image_url": str(image_path)})
            annotation = build_silver_annotation(
                image_path=image_path,
                parsed=parsed,
                dataset_name=args.dataset_name,
            )
            annotation_path = annotations_dir / f"{safe_annotation_stem(image_path)}.json"
            annotation_path.write_text(
                json.dumps(annotation, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            annotations.append(annotation)
            print(f"[ok] {image_path.name} -> {annotation_path.name}")
        except Exception as exc:  # pragma: no cover - operational path
            failures.append({"file_name": image_path.name, "error": str(exc)})
            print(f"[fail] {image_path.name}: {exc}")

    manifest = build_dataset_manifest(
        dataset_name=args.dataset_name,
        input_dir=input_dir,
        annotations=annotations,
    )
    manifest["failures"] = failures
    manifest["use_qwen"] = args.use_qwen

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
