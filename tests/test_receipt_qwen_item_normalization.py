from __future__ import annotations

from ocr_qwen.qwen import LocalTransformersQwenProvider, NoopQwenProvider
from ocr_qwen.receipts import OcrLine
from ocr_qwen.services import ReceiptParseService


def test_receipt_service_requests_item_qwen_for_low_confidence_items() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    item = {
        "raw_name": "투썸딸기피지",
        "normalized_name": "투썸딸기피치",
        "quantity": 1.0,
        "unit": "개",
        "amount": 2800.0,
        "needs_review": True,
        "review_reason": ["low_confidence"],
    }

    assert service._should_request_qwen_item_normalization(item) is True


def test_receipt_service_skips_qwen_for_clean_unknown_item_without_ocr_signals() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    item = {
        "raw_name": "허쉬쿠키앤크림",
        "normalized_name": None,
        "quantity": 1.0,
        "unit": "개",
        "amount": 1600.0,
        "needs_review": True,
        "review_reason": ["unknown_item"],
    }

    assert service._should_request_qwen_item_normalization(item) is False


def test_receipt_service_requests_qwen_for_suspicious_unknown_item() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    item = {
        "raw_name": "이에",
        "normalized_name": None,
        "quantity": 2.0,
        "unit": "개",
        "amount": 4000.0,
        "needs_review": True,
        "review_reason": ["unknown_item"],
    }

    assert service._should_request_qwen_item_normalization(item) is True


def test_receipt_service_marks_missing_amount_as_qwen_review_target() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    item = {
        "raw_name": "허쉬쿠키앤초코",
        "normalized_name": "허쉬쿠키앤초코",
        "quantity": 1.0,
        "unit": "개",
        "amount": None,
        "needs_review": False,
        "review_reason": [],
    }

    service._recalculate_review_state(item, purchased_at="2023-11-24")

    assert "missing_amount" in item["review_reason"]
    assert item["needs_review"] is True
    assert service._should_request_qwen_item_normalization(item) is True


def test_receipt_service_builds_item_qwen_payload_for_low_confidence_and_missing_amount() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    amount_missing_item = {
        "raw_name": "허쉬쿠키앤초코",
        "normalized_name": "허쉬쿠키앤초코",
        "quantity": 1.0,
        "unit": "개",
        "amount": None,
        "needs_review": False,
        "review_reason": [],
        "source_line_ids": [2],
    }
    service._recalculate_review_state(amount_missing_item, purchased_at="2023-11-24")

    parsed = {
        "vendor_name": "GS25",
        "purchased_at": "2023-11-24",
        "totals": {"payment_amount": 24090.0},
        "diagnostics": {
            "collapsed_item_name_rows": [
                {
                    "name_line_id": 3,
                    "name_text": "()2",
                    "detail_line_id": 4,
                    "detail_text": "2500000007828 6,480 1 6,480",
                }
            ]
        },
        "items": [
            {
                "raw_name": "투썸딸기피지",
                "normalized_name": "투썸딸기피치",
                "quantity": 1.0,
                "unit": "개",
                "amount": 2800.0,
                "confidence": 0.68,
                "match_confidence": 0.68,
                "needs_review": True,
                "review_reason": ["low_confidence"],
                "source_line_ids": [0, 1],
            },
            amount_missing_item,
        ]
    }
    lines = [
        OcrLine(text="투썸딸기피지", confidence=0.68, line_id=0, page_order=0),
        OcrLine(text="1 2,800", confidence=0.96, line_id=1, page_order=1),
        OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.95, line_id=2, page_order=2),
    ]

    payload = service._build_qwen_item_normalization_payload(parsed=parsed, lines=lines)

    assert [item["raw_name"] for item in payload["review_items"]] == [
        "허쉬쿠키앤초코",
        "투썸딸기피지",
    ]
    assert payload["current_vendor_name"] == "GS25"
    assert payload["current_purchased_at"] == "2023-11-24"
    assert payload["known_totals"]["payment_amount"] == 24090.0
    assert payload["review_items"][0]["missing_fields"] == ["amount"]
    assert payload["review_items"][1]["confidence"] == 0.68
    assert payload["review_items"][1]["review_reasons"] == ["low_confidence"]
    assert payload["review_items"][1]["context_lines"] == [
        "투썸딸기피지",
        "1 2,800",
        "허쉬쿠키앤초코 1 증정품",
    ]
    assert payload["collapsed_item_name_rows"] == [
        {
            "name_line_id": 3,
            "name_text": "()2",
            "detail_line_id": 4,
            "detail_text": "2500000007828 6,480 1 6,480",
            "context_lines": [
                "허쉬쿠키앤초코 1 증정품",
                "()2",
                "2500000007828 6,480 1 6,480",
            ],
        }
    ]


def test_receipt_service_allows_qwen_to_replace_normalized_name_for_low_confidence_item() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    parsed = {
        "purchased_at": "2023-11-24",
        "items": [
            {
                "raw_name": "어쉬밀크클릿 [",
                "normalized_name": "우유",
                "quantity": 1.0,
                "unit": "개",
                "amount": 1600.0,
                "needs_review": True,
                "review_reason": ["low_confidence"],
                "source_line_ids": [0],
            }
        ],
    }

    applied = service._apply_qwen_item_normalization(
        parsed,
        {
            "items": [
                {
                    "index": 0,
                    "normalized_name": "허쉬밀크초콜릿",
                }
            ]
        },
    )

    assert applied is True
    assert parsed["items"][0]["normalized_name"] == "허쉬밀크초콜릿"


def test_receipt_service_allows_qwen_to_append_rescued_item() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    parsed = {
        "purchased_at": "2023-11-24",
        "diagnostics": {},
        "items": [
            {
                "raw_name": "양념등심돈까스",
                "normalized_name": "양념등심돈까스",
                "quantity": 1.0,
                "unit": "개",
                "amount": 16980.0,
                "needs_review": False,
                "review_reason": [],
                "source_line_ids": [1, 2],
            }
        ],
    }

    applied = service._apply_qwen_item_normalization(
        parsed,
        {
            "rescued_items": [
                {
                    "raw_name": "파프리카(팩)",
                    "normalized_name": "파프리카(팩)",
                    "quantity": 1.0,
                    "unit": "개",
                    "amount": 6480.0,
                    "source_line_ids": [3, 4],
                }
            ]
        },
    )

    assert applied is True
    assert len(parsed["items"]) == 2
    assert parsed["items"][1]["raw_name"] == "파프리카(팩)"
    assert parsed["items"][1]["parse_pattern"] == "qwen_collapsed_rescue"
    assert parsed["diagnostics"]["qwen_item_rescue_count"] == 1


def test_receipt_service_rejects_implausible_qwen_rescued_item() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    parsed = {
        "purchased_at": "2023-11-24",
        "diagnostics": {},
        "items": [],
    }

    applied = service._apply_qwen_item_normalization(
        parsed,
        {
            "rescued_items": [
                {
                    "raw_name": "()2",
                    "normalized_name": "",
                    "quantity": 2.0,
                    "unit": "1",
                    "amount": 6480.0,
                    "source_line_ids": [4],
                }
            ]
        },
    )

    assert applied is False
    assert parsed["items"] == []
    assert parsed["diagnostics"]["qwen_item_rescue_count"] == 0


def test_local_qwen_item_prompt_instructs_model_to_use_source_and_context_lines() -> None:
    provider = LocalTransformersQwenProvider(enabled=False)

    prompt = provider._build_receipt_item_prompt(
        {
            "review_items": [
                {
                    "index": 0,
                    "raw_name": "투썸딸기피지",
                    "source_lines": ["투썸딸기피지", "1 2,800"],
                    "context_lines": ["허쉬쿠키앤초코 1 증정품"],
                }
            ]
        }
    )

    assert "Use source_lines first" in prompt
    assert "context_lines" in prompt


def test_local_qwen_item_prompt_mentions_collapsed_row_rescue() -> None:
    provider = LocalTransformersQwenProvider(enabled=False)

    prompt = provider._build_receipt_item_prompt(
        {
            "review_items": [],
            "collapsed_item_name_rows": [
                {
                    "name_text": "()2",
                    "detail_text": "2500000007828 6,480 1 6,480",
                    "context_lines": [
                        "양념등심돈까스 16,980 1 16,980",
                        "()2",
                        "2500000007828 6,480 1 6,480",
                    ],
                }
            ],
        }
    )

    assert "collapsed_item_name_rows" in prompt
    assert "rescued_items" in prompt
    assert "2500000007828 6,480 1 6,480" in prompt
    assert "Do not copy collapsed name_text like ()2 as raw_name" in prompt
    assert "unit must be a plausible merchandise unit" in prompt


def test_receipt_service_limits_qwen_review_items_to_ambiguous_subset() -> None:
    service = ReceiptParseService(qwen_provider=NoopQwenProvider())

    parsed = {
        "vendor_name": "GS25",
        "purchased_at": "2023-11-24",
        "totals": {"payment_amount": 24090.0},
        "items": [
            {
                "raw_name": "투썸딸기피치",
                "normalized_name": None,
                "quantity": 1.0,
                "unit": "개",
                "amount": 2800.0,
                "needs_review": True,
                "review_reason": ["unknown_item"],
                "source_line_ids": [10],
            },
            {
                "raw_name": "어쉬밀크클릿 [",
                "normalized_name": "우유",
                "quantity": 1.0,
                "unit": "개",
                "amount": 1600.0,
                "needs_review": True,
                "review_reason": ["low_confidence"],
                "source_line_ids": [11],
            },
            {
                "raw_name": "허쉬쿠키앤초코",
                "normalized_name": None,
                "quantity": 1.0,
                "unit": "개",
                "amount": None,
                "needs_review": True,
                "review_reason": ["unknown_item", "missing_amount"],
                "source_line_ids": [12],
            },
            {
                "raw_name": "화이트빼빼로",
                "normalized_name": None,
                "quantity": 1.0,
                "unit": "개",
                "amount": 1700.0,
                "needs_review": True,
                "review_reason": ["unknown_item"],
                "source_line_ids": [13],
            },
            {
                "raw_name": "이에",
                "normalized_name": None,
                "quantity": 2.0,
                "unit": "개",
                "amount": 4000.0,
                "needs_review": True,
                "review_reason": ["low_confidence", "unknown_item"],
                "source_line_ids": [14],
            },
        ],
    }
    lines = [
        OcrLine(text="투썸딸기피치 1 2,800", confidence=0.88, line_id=10, page_order=10),
        OcrLine(text="어쉬밀크클릿 [ 1,600", confidence=0.62, line_id=11, page_order=11),
        OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.95, line_id=12, page_order=12),
        OcrLine(text="화이트빼빼로 1 1,700", confidence=0.96, line_id=13, page_order=13),
        OcrLine(text="이에 2 4,000", confidence=0.76, line_id=14, page_order=14),
    ]

    payload = service._build_qwen_item_normalization_payload(parsed=parsed, lines=lines)

    assert [item["raw_name"] for item in payload["review_items"]] == [
        "허쉬쿠키앤초코",
        "이에",
        "어쉬밀크클릿 [",
    ]
