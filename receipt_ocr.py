"""
Prototype OCR 파이프라인을 현재 레포의 legacy 인터페이스로 감싸는 호환 래퍼.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import cv2
import matplotlib.pyplot as plt
import numpy as np

from ocr_qwen.qwen import build_default_qwen_provider
from ocr_qwen.receipts import OcrLine, ReceiptParser
from ocr_qwen.services import PaddleOcrBackend, ReceiptParseService


class ReceiptOCR:
    """기존 공개 API를 유지하면서 내부는 prototype OCR 서비스를 사용한다."""

    def __init__(self, lang: str = "korean", use_gpu: bool = False):
        del lang
        del use_gpu
        self.backend = PaddleOcrBackend()
        self.parser = ReceiptParser()
        self.service = ReceiptParseService(
            ocr_backend=self.backend,
            parser=self.parser,
            qwen_provider=build_default_qwen_provider(),
        )

    def warm_up(self) -> None:
        self.backend.warm_up()

    def read_image(self, image_path: str) -> np.ndarray:
        path = Path(image_path)
        if not path.exists():
            raise FileNotFoundError(f"이미지 파일을 찾을 수 없습니다: {image_path}")

        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
        return image

    def preprocess_image(self, img: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        enhanced = cv2.equalizeHist(gray)
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR)

    def run_ocr(self, image_path: str, preprocess: bool = True) -> List[Dict[str, Any]]:
        extraction = self.backend.extract(str(image_path), source_type="receipt_image_url")
        return [self._serialize_ocr_line(line) for line in extraction.lines]

    def extract_food_names(
        self,
        ocr_lines: List[Dict[str, Any]],
        min_confidence: float = 0.6,
    ) -> List[Dict[str, Any]]:
        rows: list[OcrLine] = []
        for index, line in enumerate(ocr_lines):
            confidence = float(line.get("confidence", 0.0))
            if confidence < min_confidence:
                continue
            text = str(line.get("text", "")).strip()
            if not text:
                continue
            bbox = line.get("bbox") or line.get("box")
            rows.append(
                OcrLine(
                    text=text,
                    confidence=confidence,
                    line_id=index,
                    bbox=self._normalize_bbox(bbox),
                )
            )

        parsed = self.parser.parse_lines(rows)
        ocr_texts = [self._serialize_ocr_line(row) for row in rows]
        return self._legacy_food_items(
            {
                "items": [item.__dict__ for item in parsed.items],
                "ocr_texts": ocr_texts,
            }
        )

    def analyze_receipt(self, image_path: str) -> dict:
        parsed = self.service.parse({"receipt_image_url": str(image_path)})
        ocr_texts = parsed.get("ocr_texts", [])
        food_items = self._legacy_food_items(parsed)
        return {
            "image_path": str(image_path),
            "model": parsed.get("engine_version"),
            "vendor_name": parsed.get("vendor_name"),
            "purchased_at": parsed.get("purchased_at"),
            "totals": parsed.get("totals", {}),
            "confidence": parsed.get("confidence", 0.0),
            "review_required": parsed.get("review_required", False),
            "review_reasons": parsed.get("review_reasons", []),
            "diagnostics": parsed.get("diagnostics", {}),
            "all_texts": ocr_texts,
            "food_items": food_items,
            "food_count": len(food_items),
        }

    def visualize_result(
        self,
        image_path: str,
        result: dict,
        output_path: Optional[str] = None,
    ) -> None:
        img = cv2.cvtColor(self.read_image(image_path), cv2.COLOR_BGR2RGB)
        fig, ax = plt.subplots(1, figsize=(12, 16))
        ax.imshow(img)

        for item in result.get("food_items", []):
            box = item.get("box")
            if not box:
                continue
            polygon = np.array(box)
            rect = plt.Polygon(polygon, fill=False, edgecolor="red", linewidth=2)
            ax.add_patch(rect)
            ax.text(
                polygon[0][0],
                polygon[0][1] - 5,
                str(item.get("name") or item.get("product_name") or ""),
                fontsize=10,
                color="red",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="yellow", alpha=0.7),
            )

        ax.set_axis_off()
        ax.set_title(f"식품 {result.get('food_count', 0)}개 감지", fontsize=14)
        plt.tight_layout()

        if output_path:
            plt.savefig(output_path, dpi=150, bbox_inches="tight")
            print(f"결과 이미지 저장: {output_path}")
        else:
            plt.show()
        plt.close()

    def _legacy_food_items(self, parsed: dict) -> list[dict[str, Any]]:
        line_map = {
            line.get("line_id"): line
            for line in parsed.get("ocr_texts", [])
            if isinstance(line, dict) and line.get("line_id") is not None
        }
        items: list[dict[str, Any]] = []
        for item in parsed.get("items", []):
            if not isinstance(item, dict):
                continue
            name = item.get("raw_name") or item.get("normalized_name")
            if not name:
                continue
            amount = item.get("amount")
            if isinstance(amount, float) and amount.is_integer():
                amount = int(amount)
            items.append(
                {
                    "name": name,
                    "product_name": name,
                    "raw_name": item.get("raw_name"),
                    "amount_krw": amount,
                    "confidence": item.get("match_confidence", item.get("confidence", 0.0)),
                    "method": item.get("parse_pattern"),
                    "matched_keywords": [],
                    "box": self._merge_boxes(
                        [
                            self._normalize_bbox(line_map[line_id].get("bbox"))
                            for line_id in item.get("source_line_ids", [])
                            if line_id in line_map
                        ]
                    ),
                    "notes": ", ".join(item.get("review_reason", [])),
                }
            )
        return items

    def _serialize_ocr_line(self, line: OcrLine) -> dict[str, Any]:
        return {
            "line_id": line.line_id,
            "text": line.text,
            "confidence": line.confidence,
            "bbox": line.bbox,
            "center": line.center,
            "page_order": line.page_order,
        }

    def _normalize_bbox(self, bbox: Any) -> tuple[tuple[float, float], ...] | None:
        if bbox is None:
            return None
        return tuple((float(point[0]), float(point[1])) for point in bbox)

    def _merge_boxes(
        self,
        boxes: list[tuple[tuple[float, float], ...] | None],
    ) -> tuple[tuple[float, float], ...] | None:
        actual_boxes = [box for box in boxes if box]
        if not actual_boxes:
            return None
        xs = [point[0] for box in actual_boxes for point in box]
        ys = [point[1] for box in actual_boxes for point in box]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        return ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y))


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법: python receipt_ocr.py <영수증_이미지_경로> [--visualize]")
        return

    image_path = sys.argv[1]
    visualize = "--visualize" in sys.argv

    ocr = ReceiptOCR()
    result = ocr.analyze_receipt(image_path)

    print("\n" + "=" * 60)
    print(" 영수증 OCR 분석 결과")
    print("=" * 60)
    print(f"모델: {result.get('model')}")
    print(f"구매일자: {result.get('purchased_at')}")
    print(f"검토필요: {result.get('review_required')}")

    print(f"\n[전체 OCR 행] ({len(result.get('all_texts', []))}줄)")
    print("-" * 60)
    for row in result.get("all_texts", []):
        print(f"  {row['text']:<40s} ({row['confidence']:.2f})")

    print(f"\n[추출된 품목] ({result.get('food_count', 0)}개)")
    print("-" * 60)
    for index, food in enumerate(result.get("food_items", []), 1):
        amount = food.get("amount_krw")
        amount_text = f"{int(amount):,}원" if isinstance(amount, (int, float)) else "-"
        print(f"  {index}. {food['name']:<28s} {amount_text:>10s}  [{food['method']}]")

    if visualize:
        output_path = str(Path(image_path).with_name(f"{Path(image_path).stem}_result.png"))
        ocr.visualize_result(image_path, result, output_path)


if __name__ == "__main__":
    main()
