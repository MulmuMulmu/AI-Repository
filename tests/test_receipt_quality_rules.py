from __future__ import annotations

from dataclasses import replace

from ocr_qwen.receipts import OcrLine, ReceiptParser, build_default_receipt_rules


def test_parser_extracts_two_items_from_img2_style_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="[만 0H]2020-06-09(화) 20:59:47", confidence=0.94, line_id=0, page_order=0),
            OcrLine(text="상품명 수량 금 액", confidence=0.93, line_id=1, page_order=1),
            OcrLine(text="라라스윗)바널라파인트474 행상", confidence=0.90, line_id=2, page_order=2),
            OcrLine(text="8809599360081 1 6,900", confidence=0.99, line_id=3, page_order=3),
            OcrLine(text="라라스윗)초코파인트474m| 행사", confidence=0.96, line_id=4, page_order=4),
            OcrLine(text="8809599360104 1 6,900", confidence=0.99, line_id=5, page_order=5),
            OcrLine(text="비널볼투보증금 20원", confidence=0.87, line_id=6, page_order=6),
            OcrLine(text="*1171798100209 20", confidence=0.99, line_id=7, page_order=7),
            OcrLine(text="팝세물품가액 12,545", confidence=0.87, line_id=8, page_order=8),
            OcrLine(text="1.255", confidence=0.96, line_id=9, page_order=9),
        ]
    )

    assert result.purchased_at == "2020-06-09"
    assert len(result.items) == 2
    assert [item.amount for item in result.items] == [6900.0, 6900.0]
    assert all("물품가액" not in item.raw_name for item in result.items)
    assert all("보증금" not in item.raw_name for item in result.items)


def test_parser_ignores_coupon_code_and_bag_rows_in_img3_style_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="너몸 단 가 수랑 금", confidence=0.91, line_id=0, page_order=0),
            OcrLine(text="001 재사용봉투(안산시)20*날장 500", confidence=0.96, line_id=1, page_order=1),
            OcrLine(text="*0412598780002 500 1", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="002 속이면한 누룸지(5입)", confidence=0.93, line_id=3, page_order=3),
            OcrLine(text="8801169770207 5,600 1 5,600", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="[말인쿠폰] L -1,680", confidence=0.93, line_id=5, page_order=5),
            OcrLine(text="010(만매코드)913200000307", confidence=0.97, line_id=6, page_order=6),
            OcrLine(text="003속이면한 누룸지(5입)", confidence=0.95, line_id=7, page_order=7),
            OcrLine(text="8801169770207 5,600 7 39,200", confidence=0.99, line_id=8, page_order=8),
            OcrLine(text="[일인쿠폰] 7 -11,760", confidence=0.95, line_id=9, page_order=9),
            OcrLine(text="010(만매코드)913200000307", confidence=0.95, line_id=10, page_order=10),
            OcrLine(text="1ORVO0", confidence=0.70, line_id=11, page_order=11),
            OcrLine(text="8809145590207 990 4 3,960", confidence=0.72, line_id=12, page_order=12),
            OcrLine(text="8801062639854 005 롯데 앤디카페조릿 다크", confidence=0.87, line_id=13, page_order=13),
            OcrLine(text="4,800 1 4.800", confidence=0.92, line_id=14, page_order=14),
        ]
    )

    raw_names = [item.raw_name for item in result.items]

    assert len(result.items) == 3
    assert raw_names == [
        "속이편한 누룽지",
        "속이편한 누룽지",
        "롯데 앤디카페조릿 다크",
    ]
    assert [item.amount for item in result.items] == [5600.0, 39200.0, 4800.0]


def test_parser_cleans_single_line_name_quantity_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤클릴 1 1,600", confidence=0.89, line_id=0, page_order=0),
            OcrLine(text="호가든캔330ML 3,500", confidence=0.96, line_id=1, page_order=1),
            OcrLine(text="아몬드빼빼로 1 1,700", confidence=0.99, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "허쉬쿠키앤클릴",
        "호가든캔330ml",
        "아몬드빼빼로",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0, 1.0]
    assert [item.amount for item in result.items] == [1600.0, 3500.0, 1700.0]
    assert all(item.parse_pattern in {"single_line_name_qty_amount", "single_line_name_amount"} for item in result.items)


def test_parser_handles_gift_item_rows_without_treating_quantity_as_amount() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.98, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "허쉬쿠키앤초코"
    assert result.items[0].quantity == 1.0
    assert result.items[0].unit == "개"
    assert result.items[0].amount is None
    assert result.items[0].parse_pattern == "single_line_gift"


def test_parser_skips_notice_block_and_parses_se_full_style_item_section() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="재미있는 일상 플랫폼 GS25", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="GS25", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="6032785687", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="2023/11/24 1층", confidence=0.98, line_id=3, page_order=3),
            OcrLine(text="NO:17509", confidence=0.98, line_id=4, page_order=4),
            OcrLine(text="반드시 영수증을 지참하셔야 하며,", confidence=0.95, line_id=5, page_order=5),
            OcrLine(text="카드결제는 30일 이내", confidence=0.95, line_id=6, page_order=6),
            OcrLine(text="카드와 영수증 지참 시 가능합니다", confidence=0.95, line_id=7, page_order=7),
            OcrLine(text="허쉬쿠키앤크림 1 1,600", confidence=0.90, line_id=8, page_order=8),
            OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.95, line_id=9, page_order=9),
            OcrLine(text="호가든캔330ML 1 3,500", confidence=0.96, line_id=10, page_order=10),
            OcrLine(text="아몬드코볼 1 2,000", confidence=0.94, line_id=11, page_order=11),
            OcrLine(text="합계수량/금액 14 24,090", confidence=0.99, line_id=12, page_order=12),
            OcrLine(text="과세매출 18,726", confidence=0.99, line_id=13, page_order=13),
        ]
    )

    assert result.purchased_at == "2023-11-24"
    assert [item.raw_name for item in result.items] == [
        "허쉬쿠키앤크림",
        "허쉬쿠키앤초코",
        "호가든캔330ml",
        "아몬드초코볼",
    ]
    assert result.items[0].amount == 1600.0
    assert result.items[1].amount is None
    assert result.items[2].amount == 3500.0
    assert result.totals["total"] == 24090.0


def test_parser_prefers_sale_date_and_store_token_over_card_slip_lines() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="재미있는 일상 플랫폼 GS25", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="GS25", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="∠023/ 11/24 1층", confidence=0.96, line_id=2, page_order=2),
            OcrLine(text="카드결제는 30일(12월24일)이내", confidence=0.95, line_id=3, page_order=3),
            OcrLine(text="합계수량/금액 14 24,090", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="신용카드 전표(고객용)", confidence=0.98, line_id=5, page_order=5),
            OcrLine(text="23/11/2500:01:04", confidence=0.97, line_id=6, page_order=6),
        ]
    )

    assert result.vendor_name == "GS25"
    assert result.purchased_at == "2023-11-24"
    assert result.totals["total"] == 24090.0
    assert result.totals["payment_amount"] == 24090.0


def test_parser_recovers_vendor_from_7eleven_website_header_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="세계1등 문이", confidence=0.71, line_id=0, page_order=0),
            OcrLine(text="[주)코리아세븐 www7 eleven co kr", confidence=0.81, line_id=1, page_order=1),
            OcrLine(text="[판매]2020-06-09 (화) 20:59:47", confidence=0.94, line_id=2, page_order=2),
            OcrLine(text="라라스윗 바닐라파인트474 1 6,900", confidence=0.93, line_id=3, page_order=3),
        ]
    )

    assert result.vendor_name == "7-ELEVEN"


def test_parser_extracts_purchase_amount_as_payment_total() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="구매금액 49,060", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="부 가 세 1,232", confidence=0.98, line_id=1, page_order=1),
        ]
    )

    assert result.totals["payment_amount"] == 49060.0
    assert result.totals["tax"] == 1232.0


def test_parser_detects_name_and_short_code_detail_pairs_without_explicit_header() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="192205 1.000 2 2,000", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="002오뚜기 백도", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="200051 790 2 1,580", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="003오뚜기 황도", confidence=0.97, line_id=3, page_order=3),
            OcrLine(text="190160 1,600 2 3,200", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="012 45도 과일잼 딸기", confidence=0.92, line_id=5, page_order=5),
            OcrLine(text="200168 3.050 1 3,050", confidence=0.95, line_id=6, page_order=6),
            OcrLine(text="계: 80,220원", confidence=0.97, line_id=7, page_order=7),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "오뚜기 백도",
        "오뚜기 황도",
        "45도 과일잼 딸기",
    ]
    assert [item.amount for item in result.items] == [1580.0, 3200.0, 3050.0]
    assert all(item.parse_pattern == "name_then_code_numeric_detail" for item in result.items)


def test_parser_opens_item_window_for_full_image_excerpt_with_leading_numeric_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="192205 1.000 2 2,000", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="002오뚜기 백도", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="200051 790 2 1,580", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="003오뚜기 황도", confidence=0.97, line_id=3, page_order=3),
            OcrLine(text="190160 1,600 2 3,200", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="004 오뚜기 진진파라 1,800", confidence=0.94, line_id=5, page_order=5),
            OcrLine(text="220197 006 2", confidence=0.99, line_id=6, page_order=6),
            OcrLine(text="150178 16,630 1 16,630", confidence=0.88, line_id=7, page_order=7),
            OcrLine(text="008 시스테마스텐다드칫속", confidence=0.90, line_id=8, page_order=8),
            OcrLine(text="130211 1,440 1 1,440", confidence=0.93, line_id=9, page_order=9),
            OcrLine(text="계: 80,220원", confidence=0.97, line_id=10, page_order=10),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "오뚜기 백도",
        "오뚜기 황도",
    ]
    assert result.totals["total"] == 80220.0
    assert all(not item.raw_name.startswith("계") for item in result.items)


def test_parser_skips_incomplete_detail_rows_and_low_confidence_gibberish_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="004 오뚜기 진진파라 1,800", confidence=0.94, line_id=0, page_order=0),
            OcrLine(text="220197 006 2", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="0매0연ㅋ무매ㅋ링링물백위매피", confidence=0.43, line_id=2, page_order=2),
            OcrLine(text="150178 16,630 1 16,630", confidence=0.88, line_id=3, page_order=3),
            OcrLine(text="008 시스테마스텐다드칫속", confidence=0.90, line_id=4, page_order=4),
            OcrLine(text="130211 1,440 1 1,440", confidence=0.93, line_id=5, page_order=5),
            OcrLine(text="012 45도 과일잼 딸기", confidence=0.92, line_id=6, page_order=6),
            OcrLine(text="200168 3.050 1 3,050", confidence=0.95, line_id=7, page_order=7),
            OcrLine(text="023 이클립스 페퍼민트향 34g", confidence=0.92, line_id=8, page_order=8),
            OcrLine(text="220245 770 1 770", confidence=0.99, line_id=9, page_order=9),
            OcrLine(text="계: 80,220원", confidence=0.97, line_id=10, page_order=10),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "45도 과일잼 딸기",
        "이클립스 페퍼민트향 34g",
    ]
    assert [item.amount for item in result.items] == [3050.0, 770.0]


def test_parser_does_not_treat_trailing_pack_size_as_price() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="024 미클립스 피치향 34g", confidence=0.99, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "미클립스 피치향 34g"
    assert result.items[0].amount is None


def test_parser_inferrs_quantity_from_code_price_placeholder_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="*한돈) 생목살(구이용)", confidence=0.93, line_id=0, page_order=0),
            OcrLine(text="200078 13,450 - 13,450", confidence=0.88, line_id=1, page_order=1),
            OcrLine(text="*청양고추", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="202240 1,390 - 1,390", confidence=0.82, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "*한돈) 생목살",
        "*청양고추",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0]
    assert [item.amount for item in result.items] == [13450.0, 1390.0]
    assert all(item.parse_pattern == "name_then_code_amount_inferred_qty" for item in result.items)


def test_parser_inferrs_quantity_from_code_price_unicode_dash_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="*적상추", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="202210 1,900 — 1,900", confidence=0.82, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "*적상추"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount == 1900.0
    assert result.items[0].parse_pattern == "name_then_code_amount_inferred_qty"


def test_parser_filters_non_food_household_and_electronics_items() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="OnlyPrice 삼중스편지 수세미 2,990", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="구글홈미니 29,900", confidence=0.93, line_id=1, page_order=1),
            OcrLine(text="시스테마스텐다드칫속 1,440", confidence=0.90, line_id=2, page_order=2),
        ]
    )

    assert result.items == []


def test_parser_keeps_food_product_rows_after_rule_updates() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="농심 너구리 컵 3,750", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="청정원 순창 찰고추장12,780", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="갈바니'리코타치느4 8,900", confidence=0.91, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "농심 너구리 컵",
        "청정원 순창 찰고추장12,780",
        "갈바니'리코타치느4",
    ]


def test_parser_does_not_treat_gibberish_header_line_as_vendor() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="Co:z01e1(5 108-t0-z707", confidence=0.72, line_id=0, page_order=0),
            OcrLine(text="*한돈) 생목살(구이용)", confidence=0.93, line_id=1, page_order=1),
            OcrLine(text="200078 13,450 - 13,450", confidence=0.88, line_id=2, page_order=2),
        ]
    )

    assert result.vendor_name is None
    assert len(result.items) == 1
    assert result.items[0].raw_name == "*한돈) 생목살"


def test_parser_does_not_treat_short_alpha_fragment_as_vendor() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="Ra", confidence=0.16, line_id=0, page_order=0),
            OcrLine(text="*한돈) 생목살(구이용)", confidence=0.93, line_id=1, page_order=1),
            OcrLine(text="200078 13,450 - 13,450", confidence=0.88, line_id=2, page_order=2),
        ]
    )

    assert result.vendor_name is None
    assert len(result.items) == 1
    assert result.items[0].raw_name == "*한돈) 생목살"


def test_parser_skips_negative_adjustment_like_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="[(야] 7 -11,760", confidence=0.86, line_id=0, page_order=0),
        ]
    )

    assert result.items == []


def test_parser_cleans_common_ocr_noise_in_product_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="(CJ)큰사각했반300g", confidence=0.97, line_id=0, page_order=0),
            OcrLine(text="8801007054186 2,500 - 2,500", confidence=0.90, line_id=1, page_order=1),
            OcrLine(text="코카)코카콜라350m]350m1", confidence=0.93, line_id=2, page_order=2),
            OcrLine(text="8801094017200 1,500 - 1,500", confidence=0.79, line_id=3, page_order=3),
            OcrLine(text="^진로)(뉴트로)소주(병)360m]", confidence=0.96, line_id=4, page_order=4),
            OcrLine(text="8801048101023 1,650 - 1,650", confidence=0.89, line_id=5, page_order=5),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "큰사각햇반300g",
        "코카콜라350ml",
        "진로 소주 360ml",
    ]
    assert [item.amount for item in result.items] == [2500.0, 1500.0, 1650.0]


def test_parser_cleans_additional_real_world_ocr_typos_in_product_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="라라스윗)바널라파인트474 행상", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="8809599360081 1 6,900", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="003속이면한 누룸지(5입)", confidence=0.95, line_id=2, page_order=2),
            OcrLine(text="8801169770207 5,600 7 39,200", confidence=0.99, line_id=3, page_order=3),
            OcrLine(text="호가든캔330ML 1 3,500", confidence=0.96, line_id=4, page_order=4),
            OcrLine(text="아몬드코볼 1 2,000", confidence=0.94, line_id=5, page_order=5),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "라라스윗 바닐라파인트474",
        "속이편한 누룽지",
        "호가든캔330ml",
        "아몬드초코볼",
    ]
    assert [item.amount for item in result.items] == [6900.0, 39200.0, 3500.0, 2000.0]


def test_parser_uses_injected_rules_for_noise_filtering_and_alias_normalization() -> None:
    rules = build_default_receipt_rules()
    custom_rules = replace(
        rules,
        noise_keywords=rules.noise_keywords + ("샘플문구",),
        ocr_canonical_aliases={**rules.ocr_canonical_aliases, "바널라": "커스텀바닐라"},
        item_rules=rules.item_rules + ((r"커스텀바닐라", "커스텀바닐라", "dairy"),),
    )
    parser = ReceiptParser(rules=custom_rules)

    result = parser.parse_lines(
        [
            OcrLine(text="샘플문구 12345", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="라라스윗)바널라파인트474 행상", confidence=0.90, line_id=1, page_order=1),
            OcrLine(text="8809599360081 1 6,900", confidence=0.99, line_id=2, page_order=2),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].normalized_name == "커스텀바닐라"
    assert result.items[0].amount == 6900.0
    assert all("샘플문구" not in item.raw_name for item in result.items)


def test_parser_uses_injected_footer_keywords_to_stop_item_window() -> None:
    rules = build_default_receipt_rules()
    custom_rules = replace(
        rules,
        footer_keywords=rules.footer_keywords + ("정산완료",),
        payment_keywords=rules.payment_keywords + ("정산완료",),
    )
    parser = ReceiptParser(rules=custom_rules)

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 수량 금액", confidence=0.94, line_id=0, page_order=0),
            OcrLine(text="라라스윗 바닐라파인트474 1 6,900", confidence=0.95, line_id=1, page_order=1),
            OcrLine(text="정산완료 24,090", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="허쉬쿠키앤초코 1 증정품", confidence=0.96, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == ["라라스윗 바닐라파인트474"]
    assert result.totals["payment_amount"] == 24090.0
