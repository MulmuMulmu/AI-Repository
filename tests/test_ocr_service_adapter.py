from __future__ import annotations

from receipt_ocr import ReceiptOCR


def test_receipt_ocr_adapts_prototype_parse_result_to_legacy_shape(monkeypatch) -> None:
    def _stub_parse(self, payload: dict) -> dict:  # type: ignore[no-untyped-def]
        return {
            "trace_id": "receipt-test-trace",
            "engine_version": "receipt-engine-v2",
            "vendor_name": "홈플러스",
            "purchased_at": "2026-03-11",
            "ocr_texts": [
                {
                    "line_id": 0,
                    "text": "허니버터칩 1 2,000",
                    "confidence": 0.91,
                    "bbox": ((0, 0), (100, 0), (100, 20), (0, 20)),
                    "center": (50, 10),
                    "page_order": 0,
                }
            ],
            "items": [
                {
                    "raw_name": "허니버터칩",
                    "normalized_name": "감자칩",
                    "category": "other",
                    "storage_type": "room",
                    "quantity": 1.0,
                    "unit": "개",
                    "amount": 2000.0,
                    "confidence": 0.91,
                    "match_confidence": 0.91,
                    "parse_pattern": "single_line",
                    "source_line_ids": [0],
                    "needs_review": True,
                    "review_reason": ["low_confidence"],
                }
            ],
            "totals": {"payment_amount": 2000.0},
            "confidence": 0.91,
            "review_required": True,
            "review_reasons": ["unresolved_items"],
            "diagnostics": {"qwen_used": False},
        }

    monkeypatch.setattr("ocr_qwen.services.ReceiptParseService.parse", _stub_parse)

    ocr = ReceiptOCR()
    result = ocr.analyze_receipt("ignored.png")

    assert result["model"] == "receipt-engine-v2"
    assert result["vendor_name"] == "홈플러스"
    assert result["purchased_at"] == "2026-03-11"
    assert result["food_count"] == 1
    assert result["food_items"][0]["product_name"] == "허니버터칩"
    assert result["food_items"][0]["amount_krw"] == 2000
    assert result["food_items"][0]["notes"] == "low_confidence"
    assert result["food_items"][0]["box"] == ((0, 0), (100, 0), (100, 20), (0, 20))
    assert result["all_texts"][0]["text"] == "허니버터칩 1 2,000"


def test_receipt_ocr_uses_default_qwen_provider_factory(monkeypatch) -> None:
    stub_provider = object()
    monkeypatch.setattr("receipt_ocr.build_default_qwen_provider", lambda: stub_provider)

    ocr = ReceiptOCR()

    assert ocr.service.qwen_provider is stub_provider
