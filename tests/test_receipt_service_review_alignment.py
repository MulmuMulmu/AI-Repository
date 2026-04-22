from __future__ import annotations

from ocr_qwen.services import ReceiptParseService
from ocr_qwen.services import OcrExtraction


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


def test_service_finalize_parse_result_uses_subtotal_plus_tax_fallback() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "purchased_at": "2020-06-09",
        "vendor_name": "7-ELEVEN",
        "items": [
            {"normalized_name": "라라스윗 바닐라파인트474ml", "quantity": 1.0, "unit": "개", "amount": 6900.0, "needs_review": False},
            {"normalized_name": "라라스윗 초코파인트474ml", "quantity": 1.0, "unit": "개", "amount": 6900.0, "needs_review": False},
        ],
        "totals": {
            "subtotal": 12545.0,
            "tax": 1255.0,
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


def test_service_finalize_parse_result_allows_partial_receipt_with_noisy_rows_before_item_header() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": None,
        "items": [
            {"raw_name": "*한돈) 생목살", "quantity": 1.0, "unit": "개", "amount": 13450.0, "needs_review": False, "review_reason": []},
            {"raw_name": "*한돈)벌집 삼겹살", "quantity": 1.0, "unit": "개", "amount": 15970.0, "needs_review": False, "review_reason": []},
            {"raw_name": "*청양고추", "normalized_name": "고추", "quantity": 1.0, "unit": "개", "amount": 1390.0, "needs_review": False, "review_reason": []},
            {"raw_name": "*적상추", "quantity": 1.0, "unit": "개", "amount": 1900.0, "needs_review": False, "review_reason": []},
            {"raw_name": "큰사각햇반300g", "quantity": 1.0, "unit": "개", "amount": 2500.0, "needs_review": False, "review_reason": []},
            {"raw_name": "햇반200g", "normalized_name": "햇반", "quantity": 1.0, "unit": "개", "amount": 1600.0, "needs_review": False, "review_reason": []},
            {"raw_name": "콤비부어스트4가지맛285g", "quantity": 1.0, "unit": "개", "amount": 6300.0, "needs_review": False, "review_reason": []},
            {"raw_name": "코카콜라350ml", "quantity": 1.0, "unit": "개", "amount": 1500.0, "needs_review": False, "review_reason": []},
            {"raw_name": "진로 소주 360ml", "quantity": 1.0, "unit": "개", "amount": 1650.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {
            "payment_amount": 49060.0,
            "tax": 1232.0,
        },
        "ocr_texts": [
            {"line_id": 0, "text": "Co:z01e1(5 108-t0-z707"},
            {"line_id": 1, "text": "Ra"},
            {"line_id": 2, "text": "상품 1C금 수량"},
            {"line_id": 3, "text": "*한돈) 생목살(구이용)"},
            {"line_id": 4, "text": "200078 13,450 - 13,450"},
            {"line_id": 5, "text": "*종량10L(재사용봉투날장)"},
            {"line_id": 6, "text": "2908144263092 180 I 180"},
            {"line_id": 7, "text": "*한돈)벌집 삼겹살(암태지)"},
            {"line_id": 8, "text": "200074 15,970 | 15,970"},
            {"line_id": 24, "text": "구매금액 49,060"},
            {"line_id": 30, "text": "부 가 세 1,232"},
        ],
        "review_reasons": [],
        "diagnostics": {"quality_score": 0.4194},
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["partial_receipt"] is True
    assert parsed["review_required"] is False
    assert "missing_vendor_name" not in parsed["review_reasons"]
    assert "missing_purchased_at" not in parsed["review_reasons"]
    assert "total_mismatch" not in parsed["review_reasons"]


def test_service_finalize_parse_result_marks_orphan_item_detail_in_partial_receipt() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": "2022-04-30",
        "items": [
            {"raw_name": "*한돈) 생목살", "quantity": 1.0, "unit": "개", "amount": 13450.0, "needs_review": False, "review_reason": []},
            {"raw_name": "진로 소주 360ml", "quantity": 1.0, "unit": "개", "amount": 1650.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {
            "payment_amount": 49060.0,
            "tax": 1232.0,
        },
        "ocr_texts": [
            {"line_id": 2, "text": "상품명 단 가 수량 금 액"},
            {"line_id": 3, "text": "*한돈) 생목살(구이용)"},
            {"line_id": 4, "text": "200078 13,450 - 13,450"},
            {"line_id": 5, "text": "*종량10L(재사용봉투날장)"},
            {"line_id": 6, "text": "2908144263092 180 I 180"},
            {"line_id": 21, "text": "^진로)(뉴트로)소주(병)360m]"},
            {"line_id": 22, "text": "8801048101023 1,650 - 1,650"},
            {"line_id": 23, "text": "202037 2,620 1 2,620"},
            {"line_id": 24, "text": "구매금액 49,060"},
            {"line_id": 30, "text": "부 가 세 1,232"},
        ],
        "review_reasons": [],
        "diagnostics": {
            "quality_score": 0.4194,
            "section_map": {
                "2": "header",
                "3": "items",
                "4": "items",
                "5": "ignored",
                "6": "items",
                "21": "items",
                "22": "items",
                "23": "items",
                "24": "payment",
                "30": "totals",
            },
            "consumed_line_ids": [3, 4, 21, 22],
        },
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["orphan_item_detail_count"] == 1
    assert "orphan_item_detail" in parsed["review_reasons"]
    assert parsed["review_required"] is True


def test_service_finalize_parse_result_marks_collapsed_item_name_row_for_review() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "vendor_name": None,
        "purchased_at": None,
        "items": [
            {"raw_name": "양념등심돈까스", "quantity": 1.0, "unit": "개", "amount": 16980.0, "needs_review": False, "review_reason": []},
        ],
        "totals": {},
        "ocr_texts": [
            {"line_id": 0, "text": "상품명 단가 수량 금액"},
            {"line_id": 1, "text": "양념등심돈까스 16,980 1 16,980"},
            {"line_id": 2, "text": "()2"},
            {"line_id": 3, "text": "2500000007828 6,480 1 6,480"},
        ],
        "review_reasons": [],
        "diagnostics": {
            "quality_score": 1.0,
            "section_map": {
                "0": "header",
                "1": "items",
                "2": "items",
                "3": "items",
            },
            "consumed_line_ids": [1],
        },
        "confidence": 1.0,
    }

    service._finalize_parse_result(parsed, low_quality_reasons=[])

    assert parsed["diagnostics"]["collapsed_item_name_count"] == 1
    assert parsed["diagnostics"]["collapsed_item_name_rows"] == [
        {
            "name_line_id": 2,
            "name_text": "()2",
            "detail_line_id": 3,
            "detail_text": "2500000007828 6,480 1 6,480",
        }
    ]
    assert "ocr_collapse_item_name" in parsed["review_reasons"]
    assert parsed["review_required"] is True


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


def test_service_does_not_request_placeholder_item_strip_fallback_for_dense_receipt() -> None:
    service = ReceiptParseService(ocr_backend=object())
    parsed = {
        "items": [{"raw_name": f"item-{index}"} for index in range(9)],
        "ocr_texts": [
            {"line_id": 0, "text": "상품명 단가 수량 금액"},
            {"line_id": 1, "text": "011 볶음아몬드"},
            {"line_id": 2, "text": "230298 5,210 1 5,210"},
            {"line_id": 3, "text": "012 45도 과일잼 딸기"},
            {"line_id": 4, "text": "200168 3,050 1 3,050"},
            {"line_id": 5, "text": "013 프로틴 초코스틱 아몬드맛"},
            {"line_id": 6, "text": "220029 2,750 1 2,750"},
            {"line_id": 7, "text": "00CB2IOU0 3.870"},
            {"line_id": 8, "text": "210155 3,870 1"},
            {"line_id": 9, "text": "024 미클립스 피치향 34g"},
            {"line_id": 10, "text": "210032 790 T 790"},
        ],
        "diagnostics": {
            "section_map": {
                "0": "header",
                "1": "items",
                "2": "items",
                "3": "items",
                "4": "items",
                "5": "items",
                "6": "items",
                "7": "items",
                "8": "items",
                "9": "items",
                "10": "items",
            },
            "consumed_line_ids": [1, 2, 3, 4, 5, 6],
        },
    }
    extraction = OcrExtraction(lines=[], quality_score=0.5, low_quality_reasons=["low_quality"])

    gap = service._detect_item_strip_gap(parsed, extraction=extraction, source_type="receipt_image_url")

    assert gap is None
