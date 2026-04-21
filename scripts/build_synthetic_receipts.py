from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ocr_qwen.synthetic_receipts import (
    DEFAULT_DATASET_NAME,
    build_synthetic_manifest,
    build_synthetic_sample_specs,
    render_synthetic_receipt,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Build synthetic receipt images and annotations.")
    parser.add_argument(
        "--output-dir",
        default=str(REPO_ROOT / "data" / "receipt_synthetic" / DEFAULT_DATASET_NAME),
        help="Directory to write generated images, annotations, and manifest.",
    )
    parser.add_argument(
        "--target-count",
        type=int,
        default=300,
        help="Number of synthetic receipts to generate.",
    )
    parser.add_argument(
        "--dataset-name",
        default=DEFAULT_DATASET_NAME,
        help="Synthetic dataset name.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser().resolve()
    annotations_dir = output_dir / "annotations"
    annotations_dir.mkdir(parents=True, exist_ok=True)

    annotations: list[dict] = []
    for spec in build_synthetic_sample_specs(target_count=args.target_count):
        image_path, annotation = render_synthetic_receipt(
            spec=spec,
            output_dir=output_dir,
            dataset_name=args.dataset_name,
        )
        annotation_path = annotations_dir / f"{spec.file_stem}.json"
        annotation_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
        annotations.append(annotation)
        print(f"[ok] {image_path.name} -> {annotation_path.name}")

    manifest = build_synthetic_manifest(
        dataset_name=args.dataset_name,
        output_dir=output_dir,
        annotations=annotations,
    )
    manifest["target_count"] = args.target_count
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[done] manifest -> {manifest_path}")


if __name__ == "__main__":
    main()
