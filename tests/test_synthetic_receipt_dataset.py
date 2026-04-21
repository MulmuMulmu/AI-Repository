from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from ocr_qwen.synthetic_receipts import (
    SyntheticReceiptSpec,
    build_synthetic_annotation,
    build_synthetic_dataset_plan,
    build_synthetic_manifest,
    build_synthetic_sample_specs,
    render_synthetic_receipt,
)


def test_build_synthetic_sample_specs_creates_known_layouts() -> None:
    specs = build_synthetic_sample_specs()

    assert len(specs) >= 3
    assert {spec.layout_type for spec in specs} >= {
        "convenience_pos",
        "mart_column",
        "barcode_detail",
        "compact_single_line",
        "mixed_noise",
    }
    assert all(spec.vendor_name for spec in specs)
    assert all(spec.purchased_at for spec in specs)
    assert all(spec.items for spec in specs)


def test_build_synthetic_dataset_plan_hits_target_count_and_spreads_layouts() -> None:
    plan = build_synthetic_dataset_plan(target_count=300)

    assert sum(plan.values()) == 300
    assert plan == {
        "barcode_detail": 60,
        "compact_single_line": 30,
        "convenience_pos": 90,
        "mart_column": 90,
        "mixed_noise": 30,
    }


def test_build_synthetic_sample_specs_can_expand_to_requested_count() -> None:
    specs = build_synthetic_sample_specs(target_count=300)

    assert len(specs) == 300
    layout_counts: dict[str, int] = {}
    for spec in specs:
        layout_counts[spec.layout_type] = layout_counts.get(spec.layout_type, 0) + 1

    assert layout_counts == {
        "barcode_detail": 60,
        "compact_single_line": 30,
        "convenience_pos": 90,
        "mart_column": 90,
        "mixed_noise": 30,
    }


def test_convenience_pos_specs_include_hard_variants() -> None:
    specs = build_synthetic_sample_specs(target_count=300)

    convenience_specs = [spec for spec in specs if spec.layout_type == "convenience_pos"]
    variants = {getattr(spec, "variant", "default") for spec in convenience_specs}

    assert "default" in variants
    assert "header_noise" in variants
    assert "narrow_columns" in variants
    assert "split_rows" in variants


def test_render_synthetic_receipt_writes_image_and_annotation(tmp_path: Path) -> None:
    spec = SyntheticReceiptSpec(
        file_stem="gs25-sample",
        vendor_name="GS25",
        purchased_at="2023-11-24",
        layout_type="convenience_pos",
        items=[
            {"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "quantity": 1.0, "unit": "개", "amount": 1600.0},
            {"raw_name": "호가든캔330ml", "normalized_name": "호가든캔330ml", "quantity": 1.0, "unit": "캔", "amount": 3500.0},
        ],
        totals={"payment_amount": 5100.0, "total": 5100.0},
        noise_profile={"blur": "none", "contrast": "normal", "skew": "none", "crop": "none", "shadow": "none"},
    )

    image_path, annotation = render_synthetic_receipt(spec=spec, output_dir=tmp_path)

    assert image_path.exists()
    assert image_path.suffix.lower() == ".png"

    image = Image.open(image_path)
    assert image.width >= 700
    assert image.height >= 1200

    assert annotation["label_source"] == "synthetic-template-v1"
    assert annotation["expected"]["vendor_name"] == "GS25"
    assert annotation["expected"]["purchased_at"] == "2023-11-24"
    assert annotation["expected"]["items"][0]["raw_name"] == "허쉬쿠키앤크림"
    assert annotation["expected"]["totals"]["payment_amount"] == 5100.0
    assert annotation["metadata"]["layout_type"] == "convenience_pos"


def test_build_synthetic_annotation_uses_spec_values() -> None:
    spec = SyntheticReceiptSpec(
        file_stem="barcode-detail",
        vendor_name="7-ELEVEN",
        purchased_at="2020-06-09",
        layout_type="barcode_detail",
        items=[
            {"raw_name": "라라스윗 바닐라파인트474", "normalized_name": "라라스윗 바닐라파인트474", "quantity": 1.0, "unit": "개", "amount": 6900.0}
        ],
        totals={"payment_amount": 6900.0},
        noise_profile={"blur": "low", "contrast": "normal", "skew": "small", "crop": "none", "shadow": "none"},
    )

    annotation = build_synthetic_annotation(
        spec=spec,
        image_path=Path(r"C:\synthetic\barcode-detail.png"),
        dataset_name="receipt-synthetic-v1",
        generated_at="2026-04-18T00:00:00Z",
    )

    assert annotation["dataset_name"] == "receipt-synthetic-v1"
    assert annotation["image"]["file_name"] == "barcode-detail.png"
    assert annotation["expected"]["vendor_name"] == "7-ELEVEN"
    assert annotation["metadata"]["noise_profile"]["skew"] == "small"


def test_build_synthetic_annotation_includes_variant_metadata() -> None:
    spec = SyntheticReceiptSpec(
        file_stem="convenience-hard",
        vendor_name="GS25",
        purchased_at="2026-04-19",
        layout_type="convenience_pos",
        items=[
            {"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "quantity": 1.0, "unit": "개", "amount": 1600.0}
        ],
        totals={"payment_amount": 1600.0, "total": 1600.0},
        noise_profile={"blur": "low"},
        variant="header_noise",
    )

    annotation = build_synthetic_annotation(
        spec=spec,
        image_path=Path(r"C:\synthetic\convenience-hard.png"),
        dataset_name="receipt-synthetic-v1",
        generated_at="2026-04-19T00:00:00Z",
    )

    assert annotation["metadata"]["variant"] == "header_noise"


def test_build_synthetic_manifest_summarizes_generated_annotations(tmp_path: Path) -> None:
    annotations = [
        {
            "image": {"file_name": "a.png", "source_path": str(tmp_path / "a.png")},
            "expected": {"items": [{"raw_name": "x"}], "review_required": False},
            "metadata": {"layout_type": "convenience_pos"},
        },
        {
            "image": {"file_name": "b.png", "source_path": str(tmp_path / "b.png")},
            "expected": {"items": [{"raw_name": "y"}, {"raw_name": "z"}], "review_required": False},
            "metadata": {"layout_type": "barcode_detail"},
        },
    ]

    manifest = build_synthetic_manifest(
        dataset_name="receipt-synthetic-v1",
        output_dir=tmp_path,
        annotations=annotations,
    )

    assert manifest["dataset_name"] == "receipt-synthetic-v1"
    assert manifest["image_count"] == 2
    assert manifest["total_item_count"] == 3
    assert manifest["layout_counts"] == {
        "barcode_detail": 1,
        "convenience_pos": 1,
    }


def test_script_like_output_can_be_serialized(tmp_path: Path) -> None:
    spec = build_synthetic_sample_specs()[0]
    image_path, annotation = render_synthetic_receipt(spec=spec, output_dir=tmp_path)
    manifest = build_synthetic_manifest(
        dataset_name="receipt-synthetic-v1",
        output_dir=tmp_path,
        annotations=[annotation],
    )

    annotation_path = tmp_path / "annotations" / f"{spec.file_stem}.json"
    annotation_path.parent.mkdir(parents=True, exist_ok=True)
    annotation_path.write_text(json.dumps(annotation, ensure_ascii=False, indent=2), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    assert image_path.exists()
    assert annotation_path.exists()
    assert manifest_path.exists()
