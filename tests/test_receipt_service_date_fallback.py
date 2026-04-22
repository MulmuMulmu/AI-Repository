from __future__ import annotations

from pathlib import Path

from PIL import Image

from ocr_qwen.qwen import LocalTransformersQwenProvider, NoopQwenProvider
from ocr_qwen.receipts import OcrLine
from ocr_qwen.services import OcrExtraction, ReceiptParseService


class StubBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="GS25", confidence=0.9, line_id=0, page_order=0),
                    OcrLine(text="상품명 단가 수량 금액", confidence=0.9, line_id=1, page_order=1),
                    OcrLine(text="허니버터칩", confidence=0.95, line_id=2, page_order=2),
                    OcrLine(text="2000 1 2000", confidence=0.95, line_id=3, page_order=3),
                ],
                raw_tokens=[],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="[판매] 2023-11-24 00:01:04", confidence=0.88, line_id=0, page_order=0),
            ],
            raw_tokens=[],
            quality_score=0.8,
            low_quality_reasons=[],
        )


class StubBackendWithoutDate:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="상품명 단가 수량 금액", confidence=0.9, line_id=0, page_order=0),
                    OcrLine(text="허니버터칩", confidence=0.95, line_id=1, page_order=1),
                    OcrLine(text="2000 1 2000", confidence=0.95, line_id=2, page_order=2),
                ],
                raw_tokens=[
                    {"text": "허니버터칩", "confidence": 0.95, "bbox": ((0, 0), (50, 0), (50, 20), (0, 20))},
                ],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="상단 헤더 깨짐", confidence=0.4, line_id=0, page_order=0),
            ],
            raw_tokens=[],
            quality_score=0.8,
            low_quality_reasons=[],
        )


class StubBackendWithoutVendor:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="[주문] 2023-11-24 18:59", confidence=0.99, line_id=0, page_order=0),
                    OcrLine(text="상품명 단가 수량 금액", confidence=0.9, line_id=1, page_order=1),
                    OcrLine(text="허니버터칩", confidence=0.95, line_id=2, page_order=2),
                    OcrLine(text="2000 1 2000", confidence=0.95, line_id=3, page_order=3),
                ],
                raw_tokens=[],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="세븐일레븐", confidence=0.88, line_id=0, page_order=0),
                OcrLine(text="[판매] 2023-11-24 18:59", confidence=0.88, line_id=1, page_order=1),
            ],
            raw_tokens=[],
            quality_score=0.8,
            low_quality_reasons=[],
        )


class StubHeaderQwenProvider:
    def __init__(self) -> None:
        self.payloads: list[dict] = []
        self.header_calls = 0

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        self.payloads.append(payload)
        self.header_calls += 1
        return {
            "vendor_name": "re-MART",
            "purchased_at": "2022-04-30",
        }

    def extract_receipt(self, payload: dict) -> dict | None:
        raise AssertionError("header rescue should use rescue_receipt_header first")

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        return None


class StubLargeHeaderBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text=f"row-{idx}", confidence=0.9, line_id=idx, page_order=idx)
                    for idx in range(20)
                ],
                raw_tokens=[
                    {"text": f"token-{idx}", "confidence": 0.9, "bbox": ((0, 0), (1, 0), (1, 1), (0, 1))}
                    for idx in range(40)
                ],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text=f"strip-{idx}", confidence=0.4, line_id=idx, page_order=idx)
                for idx in range(10)
            ],
            raw_tokens=[],
            quality_score=0.8,
            low_quality_reasons=[],
        )


class StubItemNormalizationBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="GS25", confidence=0.98, line_id=0, page_order=0),
                    OcrLine(text="2023/11/24 1층", confidence=0.98, line_id=1, page_order=1),
                    OcrLine(text="머쉬밀크크릿 [ 1,600", confidence=0.62, line_id=2, page_order=2),
                ],
                raw_tokens=[],
                quality_score=0.82,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="GS25", confidence=0.9, line_id=0, page_order=0),
                OcrLine(text="2023/11/24", confidence=0.9, line_id=1, page_order=1),
            ],
            raw_tokens=[],
            quality_score=0.82,
            low_quality_reasons=[],
        )


class StubMultiItemNormalizationBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="GS25", confidence=0.98, line_id=0, page_order=0),
                    OcrLine(text="2023/11/24 1층", confidence=0.98, line_id=1, page_order=1),
                    OcrLine(text="머쉬밀크크릿 [ 1,600", confidence=0.62, line_id=2, page_order=2),
                    OcrLine(text="이애 2 4,000", confidence=0.76, line_id=3, page_order=3),
                    OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.95, line_id=4, page_order=4),
                ],
                raw_tokens=[],
                quality_score=0.82,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="GS25", confidence=0.9, line_id=0, page_order=0),
                OcrLine(text="2023/11/24", confidence=0.9, line_id=1, page_order=1),
            ],
            raw_tokens=[],
            quality_score=0.82,
            low_quality_reasons=[],
        )


class StubBackendWithItemStripRecovery:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="[판매] 2015-01-20 18:28", confidence=0.98, line_id=0, page_order=0),
                    OcrLine(text="상품명 단가 수량 금액", confidence=0.95, line_id=1, page_order=1),
                    OcrLine(text="003 속이면한 누룸지(5입)", confidence=0.91, line_id=2, page_order=2),
                    OcrLine(text="8801169770207 5,600 7 39,200", confidence=0.99, line_id=3, page_order=3),
                    OcrLine(text="OV00", confidence=0.63, line_id=4, page_order=4),
                    OcrLine(text="8809145590207 990 4 3,960", confidence=0.99, line_id=5, page_order=5),
                ],
                raw_tokens=[],
                quality_score=0.54,
                low_quality_reasons=[],
            )
        if len(self.calls) == 2:
            return OcrExtraction(
                lines=[
                    OcrLine(text="[판매] 2015-01-20 18:28", confidence=0.9, line_id=0, page_order=0),
                ],
                raw_tokens=[],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="004 L맥주바이젠미니", confidence=0.74, line_id=0, page_order=0),
                OcrLine(text="8809145590207 990 4 3,960", confidence=0.99, line_id=1, page_order=1),
            ],
            raw_tokens=[],
            quality_score=0.78,
            low_quality_reasons=[],
        )


class StubBackendWithGiftItemStripRecovery:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        if len(self.calls) == 1:
            return OcrExtraction(
                lines=[
                    OcrLine(text="GS25", confidence=0.99, line_id=0, page_order=0),
                    OcrLine(text="[판매] 2023-11-24 18:59", confidence=0.99, line_id=1, page_order=1),
                    OcrLine(text="1 증정풍", confidence=0.95, line_id=2, page_order=2),
                    OcrLine(text="투썸딸기피지 1 2,800", confidence=0.88, line_id=3, page_order=3),
                    OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.89, line_id=4, page_order=4),
                    OcrLine(text="합계수량/금액 3 2,800", confidence=0.97, line_id=5, page_order=5),
                ],
                raw_tokens=[],
                quality_score=0.62,
                low_quality_reasons=[],
            )
        if len(self.calls) == 2:
            return OcrExtraction(
                lines=[
                    OcrLine(text="GS25", confidence=0.99, line_id=0, page_order=0),
                ],
                raw_tokens=[],
                quality_score=0.8,
                low_quality_reasons=[],
            )
        return OcrExtraction(
            lines=[
                OcrLine(text="투썰로알밀크티 1 증정품", confidence=0.84, line_id=0, page_order=0),
                OcrLine(text="투썸딸기피지 1 2,800", confidence=0.88, line_id=1, page_order=1),
                OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.89, line_id=2, page_order=2),
            ],
            raw_tokens=[],
            quality_score=0.79,
            low_quality_reasons=[],
        )


class StubItemQwenProvider:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        self.payloads.append(payload)
        return {
            "items": [
                {
                    "index": 0,
                    "normalized_name": "허쉬밀크초콜릿",
                }
            ]
        }

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        return None


class StubPerItemRetryQwenProvider:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        self.payloads.append(payload)
        review_items = payload.get("review_items", [])
        if len(review_items) != 1:
            return None

        raw_name = review_items[0]["raw_name"]
        if raw_name == "이애":
            return {
                "items": [
                    {
                        "index": review_items[0]["index"],
                        "normalized_name": "호레오화이트",
                    }
                ]
            }
        return None

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        return None


class StubCollapsedRescueBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def extract(self, source: str, source_type: str = "receipt_image_url") -> OcrExtraction:
        self.calls.append(source)
        return OcrExtraction(
            lines=[
                OcrLine(text="상품명 단가 수량 금액", confidence=0.95, line_id=0, page_order=0),
                OcrLine(text="양념등심돈까스 16,980 1 16,980", confidence=0.97, line_id=1, page_order=1),
                OcrLine(text="()2", confidence=0.42, line_id=2, page_order=2),
                OcrLine(text="2500000007828 6,480 1 6,480", confidence=0.95, line_id=3, page_order=3),
                OcrLine(text="계 23,460", confidence=0.95, line_id=4, page_order=4),
            ],
            raw_tokens=[],
            quality_score=0.84,
            low_quality_reasons=[],
        )


class StubCollapsedRescueQwenProvider:
    def __init__(self) -> None:
        self.payloads: list[dict] = []

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        self.payloads.append(payload)
        collapsed_rows = payload.get("collapsed_item_name_rows", [])
        if not collapsed_rows:
            return None
        return {
            "rescued_items": [
                {
                    "raw_name": "파프리카(팩)",
                    "normalized_name": "파프리카(팩)",
                    "quantity": 1.0,
                    "unit": "개",
                    "amount": 6480.0,
                    "source_line_ids": [collapsed_rows[0]["name_line_id"], collapsed_rows[0]["detail_line_id"]],
                }
            ]
        }

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        return None


def test_receipt_service_uses_top_strip_date_fallback_when_main_ocr_misses_date(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubBackend()
    service = ReceiptParseService(ocr_backend=backend)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["purchased_at"] == "2023-11-24"
    assert len(backend.calls) == 2
    assert backend.calls[0] == str(image_path)
    assert backend.calls[1] != str(image_path)
    assert parsed["diagnostics"]["date_fallback_used"] is True


def test_receipt_service_uses_top_strip_vendor_fallback_when_main_ocr_misses_vendor(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubBackendWithoutVendor()
    service = ReceiptParseService(ocr_backend=backend)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["vendor_name"] == "세븐일레븐"
    assert len(backend.calls) == 2
    assert parsed["diagnostics"]["vendor_fallback_used"] is True
    assert parsed["diagnostics"]["vendor_fallback_source"] == "top_strip"
    assert parsed["diagnostics"]["date_fallback_used"] is False


def test_receipt_service_uses_qwen_header_rescue_when_date_fallback_still_fails(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubBackendWithoutDate()
    qwen = StubHeaderQwenProvider()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["vendor_name"] == "re-MART"
    assert parsed["purchased_at"] == "2022-04-30"
    assert parsed["diagnostics"]["date_fallback_used"] is False
    assert parsed["diagnostics"]["qwen_header_attempted"] is True
    assert parsed["diagnostics"]["qwen_header_used"] is True
    assert qwen.payloads
    assert qwen.header_calls == 1
    assert qwen.payloads[0]["top_strip_rows"] == ["상단 헤더 깨짐"]


def test_receipt_service_skips_qwen_header_rescue_for_noop_provider(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubBackendWithoutDate()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=NoopQwenProvider())

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["diagnostics"]["qwen_header_attempted"] is False
    assert parsed["diagnostics"]["qwen_header_used"] is False
    assert parsed["diagnostics"]["qwen_header_fallback_reason"] == "provider_missing"


def test_receipt_service_disables_sync_local_qwen_header_rescue_by_default(tmp_path: Path, monkeypatch) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    monkeypatch.delenv("ENABLE_SYNC_LOCAL_QWEN_HEADER_RESCUE", raising=False)
    backend = StubBackendWithoutDate()
    qwen = LocalTransformersQwenProvider(model_id="Qwen/Qwen2.5-1.5B-Instruct", enabled=True)
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["diagnostics"]["qwen_header_attempted"] is False
    assert parsed["diagnostics"]["qwen_header_used"] is False
    assert parsed["diagnostics"]["qwen_header_fallback_reason"] == "disabled_sync_local_qwen_header"


def test_receipt_service_builds_compact_qwen_header_payload(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubLargeHeaderBackend()
    qwen = StubHeaderQwenProvider()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    service.parse({"receipt_image_url": str(image_path)})

    assert qwen.payloads
    payload = qwen.payloads[0]
    assert len(payload["merged_rows"]) <= 2
    assert len(payload["raw_tokens"]) <= 4
    assert len(payload["top_strip_rows"]) <= 4


def test_receipt_service_uses_lower_item_strip_fallback_for_missing_item_name(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (640, 1024), color="white").save(image_path)

    backend = StubBackendWithItemStripRecovery()
    service = ReceiptParseService(ocr_backend=backend)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert any(
        (item.get("normalized_name") or item.get("raw_name")) == "맥주 바이젠 미니"
        and item.get("quantity") == 4.0
        and item.get("amount") == 3960.0
        for item in parsed["items"]
    )
    assert parsed["diagnostics"]["item_strip_fallback_used"] is True
    assert parsed["diagnostics"]["item_strip_fallback_added_count"] == 1
    assert len(backend.calls) == 3


def test_receipt_service_uses_item_strip_fallback_for_missing_gift_item_name(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (640, 1024), color="white").save(image_path)

    backend = StubBackendWithGiftItemStripRecovery()
    service = ReceiptParseService(ocr_backend=backend)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert any(
        item.get("normalized_name") == "투썸로얄밀크티"
        and item.get("quantity") == 1.0
        and item.get("amount") is None
        for item in parsed["items"]
    )
    assert parsed["diagnostics"]["item_strip_fallback_used"] is True
    assert parsed["diagnostics"]["item_strip_fallback_added_count"] == 1
    assert len(backend.calls) == 3


def test_receipt_service_applies_qwen_item_normalization_and_revalidates(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubItemNormalizationBackend()
    qwen = StubItemQwenProvider()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["diagnostics"]["qwen_item_attempted"] is True
    assert parsed["diagnostics"]["qwen_item_used"] is True
    assert parsed["diagnostics"]["qwen_item_fallback_reason"] is None
    assert qwen.payloads
    assert parsed["items"][0]["raw_name"] == "머쉬밀크크릿 ["
    assert parsed["items"][0]["normalized_name"] == "허쉬밀크초콜릿"
    assert parsed["items"][0]["needs_review"] is False
    assert "unresolved_items" not in parsed["review_reasons"]


def test_receipt_service_retries_item_qwen_as_single_item_when_batch_returns_empty(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubMultiItemNormalizationBackend()
    qwen = StubPerItemRetryQwenProvider()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["diagnostics"]["qwen_item_attempted"] is True
    assert parsed["diagnostics"]["qwen_item_used"] is True
    assert len(qwen.payloads) >= 2
    assert len(qwen.payloads[0]["review_items"]) > 1
    assert any(len(payload["review_items"]) == 1 for payload in qwen.payloads[1:])


def test_receipt_service_attempts_qwen_item_rescue_for_collapsed_rows_without_review_items(tmp_path: Path) -> None:
    image_path = tmp_path / "receipt.png"
    Image.new("RGB", (400, 1200), color="white").save(image_path)

    backend = StubCollapsedRescueBackend()
    qwen = StubCollapsedRescueQwenProvider()
    service = ReceiptParseService(ocr_backend=backend, qwen_provider=qwen)

    parsed = service.parse({"receipt_image_url": str(image_path)})

    assert parsed["diagnostics"]["qwen_item_attempted"] is True
    assert parsed["diagnostics"]["qwen_item_used"] is True
    assert parsed["diagnostics"]["qwen_item_rescue_count"] == 1
    assert qwen.payloads
    assert qwen.payloads[0]["review_items"] == []
    assert len(qwen.payloads[0]["collapsed_item_name_rows"]) == 1
    assert any(item.get("raw_name") == "파프리카(팩)" for item in parsed["items"])
    assert "ocr_collapse_item_name" not in parsed["review_reasons"]
    assert "total_mismatch" not in parsed["review_reasons"]
    assert parsed["review_required"] is False
