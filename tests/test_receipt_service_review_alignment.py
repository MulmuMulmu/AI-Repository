from __future__ import annotations

from ocr_qwen.services import ReceiptParseService


def test_service_recalculate_review_state_keeps_unknown_item_without_forcing_review() -> None:
    service = ReceiptParseService(ocr_backend=object())
    item = {
        "raw_name": "희귀한상품A",
        "normalized_name": None,
        "quantity": 1.0,
        "unit": "개",
        "amount": 2800.0,
        "review_reason": [],
        "needs_review": False,
    }

    service._recalculate_review_state(item, purchased_at="2023-11-24")

    assert item["review_reason"] == ["unknown_item"]
    assert item["needs_review"] is False


def test_service_recalculate_review_state_keeps_low_confidence_complete_item_without_forcing_review() -> None:
    service = ReceiptParseService(ocr_backend=object())
    item = {
        "raw_name": "허쉬밀크초콜릿",
        "normalized_name": "허쉬밀크초콜릿",
        "quantity": 1.0,
        "unit": "개",
        "amount": 1600.0,
        "review_reason": ["low_confidence"],
        "needs_review": True,
    }

    service._recalculate_review_state(item, purchased_at="2023-11-24")

    assert item["review_reason"] == ["low_confidence"]
    assert item["needs_review"] is False


def test_service_recalculate_review_state_does_not_require_amount_for_gift_item() -> None:
    service = ReceiptParseService(ocr_backend=object())
    item = {
        "raw_name": "허쉬쿠키앤초코",
        "normalized_name": "허쉬쿠키앤초코",
        "quantity": 1.0,
        "unit": "개",
        "amount": None,
        "parse_pattern": "single_line_gift",
        "review_reason": [],
        "needs_review": False,
    }

    service._recalculate_review_state(item, purchased_at="2023-11-24")

    assert item["review_reason"] == []
    assert item["needs_review"] is False


def test_service_recalculate_review_state_keeps_missing_date_without_item_level_unresolved() -> None:
    service = ReceiptParseService(ocr_backend=object())
    item = {
        "raw_name": "양파",
        "normalized_name": "양파",
        "quantity": 1.0,
        "unit": "개",
        "amount": 1500.0,
        "review_reason": [],
        "needs_review": False,
    }

    service._recalculate_review_state(item, purchased_at=None)

    assert item["review_reason"] == ["missing_purchased_at"]
    assert item["needs_review"] is False


def test_service_finalize_parse_result_uses_subtotal_before_payment_total() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": "GS25",
        "purchased_at": "2023-01-01",
        "items": [
            {"normalized_name": "A", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": False},
            {"normalized_name": "B", "quantity": 1.0, "unit": "개", "amount": 3200.0, "needs_review": False},
            {"normalized_name": "C", "quantity": 1.0, "unit": "개", "amount": 10500.0, "needs_review": False},
        ],
        "totals": {
            "subtotal": 15300.0,
            "tax": 1530.0,
            "payment_amount": 16830.0,
            "total": 16830.0,
        },
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "total_mismatch" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_uses_payment_minus_tax_fallback() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "purchased_at": "2023-01-01",
        "vendor_name": "GS25",
        "items": [
            {"normalized_name": "A", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": False},
            {"normalized_name": "B", "quantity": 1.0, "unit": "개", "amount": 3200.0, "needs_review": False},
            {"normalized_name": "C", "quantity": 1.0, "unit": "개", "amount": 10500.0, "needs_review": False},
        ],
        "totals": {
            "tax": 1530.0,
            "payment_amount": 16830.0,
            "total": 16830.0,
        },
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "total_mismatch" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_marks_missing_vendor_name_for_review() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": "2023-01-01",
        "items": [
            {"normalized_name": "A", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": False},
        ],
        "totals": {
            "payment_amount": 1600.0,
        },
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "missing_vendor_name" in parsed["review_reasons"]
    assert parsed["review_required"] is True


def test_service_finalize_parse_result_uses_discount_lines_to_avoid_total_mismatch() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": "홈플러스",
        "purchased_at": "2023-01-01",
        "items": [
            {"normalized_name": "A", "quantity": 1.0, "unit": "개", "amount": 16980.0, "needs_review": False},
            {"normalized_name": "B", "quantity": 1.0, "unit": "개", "amount": 6480.0, "needs_review": False},
            {"normalized_name": "C", "quantity": 1.0, "unit": "개", "amount": 17980.0, "needs_review": False},
            {"normalized_name": "D", "quantity": 1.0, "unit": "개", "amount": 27980.0, "needs_review": False},
            {"normalized_name": "E", "quantity": 1.0, "unit": "개", "amount": 6780.0, "needs_review": False},
            {"normalized_name": "F", "quantity": 1.0, "unit": "개", "amount": 9980.0, "needs_review": False},
            {"normalized_name": "G", "quantity": 1.0, "unit": "개", "amount": 6680.0, "needs_review": False},
            {"normalized_name": "H", "quantity": 1.0, "unit": "개", "amount": 8480.0, "needs_review": False},
            {"normalized_name": "I", "quantity": 1.0, "unit": "개", "amount": 11980.0, "needs_review": False},
            {"normalized_name": "J", "quantity": 1.0, "unit": "개", "amount": 4780.0, "needs_review": False},
            {"normalized_name": "K", "quantity": 1.0, "unit": "개", "amount": 5980.0, "needs_review": False},
        ],
        "totals": {
            "total": 117580.0,
            "payment_amount": 112580.0,
        },
        "ocr_texts": [
            {"text": "2021 채소S-POINT -1,500"},
            {"text": "포인트에누리행사 -2,500"},
            {"text": "가공에누리(전점) -2,500"},
            {"text": "삼성카드할인 -5,000"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "total_mismatch" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_allows_partial_receipt_without_vendor_or_date() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": None,
        "items": [
            {"normalized_name": "양파", "quantity": 1.0, "unit": "개", "amount": 1500.0, "needs_review": True, "review_reason": ["missing_purchased_at"]},
            {"normalized_name": "대파", "quantity": 1.0, "unit": "개", "amount": 2500.0, "needs_review": True, "review_reason": ["missing_purchased_at"]},
        ],
        "totals": {
            "payment_amount": 4000.0,
        },
        "ocr_texts": [
            {"text": "상품명 단 가 수량 금 액"},
            {"text": "양파"},
            {"text": "1,500 1 1,500"},
            {"text": "대파"},
            {"text": "2,500 1 2,500"},
            {"text": "결제대상금액 4,000"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["partial_receipt"] is True
    assert "missing_vendor_name" not in parsed["review_reasons"]
    assert "missing_purchased_at" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_allows_partial_receipt_without_item_header() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": None,
        "items": [
            {"normalized_name": "오뚜기 백도", "quantity": 2.0, "unit": "개", "amount": 1580.0, "needs_review": False},
            {"normalized_name": "오뚜기 황도", "quantity": 2.0, "unit": "개", "amount": 3200.0, "needs_review": False},
            {"normalized_name": "볶음아몬드", "quantity": 1.0, "unit": "개", "amount": 5210.0, "needs_review": False},
            {"normalized_name": "게리치즈크래커", "quantity": 1.0, "unit": "개", "amount": 1990.0, "needs_review": False},
        ],
        "totals": {
            "payment_amount": 80220.0,
            "total": 80220.0,
        },
        "ocr_texts": [
            {"line_id": 0, "text": "002 오뚜기 백도"},
            {"line_id": 1, "text": "790 2 1,580"},
            {"line_id": 2, "text": "003 오뚜기 황도"},
            {"line_id": 3, "text": "1,600 2 3,200"},
            {"line_id": 4, "text": "합 계: 80,220원"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["partial_receipt"] is True
    assert "missing_vendor_name" not in parsed["review_reasons"]
    assert "missing_purchased_at" not in parsed["review_reasons"]


def test_service_finalize_parse_result_uses_unconsumed_item_amount_to_avoid_total_mismatch() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": "GS25",
        "purchased_at": "2023-11-24",
        "items": [
            {"normalized_name": "투썸딸기피치", "quantity": 1.0, "unit": "개", "amount": 2800.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "허쉬쿠키앤크림", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "허쉬밀크초콜릿", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": True, "review_reason": ["low_confidence"]},
                {"normalized_name": "허쉬쿠키앤초코", "quantity": 1.0, "unit": "개", "amount": None, "needs_review": False, "review_reason": [], "parse_pattern": "single_line_gift"},
            {"normalized_name": "호가든캔330ml", "quantity": 1.0, "unit": "개", "amount": 3500.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "아몬드초코볼", "quantity": 1.0, "unit": "개", "amount": 2000.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "화이트빼빼로", "quantity": 1.0, "unit": "개", "amount": 1700.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "초코빼빼로", "quantity": 1.0, "unit": "개", "amount": 1700.0, "needs_review": True, "review_reason": ["low_confidence"]},
            {"normalized_name": "호레오화이트", "quantity": 2.0, "unit": "개", "amount": 4000.0, "needs_review": True, "review_reason": ["low_confidence"]},
                {"normalized_name": "투썸로얄밀크티", "quantity": 1.0, "unit": "개", "amount": None, "needs_review": False, "review_reason": [], "parse_pattern": "single_line_gift"},
        ],
        "totals": {
            "total": 24090.0,
            "tax": 1874.0,
            "payment_amount": 24090.0,
        },
        "ocr_texts": [
            {"line_id": 8, "text": "1 증정풍"},
            {"line_id": 16, "text": "1 1,700"},
            {"line_id": 20, "text": "*재사용봉투20L 1 490"},
            {"line_id": 21, "text": "*3l() 1 3,000"},
        ],
        "review_reasons": [],
        "diagnostics": {
            "quality_score": 1.0,
            "section_map": {"20": "ignored", "21": "items"},
            "consumed_line_ids": [],
        },
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "total_mismatch" not in parsed["review_reasons"]
    assert "unresolved_items" not in parsed["review_reasons"]


def test_service_finalize_parse_result_allows_missing_vendor_for_item_strip_recovered_receipt() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": "2015-01-20",
        "items": [
            {"normalized_name": "속이편한 누룽지", "quantity": 1.0, "unit": "개", "amount": 5600.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "맥주 바이젠 미니", "quantity": 4.0, "unit": "개", "amount": 3960.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {},
        "ocr_texts": [
            {"line_id": 0, "text": "속이편한 누룽지(5입)"},
            {"line_id": 1, "text": "5,600 1 5,600"},
            {"line_id": 2, "text": "맥주 바이젠 미니"},
            {"line_id": 3, "text": "990 4 3,960"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0, "item_strip_fallback_used": True},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "missing_vendor_name" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_allows_missing_vendor_for_single_item_payment_receipt() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": "2023-06-08",
        "items": [
            {"normalized_name": "스팀덱 64GB", "quantity": 1.0, "unit": "개", "amount": 589000.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {
            "payment_amount": 589000.0,
        },
        "ocr_texts": [
            {"line_id": 0, "text": "전자제품 영수증"},
            {"line_id": 1, "text": "거래일자 2023-06-08"},
            {"line_id": 2, "text": "품목"},
            {"line_id": 3, "text": "스팀덱 64GB 589,000"},
            {"line_id": 4, "text": "카드결제 589,000"},
            {"line_id": 5, "text": "승인번호 123456"},
            {"line_id": 6, "text": "고객용"},
            {"line_id": 7, "text": "감사합니다"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 1.0},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert "missing_vendor_name" not in parsed["review_reasons"]
    assert parsed["review_required"] is False


def test_service_finalize_parse_result_ignores_tax_and_loyalty_rows_from_unconsumed_amount_total() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": "롯데마트",
        "purchased_at": "2019-11-25",
        "items": [
            {"normalized_name": "A", "quantity": 1.0, "unit": "개", "amount": 2500.0, "needs_review": False, "review_reason": []},
            {"normalized_name": "B", "quantity": 1.0, "unit": "개", "amount": 2500.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {
            "payment_amount": 6000.0,
        },
        "ocr_texts": [
            {"line_id": 0, "text": "상품명 단가 수량 금액"},
            {"line_id": 1, "text": "A 2,500 1 2,500"},
            {"line_id": 2, "text": "B 2,500 1 2,500"},
            {"line_id": 3, "text": "OnlyPrice 삼중스펀지 수세미"},
            {"line_id": 4, "text": "1,000 1 1,000"},
            {"line_id": 5, "text": "부 I 가 세 819"},
            {"line_id": 6, "text": "은*학 고객님: 최우수단계(0.1%적립)"},
        ],
        "review_reasons": [],
        "diagnostics": {
            "quality_score": 1.0,
            "section_map": {
                "0": "header",
                "1": "items",
                "2": "items",
                "3": "items",
                "4": "items",
                "5": "ignored",
                "6": "ignored",
            },
            "consumed_line_ids": [1, 2],
        },
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["unconsumed_item_amount_total"] == 1000.0
    assert "total_mismatch" not in parsed["review_reasons"]
