from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import main
from ocr_qwen.qwen import NoopQwenProvider
from ocr_qwen.receipts import ReceiptParser
from ocr_qwen.rule_candidates import build_rule_candidate_report
from ocr_qwen.services import PaddleOcrBackend, ReceiptParseService
from ocr_qwen.silver_dataset import discover_receipt_images


def main_cli() -> None:
    parser = argparse.ArgumentParser(description="Mine alias/product mapping candidates from real receipt images.")
    parser.add_argument("--input-dir", required=True, help="Directory containing receipt images")
    parser.add_argument(
        "--output-json",
        required=True,
        help="Path to write candidate JSON report",
    )
    parser.add_argument(
        "--output-md",
        required=True,
        help="Path to write candidate Markdown summary",
    )
    args = parser.parse_args()

    input_dir = Path(args.input_dir).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()
    output_md = Path(args.output_md).expanduser().resolve()

    images = discover_receipt_images(input_dir)
    service = ReceiptParseService(
        ocr_backend=PaddleOcrBackend(),
        parser=ReceiptParser(),
        qwen_provider=NoopQwenProvider(),
    )
    service.ocr_backend.warm_up()

    parsed_receipts: list[dict[str, object]] = []
    for image_path in images:
        parsed = service.parse({"receipt_image_url": str(image_path)})
        parsed_receipts.append(
            {
                "file_name": image_path.name,
                "items": list(parsed.get("items", [])),
            }
        )
        print(f"[mine] {image_path.name} -> {len(parsed.get('items', []))} items")

    report = build_rule_candidate_report(parsed_receipts, main._match_product_to_ingredient)
    report["input_dir"] = str(input_dir)
    report["images"] = [path.name for path in images]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(render_markdown_report(report), encoding="utf-8")

    print(f"[done] json={output_json}")
    print(f"[done] md={output_md}")


def render_markdown_report(report: dict[str, object]) -> str:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    alias_candidates = report.get("alias_candidates", []) if isinstance(report, dict) else []
    unmapped_products = report.get("unmapped_products", []) if isinstance(report, dict) else []
    weak_match_products = report.get("weak_match_products", []) if isinstance(report, dict) else []
    false_positive_item_candidates = report.get("false_positive_item_candidates", []) if isinstance(report, dict) else []

    lines = [
        "# Receipt Rule Candidate Report",
        "",
        f"- input_dir: `{report.get('input_dir', '')}`",
        f"- receipt_count: `{summary.get('receipt_count', 0)}`",
        f"- item_count: `{summary.get('item_count', 0)}`",
        f"- alias_candidate_count: `{summary.get('alias_candidate_count', 0)}`",
        f"- unmapped_product_count: `{summary.get('unmapped_product_count', 0)}`",
        f"- weak_match_product_count: `{summary.get('weak_match_product_count', 0)}`",
        f"- false_positive_item_candidate_count: `{summary.get('false_positive_item_candidate_count', 0)}`",
        "",
        "## Alias Candidates",
        "",
    ]
    lines.extend(_render_alias_section(alias_candidates))
    lines.extend(["", "## Unmapped Products", ""])
    lines.extend(_render_product_section(unmapped_products, include_match_fields=False))
    lines.extend(["", "## False Positive Item Candidates", ""])
    lines.extend(_render_product_section(false_positive_item_candidates, include_match_fields=False))
    lines.extend(["", "## Weak Match Products", ""])
    lines.extend(_render_product_section(weak_match_products, include_match_fields=True))
    return "\n".join(lines).strip() + "\n"


def _render_alias_section(entries: object) -> list[str]:
    rows = entries if isinstance(entries, list) else []
    if not rows:
        return ["- none"]
    lines: list[str] = []
    for entry in rows[:30]:
        lines.append(
            f"- `{entry['raw_name']}` -> `{entry['normalized_name']}` "
            f"(count={entry['count']}, avg_conf={entry['avg_confidence']}, files={', '.join(entry['sample_files'])})"
        )
    return lines


def _render_product_section(entries: object, *, include_match_fields: bool) -> list[str]:
    rows = entries if isinstance(entries, list) else []
    if not rows:
        return ["- none"]
    lines: list[str] = []
    for entry in rows[:30]:
        suffix = ""
        if include_match_fields:
            suffix = (
                f", ingredient={entry['ingredient_name']}, "
                f"source={entry['mapping_source']}, similarity={entry['similarity']}"
            )
        lines.append(
            f"- `{entry['product_name']}` (count={entry['count']}, avg_conf={entry['avg_confidence']}, "
            f"files={', '.join(entry['sample_files'])}{suffix})"
        )
    return lines


if __name__ == "__main__":
    main_cli()
