from __future__ import annotations

import asyncio
from io import BytesIO

import httpx
from PIL import Image

import main


class StubReceiptService:
    def parse(self, payload: dict) -> dict:
        assert "receipt_image_url" in payload
        return {
            "trace_id": "receipt-test-trace",
            "engine_version": "receipt-engine-v2",
            "vendor_name": "이마트",
            "purchased_at": "2026-03-11",
            "ocr_texts": [
                {
                    "line_id": 0,
                    "text": "서울우유 1L",
                    "confidence": 0.98,
                    "bbox": ((0, 0), (10, 0), (10, 10), (0, 10)),
                    "center": (5, 5),
                    "page_order": 0,
                }
            ],
            "items": [
                {
                    "raw_name": "서울우유 1L",
                    "normalized_name": "우유",
                    "category": "dairy",
                    "storage_type": "refrigerated",
                    "quantity": 1.0,
                    "unit": "L",
                    "amount": 3500.0,
                    "confidence": 0.92,
                    "match_confidence": 0.92,
                    "parse_pattern": "single_line",
                    "source_line_ids": [0],
                    "needs_review": False,
                    "review_reason": [],
                }
            ],
            "totals": {"payment_amount": 3500.0},
            "confidence": 0.97,
            "review_required": False,
            "review_reasons": [],
            "diagnostics": {
                "quality_score": 0.95,
                "section_confidence": 0.93,
                "qwen_used": False,
                "unresolved_groups": 0,
            },
        }


def _make_image_bytes() -> bytes:
    image = Image.new("RGB", (20, 20), color="white")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_ocr_analyze_endpoint_preserves_legacy_contract(monkeypatch) -> None:
    monkeypatch.setattr(main, "_get_receipt_service", lambda use_qwen: StubReceiptService())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ocr/analyze?use_qwen=true",
                files={"image": ("receipt.png", _make_image_bytes(), "image/png")},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert set(("ocr_texts", "food_items", "food_count", "model")) <= set(data.keys())
    assert data["food_items"] == [
        {
            "product_name": "우유",
            "amount_krw": 3500,
            "notes": "",
        }
    ]
    assert data["food_count"] == 1
    assert data["vendor_name"] == "이마트"
    assert data["purchased_at"] == "2026-03-11"
    assert data["totals"]["payment_amount"] == 3500.0
