from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ocr_qwen.qwen import NoopQwenProvider, build_default_qwen_provider
from ocr_qwen.receipts import ReceiptParser
from ocr_qwen.services import PaddleOcrBackend, ReceiptParseService
from ocr_qwen.silver_dataset import safe_annotation_stem
from ocr_qwen.synthetic_dataset import compare_synthetic_annotation, summarize_synthetic_results


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate OCR outputs against a synthetic receipt dataset.")
    parser.add_argument("--manifest", required=True, help="Path to synthetic manifest.json")
    parser.add_argument("--use-qwen", action="store_true", help="Use the currently configured Qwen provider.")
    parser.add_argument("--limit", type=int, default=0, help="Optional limit for number of images to evaluate.")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).expanduser().resolve()
    dataset_dir = manifest_path.parent
    annotations_dir = dataset_dir / "annotations"
    report_dir = dataset_dir / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    suffix = "with-qwen" if args.use_qwen else "ocr-only"
    partial_json_path = report_dir / f"synthetic-eval-{suffix}.partial.json"
    partial_md_path = report_dir / f"synthetic-eval-{suffix}.partial.md"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    qwen_provider = build_default_qwen_provider() if args.use_qwen else NoopQwenProvider()
    service = ReceiptParseService(
        ocr_backend=PaddleOcrBackend(),
        parser=ReceiptParser(),
        qwen_provider=qwen_provider,
    )
    service.ocr_backend.warm_up()

    image_entries = list(manifest.get("images", []))
    if args.limit > 0:
        image_entries = image_entries[: args.limit]

    results: list[dict] = []
    failures: list[dict[str, str]] = []
    layout_results: dict[str, list[dict]] = {}

    started_at = time.perf_counter()
    for index, image_entry in enumerate(image_entries, start=1):
        file_name = image_entry.get("file_name")
        source_path = image_entry.get("source_path")
        if not file_name or not source_path:
            continue

        annotation_path = annotations_dir / f"{safe_annotation_stem(file_name)}.json"
        if not annotation_path.exists():
            failures.append({"file_name": str(file_name), "error": "missing_annotation"})
            write_partial_report(
                report_path=partial_json_path,
                dataset_name=str(manifest.get("dataset_name")),
                manifest_path=manifest_path,
                results=results,
                failures=failures,
                processed_count=index,
                total_count=len(image_entries),
                use_qwen=args.use_qwen,
            )
            continue

        annotation = json.loads(annotation_path.read_text(encoding="utf-8"))
        sample_started_at = time.perf_counter()
        try:
            parsed = service.parse({"receipt_image_url": source_path})
        except Exception as exc:  # pragma: no cover - operational path
            failures.append({"file_name": str(file_name), "error": str(exc)})
            print(f"[fail {index}/{len(image_entries)}] {file_name}: {exc}", flush=True)
            write_partial_report(
                report_path=partial_json_path,
                dataset_name=str(manifest.get("dataset_name")),
                manifest_path=manifest_path,
                results=results,
                failures=failures,
                processed_count=index,
                total_count=len(image_entries),
                use_qwen=args.use_qwen,
            )
            continue
        processing_seconds = time.perf_counter() - sample_started_at
        metrics = compare_synthetic_annotation(
            annotation=annotation,
            parsed=parsed,
            processing_seconds=processing_seconds,
        )
        metrics["file_name"] = file_name
        metrics["layout_type"] = annotation.get("metadata", {}).get("layout_type")
        results.append(metrics)
        layout_type = str(metrics["layout_type"])
        layout_results.setdefault(layout_type, []).append(metrics)
        print(
            f"[eval {index}/{len(image_entries)}] {file_name} "
            f"item_f1={metrics['item_name_f1']:.4f} qty={metrics['quantity_match_rate']:.4f} "
            f"amt={metrics['amount_match_rate']:.4f} sec={metrics['processing_seconds']:.2f}",
            flush=True,
        )
        if index == 1 or index % 10 == 0 or index == len(image_entries):
            write_partial_report(
                report_path=partial_json_path,
                dataset_name=str(manifest.get("dataset_name")),
                manifest_path=manifest_path,
                results=results,
                failures=failures,
                processed_count=index,
                total_count=len(image_entries),
                use_qwen=args.use_qwen,
            )
            partial_report = json.loads(partial_json_path.read_text(encoding="utf-8"))
            partial_md_path.write_text(_render_markdown_report(partial_report), encoding="utf-8")

    total_elapsed = time.perf_counter() - started_at
    summary = summarize_synthetic_results(results)
    summary["total_elapsed_seconds"] = round(total_elapsed, 4)
    summary["success_count"] = len(results)
    summary["failure_count"] = len(failures)
    summary["use_qwen"] = args.use_qwen
    summary["limit"] = args.limit

    report = {
        "dataset_name": manifest.get("dataset_name"),
        "manifest_path": str(manifest_path),
        "summary": summary,
        "layout_breakdown": {
            layout_type: summarize_synthetic_results(layout_rows)
            for layout_type, layout_rows in sorted(layout_results.items())
        },
        "failures": failures,
        "results": results,
    }

    report_json_path = report_dir / f"synthetic-eval-{suffix}.json"
    report_md_path = report_dir / f"synthetic-eval-{suffix}.md"
    report_json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report_md_path.write_text(_render_markdown_report(report), encoding="utf-8")

    print(f"[done] json -> {report_json_path}", flush=True)
    print(f"[done] md   -> {report_md_path}", flush=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


def write_partial_report(
    *,
    report_path: Path,
    dataset_name: str,
    manifest_path: Path,
    results: list[dict],
    failures: list[dict[str, str]],
    processed_count: int,
    total_count: int,
    use_qwen: bool,
) -> None:
    layout_results: dict[str, list[dict]] = {}
    for result in results:
        layout_results.setdefault(str(result.get("layout_type")), []).append(result)

    summary = summarize_synthetic_results(results)
    report = {
        "dataset_name": dataset_name,
        "manifest_path": str(manifest_path),
        "progress": {
            "processed_count": processed_count,
            "total_count": total_count,
            "remaining_count": max(total_count - processed_count, 0),
        },
        "summary": {
            **summary,
            "success_count": len(results),
            "failure_count": len(failures),
            "use_qwen": use_qwen,
        },
        "layout_breakdown": {
            layout_type: summarize_synthetic_results(layout_rows)
            for layout_type, layout_rows in sorted(layout_results.items())
        },
        "failures": failures,
        "results": results,
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")


def _render_markdown_report(report: dict) -> str:
    summary = report["summary"]
    progress = report.get("progress")
    lines = [
        "# Synthetic Receipt OCR Evaluation",
        "",
        f"- dataset: `{report.get('dataset_name')}`",
        f"- manifest: `{report.get('manifest_path')}`",
        f"- success_count: `{summary['success_count']}`",
        f"- failure_count: `{summary['failure_count']}`",
        f"- use_qwen: `{summary['use_qwen']}`",
        "",
    ]
    if isinstance(progress, dict):
        lines.extend(
            [
                "## Progress",
                "",
                f"- processed_count: `{progress['processed_count']}`",
                f"- total_count: `{progress['total_count']}`",
                f"- remaining_count: `{progress['remaining_count']}`",
                "",
            ]
        )
    lines.extend(
        [
        "## Summary",
        "",
        "| metric | value |",
        "|---|---:|",
        f"| image_count | {summary['image_count']} |",
        f"| vendor_name_accuracy | {summary['vendor_name_accuracy']} |",
        f"| purchased_at_accuracy | {summary['purchased_at_accuracy']} |",
        f"| payment_amount_accuracy | {summary['payment_amount_accuracy']} |",
        f"| item_name_precision_avg | {summary['item_name_precision_avg']} |",
        f"| item_name_recall_avg | {summary['item_name_recall_avg']} |",
        f"| item_name_f1_avg | {summary['item_name_f1_avg']} |",
        f"| quantity_match_rate_avg | {summary['quantity_match_rate_avg']} |",
        f"| amount_match_rate_avg | {summary['amount_match_rate_avg']} |",
        f"| review_required_rate | {summary['review_required_rate']} |",
        f"| avg_processing_seconds | {summary['avg_processing_seconds']} |",
        f"| total_elapsed_seconds | {summary.get('total_elapsed_seconds', 0.0)} |",
        "",
        "## Layout Breakdown",
        "",
    ]
    )

    for layout_type, layout_summary in report.get("layout_breakdown", {}).items():
        lines.extend(
            [
                f"### {layout_type}",
                "",
                "| metric | value |",
                "|---|---:|",
                f"| image_count | {layout_summary['image_count']} |",
                f"| vendor_name_accuracy | {layout_summary['vendor_name_accuracy']} |",
                f"| purchased_at_accuracy | {layout_summary['purchased_at_accuracy']} |",
                f"| payment_amount_accuracy | {layout_summary['payment_amount_accuracy']} |",
                f"| item_name_f1_avg | {layout_summary['item_name_f1_avg']} |",
                f"| quantity_match_rate_avg | {layout_summary['quantity_match_rate_avg']} |",
                f"| amount_match_rate_avg | {layout_summary['amount_match_rate_avg']} |",
                f"| review_required_rate | {layout_summary['review_required_rate']} |",
                f"| avg_processing_seconds | {layout_summary['avg_processing_seconds']} |",
                "",
            ]
        )

    if report.get("failures"):
        lines.extend(["## Failures", ""])
        for failure in report["failures"]:
            lines.append(f"- `{failure.get('file_name')}`: {failure.get('error')}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    main()
