from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from inspect import signature
import os
from pathlib import Path
import re
import tempfile
from uuid import uuid4

import httpx
import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from .expiry import ExpiryEvaluator, InventoryItem
from .preprocess import ReceiptPreprocessor, preprocess_receipt
from .qwen import LocalTransformersQwenProvider, NoopQwenProvider
from .receipts import CATEGORY_STORAGE, OcrLine, ReceiptParser
from .recommendations import (
    InventorySnapshot,
    RecipeEngine,
)

VALID_CATEGORIES = {
    "vegetable",
    "fruit",
    "dairy",
    "meat",
    "seafood",
    "egg",
    "tofu_bean",
    "sauce",
    "beverage",
    "frozen",
    "other",
}
VALID_STORAGE_TYPES = {"room", "refrigerated", "frozen"}
RECEIPT_ENGINE_VERSION = "receipt-engine-v2"
OCR_ROW_MERGE_TOLERANCE = 18.0
DATE_FALLBACK_TOP_RATIO = 0.22
DATE_FALLBACK_MIN_HEIGHT = 140
DATE_FALLBACK_MAX_HEIGHT = 320
DATE_FALLBACK_UPSCALE = 3
ITEM_STRIP_FALLBACK_TOP_RATIO = 0.38
GIFT_ITEM_STRIP_TOP_RATIO = 0.26
GIFT_ITEM_STRIP_BOTTOM_RATIO = 0.62
QWEN_HEADER_MAX_MERGED_ROWS = 2
QWEN_HEADER_MAX_RAW_TOKENS = 4
QWEN_HEADER_MAX_TOP_STRIP_ROWS = 4
QWEN_ITEM_MAX_REVIEW_ITEMS = 4
DISCOUNT_KEYWORDS = ("할인", "에누리", "포인트", "S-POINT", "쿠폰", "행사")


@dataclass
class OcrExtraction:
    lines: list[OcrLine]
    raw_tokens: list[dict[str, object]] = field(default_factory=list)
    quality_score: float = 1.0
    rotation_applied: int = 0
    perspective_corrected: bool = False
    low_quality_reasons: list[str] = field(default_factory=list)
    preprocessed_path: str | None = None


class PaddleOcrBackend:
    def __init__(self, preprocessor: ReceiptPreprocessor | None = None) -> None:
        self._engine = None
        self.preprocessor = preprocessor or ReceiptPreprocessor()

    def warm_up(self) -> None:
        if self._engine is not None:
            return
        from paddleocr import PaddleOCR

        self._engine = PaddleOCR(**self._build_paddle_ocr_kwargs(PaddleOCR))

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        image_path = self._resolve_source(source, source_type=source_type)
        preprocess_result = preprocess_receipt(image_path, persist=True)
        ocr_input_path = preprocess_result.output_path or str(image_path)

        if self._engine is None:
            self.warm_up()

        try:
            raw_result = self._run_paddle_ocr(ocr_input_path)
        finally:
            if preprocess_result.output_path:
                Path(preprocess_result.output_path).unlink(missing_ok=True)
        lines, raw_tokens = self._extract_ocr_lines(raw_result)

        ordered_lines = sorted(lines, key=self._line_sort_key)
        ordered_lines = [replace(line, page_order=index) for index, line in enumerate(ordered_lines)]

        return OcrExtraction(
            lines=ordered_lines,
            raw_tokens=raw_tokens,
            quality_score=preprocess_result.quality_score,
            rotation_applied=preprocess_result.rotation_applied,
            perspective_corrected=preprocess_result.perspective_corrected,
            low_quality_reasons=list(preprocess_result.low_quality_reasons),
            preprocessed_path=preprocess_result.output_path,
        )

    def _build_paddle_ocr_kwargs(self, paddle_ocr_cls: type) -> dict[str, object]:
        params = signature(paddle_ocr_cls.__init__).parameters
        kwargs: dict[str, object] = {"lang": "korean"}

        if "use_angle_cls" in params:
            kwargs["use_angle_cls"] = True
        elif "use_textline_orientation" in params:
            kwargs["use_textline_orientation"] = True

        if "use_doc_orientation_classify" in params:
            kwargs["use_doc_orientation_classify"] = False
        if "use_doc_unwarping" in params:
            kwargs["use_doc_unwarping"] = False
        if "device" in params:
            kwargs["device"] = "cpu"
        if "show_log" in params:
            kwargs["show_log"] = False

        return kwargs

    def _run_paddle_ocr(self, image_path: str) -> object:
        if hasattr(self._engine, "predict"):
            return self._engine.predict(image_path)
        ocr_params = signature(self._engine.ocr).parameters
        kwargs: dict[str, object] = {}
        if "cls" in ocr_params:
            kwargs["cls"] = True
        return self._engine.ocr(image_path, **kwargs)

    def _extract_ocr_lines(self, raw_result: object) -> tuple[list[OcrLine], list[dict[str, object]]]:
        lines: list[OcrLine] = []
        raw_tokens: list[dict[str, object]] = []
        for block in raw_result or []:
            if self._looks_like_current_ocr_result(block):
                current_lines, current_tokens = self._extract_current_ocr_result_lines(block)
                lines.extend(current_lines)
                raw_tokens.extend(current_tokens)
                continue
            for line in block or []:
                bbox_points = tuple((float(point[0]), float(point[1])) for point in line[0])
                text = str(line[1][0]).strip()
                confidence = float(line[1][1])
                if text:
                    raw_tokens.append(
                        {
                            "text": text,
                            "confidence": confidence,
                            "bbox": bbox_points,
                            "source": "legacy_line",
                        }
                    )
                    lines.append(
                        OcrLine(
                            text=text,
                            confidence=confidence,
                            line_id=len(lines),
                            bbox=bbox_points,
                        )
                    )
        return lines, raw_tokens

    def _looks_like_current_ocr_result(self, block: object) -> bool:
        return isinstance(block, dict) and "dt_polys" in block and "rec_texts" in block

    def _extract_current_ocr_result_lines(self, block: dict) -> tuple[list[OcrLine], list[dict[str, object]]]:
        tokens: list[OcrLine] = []
        raw_tokens: list[dict[str, object]] = []
        dt_polys = block.get("dt_polys", [])
        rec_boxes = block.get("rec_boxes", [])
        rec_texts = block.get("rec_texts", [])
        rec_scores = block.get("rec_scores", [])
        boxes = dt_polys if dt_polys else rec_boxes
        for index, (poly, text, score) in enumerate(zip(boxes, rec_texts, rec_scores)):
            stripped_text = str(text).strip()
            if not stripped_text:
                continue
            poly_arr = np.asarray(poly)
            if poly_arr.shape == (4,):
                x1, y1, x2, y2 = [float(value) for value in poly_arr.flat]
                bbox_points = ((x1, y1), (x2, y1), (x2, y2), (x1, y2))
            else:
                bbox_points = tuple((float(point[0]), float(point[1])) for point in poly_arr)
            tokens.append(
                OcrLine(
                    text=stripped_text,
                    confidence=float(score),
                    line_id=index,
                    bbox=bbox_points,
                )
            )
            raw_tokens.append(
                {
                    "text": stripped_text,
                    "confidence": float(score),
                    "bbox": bbox_points,
                    "source": "ocr_token",
                    "token_index": index,
                }
            )
        return self._merge_ocr_tokens_into_rows(tokens), raw_tokens

    def _merge_ocr_tokens_into_rows(self, tokens: list[OcrLine]) -> list[OcrLine]:
        if not tokens:
            return []

        sorted_tokens = sorted(tokens, key=self._line_sort_key)
        row_groups: list[list[OcrLine]] = []
        for token in sorted_tokens:
            if not row_groups:
                row_groups.append([token])
                continue
            previous_center = row_groups[-1][0].center
            current_center = token.center
            if previous_center and current_center and abs(current_center[1] - previous_center[1]) <= OCR_ROW_MERGE_TOLERANCE:
                row_groups[-1].append(token)
            else:
                row_groups.append([token])

        merged_lines: list[OcrLine] = []
        for row_index, group in enumerate(row_groups):
            ordered_group = sorted(group, key=lambda line: (line.center[0] if line.center else 0.0))
            merged_text = " ".join(token.text for token in ordered_group).strip()
            merged_confidence = sum(token.confidence for token in ordered_group) / len(ordered_group)
            merged_bbox = self._merge_bbox_points([token.bbox for token in ordered_group if token.bbox])
            merged_lines.append(
                OcrLine(
                    text=merged_text,
                    confidence=merged_confidence,
                    line_id=row_index,
                    bbox=merged_bbox,
                )
            )
        return merged_lines

    def _merge_bbox_points(
        self,
        bboxes: list[tuple[tuple[float, float], ...]],
    ) -> tuple[tuple[float, float], ...] | None:
        if not bboxes:
            return None
        xs = [point[0] for bbox in bboxes for point in bbox]
        ys = [point[1] for bbox in bboxes for point in bbox]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return (
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            (min_x, max_y),
        )

    def _line_sort_key(self, line: OcrLine) -> tuple[float, float, int]:
        if line.center is not None:
            return (round(line.center[1], 3), round(line.center[0], 3), line.line_id or 0)
        return (float(line.line_id or 0), 0.0, line.line_id or 0)

    def _resolve_source(self, source: str, source_type: str = "receipt_image_url") -> Path:
        if source.startswith(("http://", "https://")):
            return self._download_to_tempfile(source)

        if source_type == "s3_key" or source.startswith("s3://"):
            base_url = os.environ.get("S3_PUBLIC_BASE_URL")
            if not base_url:
                raise ValueError("S3_PUBLIC_BASE_URL is required to resolve s3_key inputs.")
            key = source.split("/", 3)[-1] if source.startswith("s3://") else source.lstrip("/")
            return self._download_to_tempfile(f"{base_url.rstrip('/')}/{key}")

        path = Path(source).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"Receipt image not found: {source}")
        return path

    def _download_to_tempfile(self, url: str) -> Path:
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        suffix = Path(url).suffix or ".png"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(response.content)
            return Path(handle.name)


class ReceiptParseService:
    def __init__(
        self,
        ocr_backend: object | None = None,
        parser: ReceiptParser | None = None,
        qwen_provider: object | None = None,
    ) -> None:
        self.ocr_backend = ocr_backend or PaddleOcrBackend()
        self.parser = parser or ReceiptParser()
        self.qwen_provider = qwen_provider

    def parse(self, payload: dict) -> dict:
        source_type = "receipt_image_url" if payload.get("receipt_image_url") else "s3_key"
        source = payload.get("receipt_image_url") or payload.get("s3_key")
        if not source:
            raise ValueError("Either receipt_image_url or s3_key must be provided.")

        extraction = self._normalize_extraction(self.ocr_backend.extract(source, source_type=source_type))
        trace_id = f"receipt-{uuid4().hex[:12]}"
        fallback_result = self.parser.parse_lines(extraction.lines)
        parsed = self._build_rule_parse_response(
            result=fallback_result,
            extraction=extraction,
            trace_id=trace_id,
        )
        top_strip_extraction = self._extract_top_strip_extraction(source=source, source_type=source_type)
        self._apply_top_strip_header_fallback(parsed, top_strip_extraction=top_strip_extraction)
        item_strip_extraction = None
        item_strip_gap = self._detect_item_strip_gap(parsed, extraction=extraction, source_type=source_type)
        if item_strip_gap is not None:
            item_strip_extraction = self._extract_item_strip_extraction(
                source=source,
                source_type=source_type,
                parsed=parsed,
                extraction=extraction,
                gap=item_strip_gap,
            )
        self._apply_item_strip_fallback(parsed, item_strip_extraction=item_strip_extraction, gap=item_strip_gap)

        header_qwen_attempted = False
        header_qwen_used = False
        header_qwen_fallback_reason = "provider_missing"
        if self._supports_qwen_header_rescue() and self._should_request_qwen_header_rescue(parsed):
            if (
                isinstance(self.qwen_provider, LocalTransformersQwenProvider)
                and os.environ.get("ENABLE_SYNC_LOCAL_QWEN_HEADER_RESCUE", "0") != "1"
            ):
                header_qwen_fallback_reason = "disabled_sync_local_qwen_header"
            else:
                header_qwen_attempted = True
                header_payload = self._build_qwen_header_rescue_payload(
                    parsed=parsed,
                    extraction=extraction,
                    top_strip_extraction=top_strip_extraction,
                )
                try:
                    header_qwen_result = self._invoke_qwen_header_rescue(header_payload)
                except Exception:
                    header_qwen_fallback_reason = "provider_error"
                else:
                    if isinstance(header_qwen_result, dict):
                        header_qwen_used = self._apply_qwen_header_rescue(parsed, header_qwen_result)
                        header_qwen_fallback_reason = None if header_qwen_used else "invalid_response"
                    else:
                        header_qwen_fallback_reason = "empty_response"
        elif self.qwen_provider is not None and not isinstance(self.qwen_provider, NoopQwenProvider):
            header_qwen_fallback_reason = "not_needed"

        item_qwen_attempted = False
        item_qwen_used = False
        item_qwen_fallback_reason = "provider_missing"
        if self._supports_qwen_item_normalization():
            if (
                isinstance(self.qwen_provider, LocalTransformersQwenProvider)
                and os.environ.get("ENABLE_SYNC_LOCAL_QWEN_ITEM_NORMALIZATION", "0") != "1"
            ):
                item_qwen_fallback_reason = "disabled_sync_local_qwen"
            else:
                qwen_payload = self._build_qwen_item_normalization_payload(parsed=parsed, lines=extraction.lines)
                if qwen_payload["review_items"]:
                    item_qwen_attempted = True
                    try:
                        qwen_result = self._invoke_qwen_item_normalizer(qwen_payload)
                    except Exception:
                        item_qwen_fallback_reason = "provider_error"
                    else:
                        if isinstance(qwen_result, dict):
                            item_qwen_used = self._apply_qwen_item_normalization(parsed, qwen_result)
                            item_qwen_fallback_reason = None if item_qwen_used else "invalid_response"
                        else:
                            item_qwen_fallback_reason = "empty_response"
                else:
                    item_qwen_fallback_reason = "no_review_items"

        parsed["diagnostics"]["qwen_header_attempted"] = header_qwen_attempted
        parsed["diagnostics"]["qwen_header_used"] = header_qwen_used
        parsed["diagnostics"]["qwen_header_fallback_reason"] = header_qwen_fallback_reason
        parsed["diagnostics"]["qwen_item_attempted"] = item_qwen_attempted
        parsed["diagnostics"]["qwen_item_used"] = item_qwen_used
        parsed["diagnostics"]["qwen_item_fallback_reason"] = item_qwen_fallback_reason
        parsed["diagnostics"]["qwen_attempted"] = header_qwen_attempted or item_qwen_attempted
        parsed["diagnostics"]["qwen_used"] = header_qwen_used or item_qwen_used
        parsed["diagnostics"]["qwen_mode"] = self._resolve_qwen_mode(
            header_qwen_attempted=header_qwen_attempted,
            item_qwen_attempted=item_qwen_attempted,
        )
        parsed["diagnostics"]["qwen_fallback_reason"] = (
            None
            if (header_qwen_used or item_qwen_used)
            else header_qwen_fallback_reason if header_qwen_attempted else item_qwen_fallback_reason
        )
        self._finalize_parse_result(parsed, extraction.low_quality_reasons)
        return parsed

    def _apply_top_strip_header_fallback(self, parsed: dict, *, top_strip_extraction: OcrExtraction | None) -> None:
        diagnostics = parsed.setdefault("diagnostics", {})
        diagnostics["date_fallback_used"] = False
        diagnostics["vendor_fallback_used"] = False
        if top_strip_extraction is None:
            return

        if parsed.get("vendor_name") is None:
            vendor_name = self._extract_vendor_name_from_top_strip(top_strip_extraction=top_strip_extraction)
            if vendor_name is not None:
                parsed["vendor_name"] = vendor_name
                diagnostics["vendor_fallback_used"] = True
                diagnostics["vendor_fallback_source"] = "top_strip"

        if parsed.get("purchased_at") is not None:
            return

        purchased_at = self._extract_purchased_at_from_top_strip(top_strip_extraction=top_strip_extraction)
        if purchased_at is None:
            return
        parsed["purchased_at"] = purchased_at
        diagnostics["date_fallback_used"] = True
        diagnostics["date_fallback_source"] = "top_strip"
        parsed["review_reasons"] = [
            reason for reason in parsed.get("review_reasons", []) if reason != "missing_purchased_at"
        ]
        for item in parsed.get("items", []):
            if isinstance(item, dict):
                self._recalculate_review_state(item, purchased_at)

    def _extract_purchased_at_from_top_strip(self, *, top_strip_extraction: OcrExtraction | None) -> str | None:
        if top_strip_extraction is None:
            return None
        return self.parser._extract_purchased_at(top_strip_extraction.lines)

    def _extract_vendor_name_from_top_strip(self, *, top_strip_extraction: OcrExtraction | None) -> str | None:
        if top_strip_extraction is None:
            return None
        return self.parser._extract_vendor_name(top_strip_extraction.lines)

    def _extract_top_strip_extraction(self, *, source: str, source_type: str) -> OcrExtraction | None:
        if source_type != "receipt_image_url":
            return None

        image_path = Path(source).expanduser()
        if not image_path.exists():
            return None

        strip_path: str | None = None
        try:
            with Image.open(image_path) as image:
                strip = self._build_top_strip_date_image(image)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                    strip_path = handle.name
            strip.save(strip_path)

            return self._normalize_extraction(
                self.ocr_backend.extract(strip_path, source_type="receipt_image_url")
            )
        except Exception:
            return None
        finally:
            if strip_path:
                Path(strip_path).unlink(missing_ok=True)

    def _detect_item_strip_gap(
        self,
        parsed: dict,
        *,
        extraction: OcrExtraction,
        source_type: str,
    ) -> dict[str, object] | None:
        if source_type != "receipt_image_url":
            return None
        if extraction.quality_score > 0.65 and not extraction.low_quality_reasons:
            return None
        dense_receipt = len(parsed.get("items", [])) >= 8
        rows = self._iter_unconsumed_rows_after_item_header(parsed)
        for index in range(len(rows)):
            current_text = str(rows[index]["text"])
            if self._looks_like_item_strip_gift_tail_row(current_text):
                return {"kind": "gift_tail", "line_id": rows[index]["line_id"]}
            if index + 1 >= len(rows):
                continue
            next_text = str(rows[index + 1]["text"])
            if self._looks_like_item_strip_placeholder_row(current_text) and self._looks_like_item_strip_gap_row(next_text):
                if dense_receipt:
                    continue
                return {"kind": "placeholder_barcode", "line_id": rows[index]["line_id"]}
        return None

    def _iter_unconsumed_rows_after_item_header(self, parsed: dict) -> list[dict[str, object]]:
        diagnostics = parsed.get("diagnostics", {}) if isinstance(parsed, dict) else {}
        section_map = diagnostics.get("section_map", {})
        consumed_ids = {int(value) for value in diagnostics.get("consumed_line_ids", [])}
        item_header_line_id: int | None = None
        earliest_item_line_id: int | None = None
        for row in parsed.get("ocr_texts", []):
            if not isinstance(row, dict):
                continue
            line_id = row.get("line_id")
            text = self._clean_string(row.get("text"))
            if isinstance(line_id, int) and text and self.parser._looks_like_item_header(text):
                item_header_line_id = line_id
                break
        item_line_ids = [int(key) for key, section in section_map.items() if section == "items"]
        if item_line_ids:
            earliest_item_line_id = min(item_line_ids)
        rows: list[dict[str, object]] = []
        for row in parsed.get("ocr_texts", []):
            if not isinstance(row, dict):
                continue
            line_id = row.get("line_id")
            if not isinstance(line_id, int):
                continue
            if line_id in consumed_ids:
                continue
            text = self._clean_string(row.get("text"))
            if not text:
                continue
            if item_header_line_id is not None and line_id <= item_header_line_id:
                continue
            if item_header_line_id is None and earliest_item_line_id is not None and line_id < max(0, earliest_item_line_id - 2):
                continue
            section = section_map.get(str(line_id))
            if section in {"totals", "payment", "ignored"} and not self._looks_like_item_strip_gap_row(text):
                continue
            rows.append({"line_id": line_id, "text": text, "section": section})
        return rows

    def _looks_like_item_strip_placeholder_row(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if len(normalized) < 3 or len(normalized) > 14:
            return False
        if re.search(r"\d{8,}", normalized):
            return False
        if "," in normalized or "-" in normalized:
            return False
        hangul_count = sum("가" <= char <= "힣" for char in normalized)
        alpha_digit_count = sum(char.isascii() and char.isalnum() for char in normalized)
        return hangul_count <= 1 and alpha_digit_count >= 3

    def _looks_like_item_strip_gift_tail_row(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if "증정" not in normalized:
            return False
        if not normalized or not normalized[0].isdigit():
            return False
        return True

    def _looks_like_item_strip_following_item_row(self, text: str) -> bool:
        if not re.search(r"\d{1,3}(?:,\d{3})+", text):
            return False
        return any("가" <= char <= "힣" for char in text)

    def _looks_like_item_strip_gap_row(self, text: str) -> bool:
        normalized = re.sub(r"\s+", "", text)
        if re.search(r"\d{8,}", normalized):
            return True
        return bool(re.search(r"\d+\s+\d{1,3}(?:,\d{3})+", text))

    def _extract_item_strip_extraction(
        self,
        *,
        source: str,
        source_type: str,
        parsed: dict,
        extraction: OcrExtraction,
        gap: dict[str, object],
    ) -> OcrExtraction | None:
        if source_type != "receipt_image_url":
            return None

        image_path = Path(source).expanduser()
        if not image_path.exists():
            return None

        strip_path: str | None = None
        try:
            with Image.open(image_path) as image:
                strip = self._build_item_strip_image(image, parsed=parsed, extraction=extraction, gap=gap)
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
                    strip_path = handle.name
            strip.save(strip_path)

            return self._normalize_extraction(
                self.ocr_backend.extract(strip_path, source_type="receipt_image_url")
            )
        except Exception:
            return None
        finally:
            if strip_path:
                Path(strip_path).unlink(missing_ok=True)

    def _build_item_strip_image(
        self,
        image: Image.Image,
        *,
        parsed: dict,
        extraction: OcrExtraction,
        gap: dict[str, object],
    ) -> Image.Image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        width, height = normalized.size
        if str(gap.get("kind") or "") == "gift_tail":
            top = max(0, int(height * GIFT_ITEM_STRIP_TOP_RATIO))
            bottom = min(height, max(top + 1, int(height * GIFT_ITEM_STRIP_BOTTOM_RATIO)))
            return normalized.crop((0, top, width, bottom))
        bounds = self._compute_item_strip_bounds(parsed=parsed, extraction=extraction, image_height=height, gap=gap)
        if bounds is None:
            top = min(max(int(height * ITEM_STRIP_FALLBACK_TOP_RATIO), 0), max(height - 1, 0))
            return normalized.crop((0, top, width, height))
        top, bottom = bounds
        return normalized.crop((0, top, width, bottom))

    def _compute_item_strip_bounds(
        self,
        *,
        parsed: dict,
        extraction: OcrExtraction,
        image_height: int,
        gap: dict[str, object],
    ) -> tuple[int, int] | None:
        diagnostics = parsed.get("diagnostics", {}) if isinstance(parsed, dict) else {}
        section_map = diagnostics.get("section_map", {})
        line_map = {
            line.line_id: line
            for line in extraction.lines
            if isinstance(line.line_id, int) and line.bbox is not None
        }
        candidate_line_ids: set[int] = set()
        for row in parsed.get("ocr_texts", []):
            if not isinstance(row, dict):
                continue
            line_id = row.get("line_id")
            text = self._clean_string(row.get("text"))
            if not isinstance(line_id, int) or not text:
                continue
            if section_map.get(str(line_id)) == "items":
                candidate_line_ids.add(line_id)
            if self._looks_like_item_strip_placeholder_row(text) or self._looks_like_item_strip_gift_tail_row(text):
                candidate_line_ids.add(line_id)
        selected_lines = [line_map[line_id] for line_id in candidate_line_ids if line_id in line_map]
        if not selected_lines:
            return None
        min_top = min(min(point[1] for point in line.bbox) for line in selected_lines if line.bbox is not None)
        max_bottom = max(max(point[1] for point in line.bbox) for line in selected_lines if line.bbox is not None)
        gap_line_id = gap.get("line_id")
        gap_kind = str(gap.get("kind") or "")
        gap_line = line_map.get(gap_line_id) if isinstance(gap_line_id, int) else None
        if gap_line is not None and gap_line.bbox is not None:
            gap_top = min(point[1] for point in gap_line.bbox)
            if gap_kind == "gift_tail":
                top = max(0, int(gap_top) - 50)
            elif gap_kind == "placeholder_barcode":
                top = max(0, int(gap_top) - 100)
            else:
                top = max(0, int(min_top) - 60)
        else:
            top = max(0, int(min_top) - 60)
        bottom = min(image_height, int(max_bottom) + 80)
        if top >= bottom:
            return None
        return top, bottom

    def _build_top_strip_date_image(self, image: Image.Image) -> Image.Image:
        normalized = ImageOps.exif_transpose(image).convert("RGB")
        width, height = normalized.size
        strip_height = max(DATE_FALLBACK_MIN_HEIGHT, min(int(height * DATE_FALLBACK_TOP_RATIO), DATE_FALLBACK_MAX_HEIGHT))
        strip = normalized.crop((0, 0, width, strip_height))
        grayscale = ImageOps.grayscale(strip)
        enhanced = ImageOps.autocontrast(grayscale)
        enhanced = ImageEnhance.Contrast(enhanced).enhance(1.8)
        enhanced = enhanced.filter(ImageFilter.SHARPEN).filter(ImageFilter.SHARPEN)
        upscaled = enhanced.resize(
            (enhanced.width * DATE_FALLBACK_UPSCALE, enhanced.height * DATE_FALLBACK_UPSCALE),
            resample=Image.Resampling.LANCZOS,
        )
        return ImageOps.expand(upscaled, border=(0, 36, 0, 0), fill=255)

    def _apply_item_strip_fallback(
        self,
        parsed: dict,
        *,
        item_strip_extraction: OcrExtraction | None,
        gap: dict[str, object] | None,
    ) -> None:
        diagnostics = parsed.setdefault("diagnostics", {})
        diagnostics["item_strip_fallback_used"] = False
        diagnostics["item_strip_fallback_added_count"] = 0
        if item_strip_extraction is None or gap is None:
            return

        fallback_result = self.parser.parse_lines(item_strip_extraction.lines)
        existing_items = parsed.get("items", [])
        added_count = 0
        for candidate in fallback_result.items:
            candidate_item = asdict(candidate)
            self._recalculate_review_state(candidate_item, parsed.get("purchased_at"))
            if not self._should_merge_item_strip_candidate(
                candidate_item,
                existing_items,
                gap_kind=str(gap.get("kind") or ""),
            ):
                continue
            existing_items.append(candidate_item)
            added_count += 1

        if added_count <= 0:
            return
        diagnostics["item_strip_fallback_used"] = True
        diagnostics["item_strip_fallback_added_count"] = added_count
        diagnostics["item_strip_fallback_source"] = "item_strip"

    def _should_merge_item_strip_candidate(self, candidate: dict, existing_items: list[dict], *, gap_kind: str) -> bool:
        candidate_name = self._clean_string(candidate.get("normalized_name")) or self._clean_string(candidate.get("raw_name"))
        if candidate_name is None:
            return False
        candidate_parse_pattern = self._clean_string(candidate.get("parse_pattern")) or ""
        candidate_is_gift = candidate_parse_pattern in {
            "single_line_gift",
            "split_gift",
            "compact_gift",
            "two_line_barcode_gift",
        }
        if candidate.get("quantity") is None or candidate.get("amount") is None:
            if not candidate_is_gift:
                return False
        if gap_kind == "gift_tail" and not candidate_is_gift:
            return False
        if gap_kind == "placeholder_barcode" and candidate_is_gift:
            return False
        if self.parser._looks_like_summary_fragment_name(candidate_name):
            return False
        if self.parser._looks_like_domain_noise_name(candidate_name):
            return False
        candidate_names = self._item_name_keys(candidate)
        for existing in existing_items:
            if not isinstance(existing, dict):
                continue
            existing_names = self._item_name_keys(existing)
            same_quantity = (
                candidate.get("quantity") is not None
                and existing.get("quantity") is not None
                and abs(float(candidate["quantity"]) - float(existing["quantity"])) < 0.001
            )
            same_amount = (
                candidate.get("amount") is not None
                and existing.get("amount") is not None
                and abs(float(candidate["amount"]) - float(existing["amount"])) < 1.0
            )
            existing_parse_pattern = self._clean_string(existing.get("parse_pattern")) or ""
            existing_is_gift = existing_parse_pattern in {
                "single_line_gift",
                "split_gift",
                "compact_gift",
                "two_line_barcode_gift",
            }
            if same_quantity and same_amount and candidate_names & existing_names:
                return False
            if candidate_is_gift and existing_is_gift and same_quantity and candidate_names & existing_names:
                return False
        return True

    def _item_name_keys(self, item: dict) -> set[str]:
        keys: set[str] = set()
        for field_name in ("normalized_name", "raw_name"):
            value = self._clean_string(item.get(field_name))
            if value:
                keys.add(re.sub(r"\s+", "", value).lower())
        return keys

    def _should_request_qwen_header_rescue(self, parsed: dict) -> bool:
        return parsed.get("purchased_at") is None or parsed.get("vendor_name") is None

    def _supports_qwen_header_rescue(self) -> bool:
        return self.qwen_provider is not None and not isinstance(self.qwen_provider, NoopQwenProvider)

    def _supports_qwen_item_normalization(self) -> bool:
        return self.qwen_provider is not None and not isinstance(self.qwen_provider, NoopQwenProvider)

    def _build_qwen_header_rescue_payload(
        self,
        *,
        parsed: dict,
        extraction: OcrExtraction,
        top_strip_extraction: OcrExtraction | None,
    ) -> dict:
        payload = {
            "rescue_targets": [
                key for key in ("vendor_name", "purchased_at")
                if parsed.get(key) is None
            ],
            "current_vendor_name": parsed.get("vendor_name"),
            "current_purchased_at": parsed.get("purchased_at"),
            "merged_rows": self._select_qwen_header_rows(extraction.lines),
            "raw_tokens": self._select_qwen_header_raw_tokens(top_strip_extraction, extraction),
            "top_strip_rows": [
                line.text for line in (top_strip_extraction.lines[:QWEN_HEADER_MAX_TOP_STRIP_ROWS] if top_strip_extraction else [])
            ],
            "known_totals": dict(parsed.get("totals", {})),
            "review_reasons": list(parsed.get("review_reasons", [])),
            "diagnostics": {
                "quality_score": extraction.quality_score,
                "low_quality_reasons": list(extraction.low_quality_reasons),
                "date_fallback_used": parsed.get("diagnostics", {}).get("date_fallback_used", False),
            },
        }
        return payload

    def _select_qwen_header_rows(self, lines: list[OcrLine]) -> list[dict]:
        selected: list[dict] = []
        for line in lines:
            text = line.text.strip()
            if not text:
                continue
            if self.parser._looks_like_item_header(text) or self.parser._looks_like_item_candidate(text):
                break
            selected.append(self._serialize_line(line))
            if len(selected) >= QWEN_HEADER_MAX_MERGED_ROWS:
                break
        return selected

    def _select_qwen_header_raw_tokens(
        self,
        top_strip_extraction: OcrExtraction | None,
        extraction: OcrExtraction,
    ) -> list[dict]:
        source_tokens = top_strip_extraction.raw_tokens if top_strip_extraction and top_strip_extraction.raw_tokens else extraction.raw_tokens
        return [self._serialize_raw_token(token) for token in source_tokens[:QWEN_HEADER_MAX_RAW_TOKENS]]

    def _apply_qwen_header_rescue(self, parsed: dict, rescue: dict) -> bool:
        applied = False

        if parsed.get("vendor_name") is None:
            vendor_name = self._clean_string(rescue.get("vendor_name"))
            if vendor_name and self._is_plausible_vendor_name(vendor_name):
                parsed["vendor_name"] = vendor_name
                applied = True

        if parsed.get("purchased_at") is None:
            purchased_at = self._coerce_valid_purchased_at(rescue.get("purchased_at"))
            if purchased_at is not None:
                parsed["purchased_at"] = purchased_at
                parsed["review_reasons"] = [
                    reason for reason in parsed.get("review_reasons", []) if reason != "missing_purchased_at"
                ]
                for item in parsed.get("items", []):
                    if isinstance(item, dict):
                        self._recalculate_review_state(item, purchased_at)
                applied = True

        return applied

    def _is_plausible_vendor_name(self, vendor_name: str) -> bool:
        return self.parser._looks_like_vendor_candidate(vendor_name) or self.parser._looks_like_plausible_vendor_fallback(vendor_name)

    def _coerce_valid_purchased_at(self, value: object) -> str | None:
        cleaned = self._clean_string(value)
        if cleaned is None:
            return None
        return self.parser._extract_purchased_at(
            [OcrLine(text=cleaned, confidence=1.0, line_id=0, page_order=0)]
        )

    def _resolve_qwen_mode(self, *, header_qwen_attempted: bool, item_qwen_attempted: bool) -> str:
        if header_qwen_attempted and item_qwen_attempted:
            return "header_and_item"
        if header_qwen_attempted:
            return "header_rescue"
        if item_qwen_attempted:
            return "item_refinement"
        return "disabled"

    def _build_rule_parse_response(
        self,
        result: object,
        extraction: OcrExtraction,
        trace_id: str,
    ) -> dict:
        return {
            "trace_id": trace_id,
            "engine_version": RECEIPT_ENGINE_VERSION,
            "vendor_name": result.vendor_name,
            "purchased_at": result.purchased_at,
            "ocr_texts": [self._serialize_line(line) for line in extraction.lines],
            "raw_tokens": [self._serialize_raw_token(token) for token in extraction.raw_tokens],
            "items": [asdict(item) for item in result.items],
            "totals": dict(result.totals),
            "confidence": result.confidence,
            "review_required": result.review_required,
            "review_reasons": list(result.review_reasons),
            "diagnostics": {
                **result.diagnostics,
                "quality_score": extraction.quality_score,
                "rotation_applied": extraction.rotation_applied,
                "perspective_corrected": extraction.perspective_corrected,
                "low_quality_reasons": list(extraction.low_quality_reasons),
            },
        }

    def _normalize_extraction(self, extraction: object) -> OcrExtraction:
        if isinstance(extraction, OcrExtraction):
            return extraction
        if isinstance(extraction, list):
            return OcrExtraction(lines=extraction)
        raise TypeError("OCR backend must return OcrExtraction or list[OcrLine].")

    def _build_qwen_item_normalization_payload(self, parsed: dict, lines: list[OcrLine]) -> dict:
        line_map = {line.line_id: line.text for line in lines if line.line_id is not None}
        line_index_map = {line.line_id: index for index, line in enumerate(lines) if line.line_id is not None}
        review_items = []
        for index, item in enumerate(parsed["items"]):
            if not self._should_request_qwen_item_normalization(item):
                continue
            missing_fields = []
            if item.get("normalized_name") is None:
                missing_fields.append("normalized_name")
            if item.get("quantity") is None:
                missing_fields.append("quantity")
            if item.get("unit") is None:
                missing_fields.append("unit")
            if item.get("amount") is None:
                missing_fields.append("amount")
            review_items.append(
                {
                    "index": index,
                    "raw_name": item["raw_name"],
                    "current_normalized_name": item.get("normalized_name"),
                    "current_quantity": item.get("quantity"),
                    "current_unit": item.get("unit"),
                    "current_amount": item.get("amount"),
                    "confidence": item.get("match_confidence") or item.get("confidence"),
                    "review_reasons": list(item.get("review_reason", [])),
                    "missing_fields": missing_fields,
                    "source_lines": [
                        line_map.get(line_id)
                        for line_id in item.get("source_line_ids", [])
                        if line_map.get(line_id)
                    ],
                    "context_lines": self._build_qwen_item_context_lines(
                        item=item,
                        lines=lines,
                        line_index_map=line_index_map,
                    ),
                }
            )
        review_items.sort(
            key=lambda value: self._qwen_item_priority(
                review_reasons=value.get("review_reasons", []),
                raw_name=value.get("raw_name", ""),
            ),
            reverse=True,
        )
        return {
            "current_vendor_name": parsed.get("vendor_name"),
            "current_purchased_at": parsed.get("purchased_at"),
            "known_totals": dict(parsed.get("totals", {})),
            "review_items": review_items[:QWEN_ITEM_MAX_REVIEW_ITEMS],
        }

    def _build_qwen_item_context_lines(
        self,
        *,
        item: dict,
        lines: list[OcrLine],
        line_index_map: dict[int, int],
    ) -> list[str]:
        source_line_ids = [
            line_id
            for line_id in item.get("source_line_ids", [])
            if isinstance(line_id, int) and line_id in line_index_map
        ]
        if not source_line_ids:
            return []

        indices = [line_index_map[line_id] for line_id in source_line_ids]
        start = max(0, min(indices) - 1)
        end = min(len(lines), max(indices) + 2)

        context_lines: list[str] = []
        seen: set[str] = set()
        for line in lines[start:end]:
            text = line.text.strip()
            if not text or text in seen:
                continue
            seen.add(text)
            context_lines.append(text)
        return context_lines

    def _should_request_qwen_item_normalization(self, item: dict) -> bool:
        reasons = set(item.get("review_reason", []))
        if "unknown_item" in reasons and self._looks_like_suspicious_ocr_item_name(item.get("raw_name")):
            return True
        if not item.get("needs_review"):
            return False
        if "missing_amount" in reasons or "missing_quantity_or_unit" in reasons or "low_confidence" in reasons:
            return True
        return False

    def _looks_like_suspicious_ocr_item_name(self, raw_name: object) -> bool:
        if not isinstance(raw_name, str):
            return False
        cleaned = raw_name.strip()
        compact = "".join(cleaned.split())
        if len(compact) <= 2:
            return True
        if any(char in cleaned for char in "[]{}|"):
            return True
        if cleaned.endswith(("L", "I", "]")):
            return True
        return False

    def _qwen_item_priority(self, *, review_reasons: list[str], raw_name: object) -> int:
        reasons = set(review_reasons)
        score = 0
        if "missing_amount" in reasons:
            score += 200
        if "missing_quantity_or_unit" in reasons:
            score += 180
        if "low_confidence" in reasons:
            score += 70
        if "unknown_item" in reasons and self._looks_like_suspicious_ocr_item_name(raw_name):
            score += 40
        return score

    def _invoke_qwen_item_normalizer(self, payload: dict) -> dict | None:
        provider_method = getattr(self.qwen_provider, "normalize_receipt_items", None)
        if not callable(provider_method):
            return None

        result = provider_method(payload)
        if result is not None:
            return result

        review_items = payload.get("review_items")
        if not isinstance(review_items, list) or len(review_items) <= 1:
            return None

        merged_items: list[dict] = []
        for review_item in review_items:
            if not isinstance(review_item, dict):
                continue
            single_payload = {
                **payload,
                "review_items": [review_item],
            }
            single_result = provider_method(single_payload)
            if not isinstance(single_result, dict):
                continue
            single_items = single_result.get("items")
            if not isinstance(single_items, list):
                continue
            merged_items.extend(item for item in single_items if isinstance(item, dict))

        return {"items": merged_items} if merged_items else None

    def _apply_qwen_item_normalization(self, parsed: dict, normalization: dict) -> bool:
        corrections = normalization.get("items")
        if not isinstance(corrections, list):
            return False

        applied = False
        for correction in corrections:
            if not isinstance(correction, dict):
                continue
            index = correction.get("index")
            if not isinstance(index, int) or not 0 <= index < len(parsed["items"]):
                continue
            item = parsed["items"][index]
            item_updated = False

            normalized_name = self._clean_string(correction.get("normalized_name"))
            if (
                normalized_name is not None
                and self._should_accept_qwen_normalized_name(item, normalized_name)
            ):
                item["normalized_name"] = normalized_name
                item_updated = True

            if item.get("quantity") is None:
                quantity = self._coerce_float(correction.get("quantity"))
                if quantity is not None:
                    item["quantity"] = quantity
                    item_updated = True

            if item.get("unit") is None:
                unit = self._clean_string(correction.get("unit"))
                if unit is not None:
                    item["unit"] = unit
                    item_updated = True

            if item.get("amount") is None:
                amount = self._coerce_float(correction.get("amount"))
                if amount is not None:
                    item["amount"] = amount
                    item_updated = True

            if item_updated:
                item["review_reason"] = [
                    reason for reason in item.get("review_reason", []) if reason != "low_confidence"
                ]
                applied = True

            self._recalculate_review_state(item, parsed["purchased_at"])

        return applied

    def _should_accept_qwen_normalized_name(self, item: dict, normalized_name: str) -> bool:
        if not self._is_plausible_normalized_name(item["raw_name"], normalized_name):
            return False

        current_normalized_name = self._clean_string(item.get("normalized_name"))
        if current_normalized_name is None:
            return True
        if current_normalized_name == normalized_name:
            return False

        reasons = set(item.get("review_reason", []))
        return bool({"low_confidence", "unknown_item"} & reasons)

    def _build_qwen_receipt_payload(
        self,
        extraction: OcrExtraction,
        source: str,
        source_type: str,
        fallback_result: object,
    ) -> dict:
        return {
            "source": source,
            "source_type": source_type,
            "merged_rows": [self._serialize_line(line) for line in extraction.lines],
            "raw_tokens": [self._serialize_raw_token(token) for token in extraction.raw_tokens],
            "vendor_candidates": [fallback_result.vendor_name] if fallback_result.vendor_name else [],
            "date_candidates": [fallback_result.purchased_at] if fallback_result.purchased_at else [],
            "known_totals": dict(fallback_result.totals),
            "parse_diagnostics": {
                "line_count": len(extraction.lines),
                "raw_token_count": len(extraction.raw_tokens),
                "quality_score": extraction.quality_score,
                "section_confidence": fallback_result.diagnostics.get("section_confidence"),
                "low_quality_reasons": list(extraction.low_quality_reasons),
            },
        }

    def _serialize_line(self, line: OcrLine) -> dict:
        return {
            "line_id": line.line_id,
            "text": line.text,
            "confidence": line.confidence,
            "bbox": line.bbox,
            "center": line.center,
            "page_order": line.page_order,
        }

    def _serialize_raw_token(self, token: dict[str, object]) -> dict:
        return {
            "text": token.get("text"),
            "confidence": token.get("confidence"),
            "bbox": token.get("bbox"),
            "source": token.get("source"),
            "token_index": token.get("token_index"),
        }

    def _invoke_qwen_receipt_extractor(self, payload: dict) -> dict | None:
        provider_method = getattr(self.qwen_provider, "extract_receipt", None)
        if callable(provider_method):
            return provider_method(payload)
        fallback_method = getattr(self.qwen_provider, "refine_receipt", None)
        if callable(fallback_method):
            return fallback_method(payload)
        return None

    def _invoke_qwen_header_rescue(self, payload: dict) -> dict | None:
        provider_method = getattr(self.qwen_provider, "rescue_receipt_header", None)
        if callable(provider_method):
            return provider_method(payload)
        return self._invoke_qwen_receipt_extractor(payload)

    def _build_qwen_parse_response(
        self,
        qwen_result: dict,
        fallback_result: object,
        extraction: OcrExtraction,
        trace_id: str,
    ) -> dict:
        purchased_at = self._clean_string(qwen_result.get("purchased_at")) or fallback_result.purchased_at
        qwen_items = self._normalize_qwen_items(qwen_result.get("items"), purchased_at=purchased_at)
        items = qwen_items if qwen_items else [asdict(item) for item in fallback_result.items]
        totals = self._normalize_totals(qwen_result.get("totals")) or dict(fallback_result.totals)
        confidence = self._coerce_float(qwen_result.get("confidence"))

        return {
            "trace_id": trace_id,
            "engine_version": RECEIPT_ENGINE_VERSION,
            "vendor_name": self._clean_string(qwen_result.get("vendor_name")) or fallback_result.vendor_name,
            "purchased_at": purchased_at,
            "items": items,
            "totals": totals,
            "confidence": confidence if confidence is not None else fallback_result.confidence,
            "review_required": bool(qwen_result.get("review_required", False)),
            "review_reasons": self._normalize_review_reasons(qwen_result.get("review_reasons")),
            "diagnostics": {
                **fallback_result.diagnostics,
                "quality_score": extraction.quality_score,
                "rotation_applied": extraction.rotation_applied,
                "perspective_corrected": extraction.perspective_corrected,
                "low_quality_reasons": list(extraction.low_quality_reasons),
            },
        }

    def _normalize_qwen_items(self, items: object, purchased_at: str | None) -> list[dict]:
        if not isinstance(items, list):
            return []

        normalized_items: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            raw_name = self._clean_string(item.get("raw_name")) or self._clean_string(item.get("normalized_name"))
            normalized_name = self._clean_string(item.get("normalized_name"))
            if raw_name is None:
                continue

            category = self._clean_string(item.get("category"))
            if category not in VALID_CATEGORIES:
                category = "other"

            storage_type = self._clean_string(item.get("storage_type"))
            if storage_type not in VALID_STORAGE_TYPES:
                storage_type = CATEGORY_STORAGE.get(category, "room")

            normalized_item = {
                "raw_name": raw_name,
                "normalized_name": normalized_name,
                "category": category,
                "storage_type": storage_type,
                "quantity": self._coerce_float(item.get("quantity")),
                "unit": self._clean_string(item.get("unit")),
                "amount": self._coerce_float(item.get("amount")),
                "confidence": self._coerce_float(item.get("confidence")) or 0.0,
                "match_confidence": self._coerce_float(item.get("match_confidence")) or self._coerce_float(item.get("confidence")) or 0.0,
                "parse_pattern": "qwen_structured",
                "source_line_ids": self._normalize_source_line_ids(item.get("source_line_ids")),
                "needs_review": False,
                "review_reason": [],
            }
            self._recalculate_review_state(normalized_item, purchased_at)
            normalized_items.append(normalized_item)

        return normalized_items

    def _normalize_source_line_ids(self, source_line_ids: object) -> list[int]:
        if not isinstance(source_line_ids, list):
            return []
        return [value for value in source_line_ids if isinstance(value, int) and not isinstance(value, bool)]

    def _normalize_totals(self, totals: object) -> dict[str, float]:
        if not isinstance(totals, dict):
            return {}
        normalized: dict[str, float] = {}
        for key in ("subtotal", "tax", "total", "payment_amount"):
            value = self._coerce_float(totals.get(key))
            if value is not None:
                normalized[key] = value
        return normalized

    def _normalize_review_reasons(self, review_reasons: object) -> list[str]:
        if not isinstance(review_reasons, list):
            return []
        return [value.strip() for value in review_reasons if isinstance(value, str) and value.strip()]

    def _is_plausible_normalized_name(self, raw_name: str, normalized_name: str) -> bool:
        if "_" in normalized_name:
            return False
        raw_has_hangul = any("가" <= char <= "힣" for char in raw_name)
        normalized_has_hangul = any("가" <= char <= "힣" for char in normalized_name)
        if raw_has_hangul and not normalized_has_hangul:
            return False
        return True

    def _clean_string(self, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        cleaned = value.strip()
        return cleaned or None

    def _coerce_float(self, value: object) -> float | None:
        if isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            cleaned = value.replace(",", "").strip()
            if not cleaned:
                return None
            try:
                return float(cleaned)
            except ValueError:
                return None
        return None

    def _recalculate_review_state(self, item: dict, purchased_at: str | None) -> None:
        reasons = list(item.get("review_reason", []))
        parse_pattern = self._clean_string(item.get("parse_pattern")) or ""
        is_gift_item = parse_pattern in {
            "single_line_gift",
            "split_gift",
            "compact_gift",
            "two_line_barcode_gift",
        }
        if purchased_at is not None:
            reasons = [reason for reason in reasons if reason != "missing_purchased_at"]
        elif "missing_purchased_at" not in reasons:
            reasons.append("missing_purchased_at")
        if item.get("normalized_name") is not None:
            reasons = [reason for reason in reasons if reason != "unknown_item"]
        elif "unknown_item" not in reasons:
            reasons.append("unknown_item")
        if item.get("quantity") is not None and item.get("unit") is not None:
            reasons = [reason for reason in reasons if reason != "missing_quantity_or_unit"]
        elif "missing_quantity_or_unit" not in reasons:
            reasons.append("missing_quantity_or_unit")
        if item.get("amount") is not None or is_gift_item:
            reasons = [reason for reason in reasons if reason != "missing_amount"]
        elif "missing_amount" not in reasons:
            reasons.append("missing_amount")
        item["review_reason"] = reasons
        structural_reasons = [
            reason
            for reason in reasons
            if reason not in {"unknown_item", "missing_purchased_at", "low_confidence"}
        ]
        item["needs_review"] = bool(structural_reasons)

    def _iter_ocr_text_rows(self, parsed: dict) -> list[str]:
        rows: list[str] = []
        for value in parsed.get("ocr_texts", []):
            if isinstance(value, dict):
                text = self._clean_string(value.get("text"))
            else:
                text = self._clean_string(value)
            if text:
                rows.append(text)
        return rows

    def _looks_like_partial_receipt(self, parsed: dict) -> bool:
        rows = self._iter_ocr_text_rows(parsed)
        if not rows or not parsed.get("items"):
            return False
        first_row = rows[0]
        if not self.parser._looks_like_item_header(first_row):
            if parsed.get("vendor_name") is not None or parsed.get("purchased_at") is not None:
                return False
            if not parsed.get("totals"):
                return False
            leading_rows = rows[: min(len(rows), 6)]
            item_like_rows = sum(1 for row in leading_rows if self._looks_like_partial_item_row(row))
            return len(parsed.get("items", [])) >= 4 and item_like_rows >= min(3, len(leading_rows))
        if parsed.get("vendor_name") is not None or parsed.get("purchased_at") is not None:
            return False
        return True

    def _looks_like_partial_item_row(self, text: str) -> bool:
        if self.parser._looks_like_item_candidate(text):
            return True
        compact = re.sub(r"\s+", "", text)
        if re.search(r"\d{1,3}(?:,\d{3})+\d+\d{1,3}(?:,\d{3})+", compact):
            return True
        return bool(re.search(r"\d{1,3}(?:,\d{3})+\s+\d+\s+\d{1,3}(?:,\d{3})+", text))

    def _looks_like_unconsumed_metadata_row(self, text: str) -> bool:
        hangul_only = re.sub(r"[^가-힣]", "", text or "")
        if not hangul_only:
            return False
        metadata_tokens = (
            "부가세",
            "과세물품",
            "물품가액",
            "포인트",
            "고객님",
            "적립",
            "미사용",
            "소멸",
        )
        return any(token in hangul_only for token in metadata_tokens)

    def _allows_missing_vendor_without_review(self, parsed: dict, *, partial_receipt: bool) -> bool:
        if partial_receipt:
            return True
        if parsed.get("vendor_name") is not None:
            return False
        items = [item for item in parsed.get("items", []) if isinstance(item, dict)]
        if not items or any(item.get("needs_review") for item in items):
            return False
        diagnostics = parsed.get("diagnostics", {}) if isinstance(parsed, dict) else {}
        if diagnostics.get("item_strip_fallback_used") and parsed.get("purchased_at") is not None:
            return True
        totals = parsed.get("totals", {}) if isinstance(parsed, dict) else {}
        has_known_total = isinstance(totals, dict) and any(
            totals.get(key) is not None for key in ("payment_amount", "total", "subtotal")
        )
        row_count = len(self._iter_ocr_text_rows(parsed))
        return parsed.get("purchased_at") is not None and len(items) <= 2 and has_known_total and row_count >= 8

    def _extract_discount_adjustment_total(self, parsed: dict) -> float:
        total = 0.0
        for row in self._iter_ocr_text_rows(parsed):
            if not any(keyword.lower() in row.lower() for keyword in DISCOUNT_KEYWORDS):
                continue
            matches = re.findall(r"-\d{1,3}(?:,\d{3})+|-\d+", row)
            if not matches:
                continue
            amount = self._coerce_float(matches[-1])
            if amount is None:
                continue
            total += amount
        return total

    def _extract_unconsumed_item_amount_total(self, parsed: dict) -> float:
        diagnostics = parsed.get("diagnostics", {}) if isinstance(parsed, dict) else {}
        section_map = diagnostics.get("section_map", {})
        consumed_ids = {int(value) for value in diagnostics.get("consumed_line_ids", [])}
        item_header_line_id: int | None = None
        item_line_ids: list[int] = []
        inferred_item_like_line_ids: list[int] = []
        for row in parsed.get("ocr_texts", []):
            if not isinstance(row, dict):
                continue
            line_id = row.get("line_id")
            text = self._clean_string(row.get("text"))
            if isinstance(line_id, int) and text and self.parser._looks_like_item_header(text) and item_header_line_id is None:
                item_header_line_id = line_id
            if isinstance(line_id, int) and section_map.get(str(line_id)) == "items":
                item_line_ids.append(line_id)
            if isinstance(line_id, int) and text and (
                self._looks_like_partial_item_row(text)
                or self._looks_like_item_strip_gift_tail_row(text)
                or self.parser._looks_like_item_candidate(text)
            ):
                inferred_item_like_line_ids.append(line_id)
        earliest_item_line_id = min(item_line_ids) if item_line_ids else None
        inferred_item_like_line_id = min(inferred_item_like_line_ids) if inferred_item_like_line_ids else None
        total_candidates: list[float] = []
        parsed_totals = parsed.get("totals", {}) if isinstance(parsed, dict) else {}
        if isinstance(parsed_totals, dict):
            for key in ("payment_amount", "total", "subtotal"):
                value = parsed_totals.get(key)
                if value is not None:
                    total_candidates.append(float(value))
        total = 0.0
        for row in parsed.get("ocr_texts", []):
            if not isinstance(row, dict):
                continue
            line_id = row.get("line_id")
            text = self._clean_string(row.get("text"))
            if not isinstance(line_id, int) or not text:
                continue
            if line_id in consumed_ids:
                continue
            if item_header_line_id is not None and line_id <= item_header_line_id:
                continue
            cutoff_line_id = inferred_item_like_line_id if inferred_item_like_line_id is not None else earliest_item_line_id
            if item_header_line_id is None and cutoff_line_id is not None and line_id < max(0, cutoff_line_id - 2):
                continue
            section = section_map.get(str(line_id))
            if section in {"totals", "payment"}:
                continue
            if section == "header":
                continue
            if self.parser._looks_like_footer(text) or self.parser._looks_like_date(text):
                continue
            if self._looks_like_unconsumed_metadata_row(text):
                continue
            if self._looks_like_item_strip_gift_tail_row(text):
                continue
            compact_text = re.sub(r"\s+", "", text).lower()
            if any(keyword.lower() in compact_text for keyword in self.parser.rules.payment_keywords):
                continue
            if section == "ignored":
                if not (
                    text.startswith("*")
                    or self.parser._looks_like_item_candidate(text)
                    or bool(re.search(r"\d+\s+\d{1,3}(?:,\d{3})+", text))
                ):
                    continue
            has_hangul = any("가" <= char <= "힣" for char in text)
            if not has_hangul and not text.startswith("*") and "," not in text and not re.search(r"\d+\s+\d{1,3}(?:,\d{3})+", text):
                continue
            matches = re.findall(r"\d{1,3}(?:,\d{3})+|\d+", text)
            if not matches:
                continue
            amount = self._coerce_float(matches[-1])
            if amount is None or amount <= 0:
                continue
            if len(matches[-1]) >= 7 and "," not in matches[-1]:
                continue
            if amount < 100 and re.search(r"\d+[a-zA-Z]$", text):
                continue
            if section == "ignored" and any(abs(amount - candidate) <= 1.0 for candidate in total_candidates):
                continue
            total += amount
        return total

    def _finalize_parse_result(self, parsed: dict, low_quality_reasons: list[str]) -> None:
        diagnostics = parsed.setdefault("diagnostics", {})
        partial_receipt = self._looks_like_partial_receipt(parsed)
        diagnostics["partial_receipt"] = partial_receipt
        review_reasons = [
            reason
            for reason in list(parsed.get("review_reasons", []))
            if reason not in {"missing_purchased_at", "missing_vendor_name", "unresolved_items", "total_mismatch"}
        ]
        for item in parsed["items"]:
            if isinstance(item, dict):
                self._recalculate_review_state(item, parsed.get("purchased_at"))
        allows_missing_vendor = self._allows_missing_vendor_without_review(parsed, partial_receipt=partial_receipt)
        if not allows_missing_vendor and parsed.get("vendor_name") is None and "missing_vendor_name" not in review_reasons:
            review_reasons.append("missing_vendor_name")
        if not partial_receipt and parsed.get("purchased_at") is None and "missing_purchased_at" not in review_reasons:
            review_reasons.append("missing_purchased_at")
        if any(item.get("needs_review") for item in parsed["items"]) and "unresolved_items" not in review_reasons:
            review_reasons.append("unresolved_items")
        if low_quality_reasons:
            review_reasons.extend(reason for reason in low_quality_reasons if reason not in review_reasons)

        known_total_candidates: list[float] = []
        subtotal = parsed["totals"].get("subtotal")
        if subtotal is not None:
            known_total_candidates.append(float(subtotal))
        if subtotal is not None and parsed["totals"].get("tax") is not None:
            known_total_candidates.append(float(subtotal) + float(parsed["totals"]["tax"]))
        if parsed["totals"].get("payment_amount") is not None and parsed["totals"].get("tax") is not None:
            known_total_candidates.append(float(parsed["totals"]["payment_amount"]) - float(parsed["totals"]["tax"]))
        total = parsed["totals"].get("total")
        if total is not None:
            known_total_candidates.append(float(total))
        payment_amount = parsed["totals"].get("payment_amount")
        if payment_amount is not None:
            known_total_candidates.append(float(payment_amount))
        known_total_candidates = list(dict.fromkeys(known_total_candidates))
        item_sum = sum(float(item["amount"]) for item in parsed["items"] if item.get("amount") is not None)
        discount_adjustment_total = self._extract_discount_adjustment_total(parsed)
        unconsumed_item_amount_total = self._extract_unconsumed_item_amount_total(parsed)
        diagnostics["discount_adjustment_total"] = discount_adjustment_total
        diagnostics["unconsumed_item_amount_total"] = unconsumed_item_amount_total
        if known_total_candidates and item_sum > 0:
            adjusted_item_sum = item_sum + discount_adjustment_total
            fully_adjusted_item_sum = adjusted_item_sum + unconsumed_item_amount_total
            matches_known_total = any(
                abs(candidate - item_sum) <= 1.0
                or abs(candidate - adjusted_item_sum) <= 1.0
                or abs(candidate - fully_adjusted_item_sum) <= 1.0
                for candidate in known_total_candidates
            )
            if not matches_known_total and not partial_receipt:
                if "total_mismatch" not in review_reasons:
                    review_reasons.append("total_mismatch")

        parsed["review_reasons"] = review_reasons
        parsed["review_required"] = bool(review_reasons)
        base_confidence = float(parsed.get("confidence", 0.0))
        quality_score = float(parsed["diagnostics"].get("quality_score", 1.0))
        parsed["confidence"] = round((base_confidence * 0.7) + (quality_score * 0.3), 4)
        parsed["diagnostics"]["unresolved_groups"] = sum(
            1 for item in parsed["items"] if item.get("needs_review")
        )


class ExpiryService:
    def __init__(self, evaluator: ExpiryEvaluator | None = None) -> None:
        self.evaluator = evaluator or ExpiryEvaluator()

    def evaluate(self, payload: dict) -> dict:
        items = [
            InventoryItem(
                normalized_name=item["normalized_name"],
                category=item["category"],
                storage_type=item["storage_type"],
                purchased_at=item["purchased_at"],
            )
            for item in payload["items"]
        ]
        return {
            "items": [asdict(result) for result in self.evaluator.evaluate(items)],
        }


class RecipeService:
    def __init__(self, engine: RecipeEngine | None = None, qwen_provider: object | None = None) -> None:
        self.engine = engine or RecipeEngine(qwen_provider=qwen_provider)

    def recommend(self, payload: dict) -> dict:
        inventory = [
            InventorySnapshot(
                normalized_name=item["normalized_name"],
                risk_level=item.get("risk_level", "safe"),
                is_expired=item.get("is_expired", False),
            )
            for item in payload["items"]
        ]
        return {
            "recipes": [asdict(recipe) for recipe in self.engine.recommend(inventory)],
        }
