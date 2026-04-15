from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from inspect import signature
import os
from pathlib import Path
import tempfile
from uuid import uuid4

import httpx
import numpy as np

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

from .expiry import ExpiryEvaluator, InventoryItem
from .preprocess import ReceiptPreprocessor, preprocess_receipt
from .qwen import LocalTransformersQwenProvider
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

        qwen_attempted = False
        qwen_fallback_reason = "provider_missing"
        if self.qwen_provider is not None:
            if (
                isinstance(self.qwen_provider, LocalTransformersQwenProvider)
                and os.environ.get("ENABLE_SYNC_LOCAL_QWEN_ITEM_NORMALIZATION", "0") != "1"
            ):
                qwen_fallback_reason = "disabled_sync_local_qwen"
            else:
                qwen_payload = self._build_qwen_item_normalization_payload(parsed=parsed, lines=extraction.lines)
                if qwen_payload["review_items"]:
                    qwen_attempted = True
                    try:
                        qwen_result = self._invoke_qwen_item_normalizer(qwen_payload)
                    except Exception:
                        qwen_fallback_reason = "provider_error"
                    else:
                        if isinstance(qwen_result, dict):
                            qwen_used = self._apply_qwen_item_normalization(parsed, qwen_result)
                            qwen_fallback_reason = None if qwen_used else "invalid_response"
                        else:
                            qwen_fallback_reason = "empty_response"
                else:
                    qwen_fallback_reason = "no_review_items"

        parsed["diagnostics"]["qwen_attempted"] = qwen_attempted
        parsed["diagnostics"]["qwen_used"] = qwen_fallback_reason is None
        parsed["diagnostics"]["qwen_mode"] = "item_refinement" if qwen_attempted else "disabled"
        parsed["diagnostics"]["qwen_fallback_reason"] = qwen_fallback_reason
        self._finalize_parse_result(parsed, extraction.low_quality_reasons)
        return parsed

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
                    "missing_fields": missing_fields,
                    "source_lines": [
                        line_map.get(line_id)
                        for line_id in item.get("source_line_ids", [])
                        if line_map.get(line_id)
                    ],
                }
            )
        return {
            "review_items": review_items,
        }

    def _should_request_qwen_item_normalization(self, item: dict) -> bool:
        if not item.get("needs_review"):
            return False
        reasons = set(item.get("review_reason", []))
        return bool({"unknown_item", "missing_quantity_or_unit"} & reasons)

    def _invoke_qwen_item_normalizer(self, payload: dict) -> dict | None:
        provider_method = getattr(self.qwen_provider, "normalize_receipt_items", None)
        if callable(provider_method):
            return provider_method(payload)
        return None

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

            normalized_name = self._clean_string(correction.get("normalized_name"))
            if (
                item.get("normalized_name") is None
                and normalized_name is not None
                and self._is_plausible_normalized_name(item["raw_name"], normalized_name)
            ):
                item["normalized_name"] = normalized_name
                applied = True

            if item.get("quantity") is None:
                quantity = self._coerce_float(correction.get("quantity"))
                if quantity is not None:
                    item["quantity"] = quantity
                    applied = True

            if item.get("unit") is None:
                unit = self._clean_string(correction.get("unit"))
                if unit is not None:
                    item["unit"] = unit
                    applied = True

            if item.get("amount") is None:
                amount = self._coerce_float(correction.get("amount"))
                if amount is not None:
                    item["amount"] = amount
                    applied = True

            self._recalculate_review_state(item, parsed["purchased_at"])

        return applied

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
        item["review_reason"] = reasons
        item["needs_review"] = bool(reasons)

    def _finalize_parse_result(self, parsed: dict, low_quality_reasons: list[str]) -> None:
        review_reasons = list(parsed.get("review_reasons", []))
        if parsed.get("purchased_at") is None and "missing_purchased_at" not in review_reasons:
            review_reasons.append("missing_purchased_at")
        if any(item.get("needs_review") for item in parsed["items"]) and "unresolved_items" not in review_reasons:
            review_reasons.append("unresolved_items")
        if low_quality_reasons:
            review_reasons.extend(reason for reason in low_quality_reasons if reason not in review_reasons)

        known_total = parsed["totals"].get("payment_amount") or parsed["totals"].get("total")
        item_sum = sum(float(item["amount"]) for item in parsed["items"] if item.get("amount") is not None)
        if known_total is not None and item_sum > 0 and abs(float(known_total) - item_sum) > 1.0:
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
