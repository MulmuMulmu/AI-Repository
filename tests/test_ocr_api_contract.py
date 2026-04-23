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


class StubQwenReceiptService:
    def parse(self, payload: dict) -> dict:
        assert "receipt_image_url" in payload
        return {
            "trace_id": "receipt-test-trace",
            "engine_version": "receipt-engine-v2",
            "vendor_name": "이마트",
            "purchased_at": "2026-03-11",
            "ocr_texts": [],
            "items": [
                {
                    "raw_name": "서울우유 1L",
                    "normalized_name": "서울우유",
                    "category": "dairy",
                    "storage_type": "refrigerated",
                    "quantity": 1.0,
                    "unit": "L",
                    "amount": 3500.0,
                    "confidence": 0.99,
                    "match_confidence": 0.99,
                    "parse_pattern": "qwen_structured",
                    "source_line_ids": [0],
                    "needs_review": False,
                    "review_reason": [],
                }
            ],
            "totals": {"payment_amount": 3500.0},
            "confidence": 0.99,
            "review_required": False,
            "review_reasons": [],
            "diagnostics": {
                "quality_score": 0.95,
                "section_confidence": 0.93,
                "qwen_used": True,
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
            "category": "유제품",
        }
    ]
    assert data["food_count"] == 1
    assert data["vendor_name"] == "이마트"
    assert data["purchased_at"] == "2026-03-11"
    assert data["totals"]["payment_amount"] == 3500.0
    assert data["review_required"] is False
    assert data["review_reasons"] == []


def test_ocr_analyze_endpoint_can_enqueue_async_refinement(monkeypatch) -> None:
    scheduled: list[tuple[str, bytes, str]] = []
    store = main._get_receipt_refinement_store()
    store.clear()

    def _stub_get_service(use_qwen: bool):
        return StubQwenReceiptService() if use_qwen else StubReceiptService()

    def _stub_schedule(*, trace_id: str, image_bytes: bytes, suffix: str) -> None:
        scheduled.append((trace_id, image_bytes, suffix))

    monkeypatch.setattr(main, "_get_receipt_service", _stub_get_service)
    monkeypatch.setattr(main, "_schedule_receipt_refinement", _stub_schedule)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ocr/analyze?use_qwen=true&async_refinement=true",
                files={"image": ("receipt.png", _make_image_bytes(), "image/png")},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    data = payload["data"]
    assert data["trace_id"] == "receipt-test-trace"
    assert data["refinement_status"] == "pending"
    assert data["refinement_poll_url"].endswith("/ai/ocr/refinement/receipt-test-trace")
    assert len(scheduled) == 1
    assert scheduled[0][0] == "receipt-test-trace"


def test_ocr_refinement_status_endpoint_returns_base_and_refined_results(monkeypatch) -> None:
    store = main._get_receipt_refinement_store()
    store.clear()
    base = StubReceiptService().parse({"receipt_image_url": "ignored"})
    refined = StubQwenReceiptService().parse({"receipt_image_url": "ignored"})
    store.create_pending("receipt-test-trace", base)
    store.mark_completed("receipt-test-trace", refined)

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/ai/ocr/refinement/receipt-test-trace")

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["trace_id"] == "receipt-test-trace"
    assert payload["status"] == "completed"
    assert payload["rule_based_result"]["food_items"][0]["product_name"] == "우유"
    assert payload["refined_result"]["food_items"][0]["product_name"] == "서울우유"


def test_public_food_category_normalization_maps_known_products() -> None:
    assert main._normalize_public_food_category("other", "양념닭주물럭2.2kg") == "정육/계란"
    assert main._normalize_public_food_category("other", "청정원 서해안 까나리") == "소스/조미료/오일"
    assert main._normalize_public_food_category("vegetable", "파프리카") == "채소/과일"
