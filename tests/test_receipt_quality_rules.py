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


def test_parser_recovers_homeplus_vendor_from_website_header_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="Home plus 춤플러스", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="www.homeplus.co.kr", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="2014/07/03 13:29:53", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="크라운참쌀선과293G 4,320 1 4,320", confidence=0.95, line_id=3, page_order=3),
        ]
    )

    assert result.vendor_name == "홈플러스"


def test_parser_normalizes_punctuated_7eleven_vendor_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="7.-ELEVEN", confidence=0.82, line_id=0, page_order=0),
            OcrLine(text="[주문]2023-01-01 18:59", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="허쉬쿠키앤크림 1 1,600", confidence=0.97, line_id=2, page_order=2),
        ]
    )

    assert result.vendor_name == "7-ELEVEN"


def test_parser_normalizes_comma_punctuated_7eleven_vendor_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="7,-ELEVEN", confidence=0.82, line_id=0, page_order=0),
            OcrLine(text="[주문]2023-01-01 18:59", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="허쉬쿠키앤크림 1 1,600", confidence=0.97, line_id=2, page_order=2),
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


def test_parser_extracts_payment_amount_from_payment_target_amount_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="계 117,580", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="결제대상금액 112,580", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert result.totals["total"] == 117580.0
    assert result.totals["payment_amount"] == 112580.0


def test_parser_rejects_gibberish_vendor_fallback_without_store_hint() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="CDL Frlo.DDHa RERR", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="[P 03 2023-08-11 12:46", confidence=0.86, line_id=1, page_order=1),
            OcrLine(text="상품명 금액", confidence=0.90, line_id=2, page_order=2),
            OcrLine(text="칠성사이다 제로 500ml 3,560", confidence=0.90, line_id=3, page_order=3),
        ]
    )

    assert result.vendor_name is None
    assert result.purchased_at == "2023-08-11"


def test_parser_parses_lowres_coded_convenience_rows_with_alnum_barcode_prefix() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="B301056177584 01 칠성사이다 제로 500m 1,780 3,560", confidence=0.88, line_id=1, page_order=1),
            OcrLine(text="250C003172533 02 김치제육심각 1,080 1,080", confidence=0.87, line_id=2, page_order=2),
            OcrLine(text="2500000172496 04 뉴 스명참치마요 삼각 1,080 1,080", confidence=0.91, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "칠성사이다 제로 500ml",
        "김치제육삼각",
        "참치마요 삼각",
    ]
    assert [item.quantity for item in result.items] == [2.0, 1.0, 1.0]
    assert [item.amount for item in result.items] == [3560.0, 1080.0, 1080.0]


def test_parser_strips_barcode_and_line_number_prefixes_from_lowres_food_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="*8B01075007602 016사조고추참치100g*3 2,220 1 2,220", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="017 *8801047815594 동원야채참치100g*3 4,480 4,480", confidence=0.99, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "사조고추참치100g*3",
        "동원야채참치100g*3",
    ]
    assert [item.amount for item in result.items] == [2220.0, 4480.0]


def test_parser_filters_butane_gas_as_non_food_item() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="*8801551402013 015애니파워부탄가스 3,280 1 3,280", confidence=0.92, line_id=1, page_order=1),
        ]
    )

    assert result.items == []


def test_parser_strips_leading_plu_codes_and_short_markers_from_grocery_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="200078 한은) 생목심(구이용) 13,450 13,450", confidence=0.90, line_id=1, page_order=1),
            OcrLine(text="202240 ·청양고추 1,390 1,390", confidence=0.89, line_id=2, page_order=2),
            OcrLine(text="202210 (CJ)사각햇번300g 1,900 1,900", confidence=0.91, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "한은 생목심",
        "청양고추",
        "사각햇번300g",
    ]
    assert [item.amount for item in result.items] == [13450.0, 1390.0, 1900.0]


def test_parser_strips_embedded_barcode_tail_from_single_line_qty_amount_row() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="*깐양과 8601048101023 1,E50 1 1,650", confidence=0.90, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "*깐양과"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount == 1650.0


def test_parser_normalizes_grocery_partial_ocr_typos_via_exact_aliases() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="200078 한은) 생목심(구이용) 13,450 13,450", confidence=0.90, line_id=1, page_order=1),
            OcrLine(text="202240 ·청양고수 1,390 1,390", confidence=0.89, line_id=2, page_order=2),
        ]
    )

    assert [item.normalized_name for item in result.items] == [
        "생목심(구이용)",
        "청양고추",
    ]


def test_parser_normalizes_oip9_style_grocery_ocr_typos_via_exact_aliases() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 금액", confidence=0.88, line_id=0, page_order=0),
            OcrLine(text="하인즈유기농케참90", confidence=0.83, line_id=1, page_order=1),
            OcrLine(text="8801065000699 9,980 - 9,980", confidence=0.89, line_id=2, page_order=2),
            OcrLine(text="갈바니리코타치츠4", confidence=0.89, line_id=3, page_order=3),
            OcrLine(text="0738824102401 6,680 1 6,680", confidence=0.98, line_id=4, page_order=4),
            OcrLine(text="블렌드슈레드치즈1k9", confidence=0.95, line_id=5, page_order=5),
            OcrLine(text="8809234660309 11,980 1 11,980", confidence=0.99, line_id=6, page_order=6),
        ]
    )

    assert [item.normalized_name for item in result.items] == [
        "하인즈 유기농케찹90",
        "갈바니 리코타 치즈4",
        "블렌드 슈레드치즈1kg",
    ]


def test_parser_parses_spaced_numeric_detail_rows_from_image_style_receipt() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단 가 수량 금 액", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="양념등심돈까스", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="1500000141394 16, 980 1 16,980", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="8801052993485 청정원 서해안 까나리", confidence=0.96, line_id=3, page_order=3),
            OcrLine(text="6, 780 1 6,780", confidence=0.95, line_id=4, page_order=4),
            OcrLine(text="하인즈유기농케찹90", confidence=0.85, line_id=5, page_order=5),
            OcrLine(text="8801065000699 9, 980 1 9,980", confidence=0.98, line_id=6, page_order=6),
            OcrLine(text="0738824102401 갈바니'리코타치느4", confidence=0.91, line_id=7, page_order=7),
            OcrLine(text="6, 680 1 6, 680", confidence=0.94, line_id=8, page_order=8),
        ]
    )

    assert [(item.raw_name, item.quantity, item.amount) for item in result.items] == [
        ("양념등심돈까스", 1.0, 16980.0),
        ("청정원 서해안 까나리", 1.0, 6780.0),
        ("하인즈유기농케찹90", 1.0, 9980.0),
        ("갈바니'리코타치느4", 1.0, 6680.0),
    ]


def test_parser_skips_summary_fragment_tail_rows_from_image_style_receipt() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단 가 수량 금 액", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="품 2 11", confidence=0.78, line_id=1, page_order=1),
            OcrLine(text="(*) 세 물물 27,740", confidence=0.90, line_id=2, page_order=2),
            OcrLine(text="세 품품세 81, 673", confidence=0.97, line_id=3, page_order=3),
            OcrLine(text="가 8,167", confidence=1.00, line_id=4, page_order=4),
            OcrLine(text="계 117, 580", confidence=0.98, line_id=5, page_order=5),
            OcrLine(text="결제대상금액 112,580", confidence=0.90, line_id=6, page_order=6),
        ]
    )

    assert result.items == []
    assert result.totals["total"] == 117580.0
    assert result.totals["payment_amount"] == 112580.0


def test_parser_normalizes_homeplus_snack_aliases_and_skips_domain_noise() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="크라우참쌀서과293G 4,320 1 4,320", confidence=0.95, line_id=1, page_order=1),
            OcrLine(text="09 해태구문감자4 2 2,240", confidence=0.94, line_id=2, page_order=2),
            OcrLine(text="13미니투셔바베큐4입( ㄷ120g TE.CO.KR 760 1 1,760", confidence=0.94, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "크라운참쌀선과293G",
        "해태구운감자4",
    ]


def test_parser_strips_embedded_price_tail_from_single_line_name_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="와이멘씨라이스퍼프1 3,980 ] 3,980", confidence=0.87, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "와이멘씨라이스퍼프"
    assert result.items[0].amount == 3980.0
    assert result.items[0].parse_pattern == "single_line_name_amount"


def test_parser_does_not_accept_bracketed_alpha_noise_as_vendor() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="[NATT", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="[판매] 2015-01-20 18:28", confidence=0.95, line_id=1, page_order=1),
            OcrLine(text="속이면한 누룸지(5입)", confidence=0.92, line_id=2, page_order=2),
            OcrLine(text="8801169770207 5,600 1 5,600", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert result.vendor_name is None


def test_parser_strips_trailing_barcode_suffix_from_single_line_name_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="스팀덱 64GB 0814585021752 589,000 589,000", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="1", confidence=0.99, line_id=2, page_order=2),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "스팀덱 64GB"
    assert result.items[0].amount == 589000.0


def test_parser_keeps_legitimate_single_item_even_when_amount_matches_total() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="[구매] 2023-06-08 19:01", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="스팀덱 64GB 0814585021752 589,000 589,000", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="1", confidence=0.99, line_id=3, page_order=3),
            OcrLine(text="결제대상금 589,000", confidence=0.99, line_id=4, page_order=4),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "스팀덱 64GB"


def test_parser_keeps_explicit_payment_amount_over_later_card_split_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="결제대상금 589,000", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="카드결제(IC) 일시불7200,000", confidence=0.96, line_id=1, page_order=1),
            OcrLine(text="0025신한 일시물/289,000", confidence=0.92, line_id=2, page_order=2),
        ]
    )

    assert result.totals["payment_amount"] == 589000.0


def test_parser_uses_exact_product_aliases_for_noisy_packaged_item_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="어쉬밀크클릿 [ 1,600", confidence=0.79, line_id=0, page_order=0),
            OcrLine(text="초코빼빼로지암 L 1,700", confidence=0.76, line_id=1, page_order=1),
            OcrLine(text="이에 2 4,000", confidence=0.77, line_id=2, page_order=2),
            OcrLine(text="8801062639854 005 롯데앤디카페조릿 다크", confidence=0.92, line_id=3, page_order=3),
            OcrLine(text="4,800 1 4,800", confidence=0.99, line_id=4, page_order=4),
        ]
    )

    assert [item.normalized_name for item in result.items] == [
        "허쉬밀크초콜릿",
        "초코빼빼로",
        "호레오화이트",
        "롯데 앤디카페 초콜릿 다크빈",
    ]


def test_parser_does_not_use_approval_number_as_payment_amount() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="결제금액 11,517", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="카드결제 승인번호123456", confidence=0.98, line_id=1, page_order=1),
        ]
    )

    assert result.totals["payment_amount"] == 11517.0


def test_parser_does_not_mark_total_mismatch_when_subtotal_matches_items_and_tax_exists() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="GS25", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="[주문] 2023-11-24 18:59", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="호가든캔330ml 1 3,500", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="아몬드초코볼 2 4,000", confidence=0.97, line_id=3, page_order=3),
            OcrLine(text="양파 3 2,970", confidence=0.97, line_id=4, page_order=4),
            OcrLine(text="과세물품 10,470", confidence=0.99, line_id=5, page_order=5),
            OcrLine(text="부가세 1,047", confidence=0.99, line_id=6, page_order=6),
            OcrLine(text="결제금액 11,517", confidence=0.99, line_id=7, page_order=7),
        ]
    )

    assert "total_mismatch" not in result.review_reasons


def test_parser_does_not_mark_total_mismatch_when_payment_minus_tax_matches_items() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="GS25", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="[주문] 2023-11-24 18:59", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="허쉬쿠키앤크림 1 1,600", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="허쉬쿠키앤초코 2 3,200", confidence=0.97, line_id=3, page_order=3),
            OcrLine(text="호가든캔330ml 3 10,500", confidence=0.97, line_id=4, page_order=4),
            OcrLine(text="부가세 1,530", confidence=0.99, line_id=5, page_order=5),
            OcrLine(text="결제금액 16,830", confidence=0.99, line_id=6, page_order=6),
        ]
    )

    assert "total_mismatch" not in result.review_reasons


def test_parser_does_not_require_review_only_for_unknown_item_when_structure_is_complete() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="GS25", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="[주문] 2023-11-24 18:59", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="희귀한상품A 1 2,800", confidence=0.95, line_id=2, page_order=2),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "희귀한상품A"
    assert "unknown_item" in result.items[0].review_reason
    assert result.items[0].needs_review is False
    assert result.review_required is False


def test_parser_parses_name_quantity_then_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="아몬드초코볼 3", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="6,000", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="대파 1", confidence=0.94, line_id=2, page_order=2),
            OcrLine(text="2,480", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "아몬드초코볼",
        "대파",
    ]
    assert [item.quantity for item in result.items] == [3.0, 1.0]
    assert [item.amount for item in result.items] == [6000.0, 2480.0]
    assert all(item.parse_pattern == "name_qty_then_amount" for item in result.items)


def test_parser_parses_compact_name_quantity_then_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330ml3", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="10,500", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="양파1", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="990", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == ["호가든캔330ml", "양파"]
    assert [item.quantity for item in result.items] == [3.0, 1.0]
    assert [item.amount for item in result.items] == [10500.0, 990.0]


def test_parser_parses_compact_split_gift_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파1", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="증정품", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "양파"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount is None


def test_parser_parses_narrow_column_name_qty_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파21,980", confidence=0.97, line_id=0, page_order=0),
            OcrLine(text="속이편한 누룸지15,600", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="롯데 앤디카페조릿 다크29,600", confidence=0.97, line_id=2, page_order=2),
            OcrLine(text="닭주물럭2.2kg114,900", confidence=0.97, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "양파",
        "속이편한 누룽지",
        "롯데 앤디카페조릿 다크",
        "닭주물럭2.2kg",
    ]
    assert [item.quantity for item in result.items] == [2.0, 1.0, 2.0, 1.0]
    assert [item.amount for item in result.items] == [1980.0, 5600.0, 9600.0, 14900.0]


def test_parser_parses_narrow_column_gift_rows_with_digit_suffix_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤크림1증정품", confidence=0.97, line_id=0, page_order=0),
            OcrLine(text="계란10구1증정품", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="맛밤42G*101증정품", confidence=0.97, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "허쉬쿠키앤크림",
        "계란10구",
        "맛밤42G*10",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0, 1.0]
    assert [item.amount for item in result.items] == [None, None, None]


def test_parser_recovers_digit_suffix_name_from_compact_qty_amount_with_merged_unit_price() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="라라스윗 바닐라파인트4746,900213,800", confidence=0.98, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "라라스윗 바닐라파인트474"
    assert result.items[0].quantity == 2.0
    assert result.items[0].amount == 13800.0


def test_parser_strips_barcode_detail_suffix_with_placeholder_before_quantity() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="닭주물럭2.2kg 14,900 )1 14,900", confidence=0.94, line_id=0, page_order=0),
            OcrLine(text="8800299000123 14,900 1", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "닭주물럭2.2kg"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount == 14900.0


def test_parser_parses_name_price_then_quantity_and_amount_stack() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330ml 3,500", confidence=0.97, line_id=0, page_order=0),
            OcrLine(text="1", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="3,500", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="아몬드초코볼 2,000", confidence=0.95, line_id=3, page_order=3),
            OcrLine(text="2", confidence=0.98, line_id=4, page_order=4),
            OcrLine(text="4,000", confidence=0.99, line_id=5, page_order=5),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "호가든캔330ml",
        "아몬드초코볼",
    ]
    assert [item.quantity for item in result.items] == [1.0, 2.0]
    assert [item.amount for item in result.items] == [3500.0, 4000.0]
    assert all(item.parse_pattern == "name_price_then_qty_amount" for item in result.items)


def test_parser_parses_split_gift_item_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330ml 1", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="증정품", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "호가든캔330ml"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount is None
    assert result.items[0].parse_pattern == "split_gift"


def test_parser_parses_compact_name_qty_amount_without_space() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330ml27,000", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="대파1 2,480", confidence=0.96, line_id=1, page_order=1),
            OcrLine(text="계란10구1 4,590", confidence=0.98, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "호가든캔330ml",
        "대파",
        "계란10구",
    ]
    assert [item.quantity for item in result.items] == [2.0, 1.0, 1.0]
    assert [item.amount for item in result.items] == [7000.0, 2480.0, 4590.0]


def test_parser_parses_compact_unit_price_qty_amount_without_spaces() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330ml3,500310,500", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="라라스윗초코파인트474ml6,900213,800", confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "호가든캔330ml",
        "라라스윗초코파인트474ml",
    ]
    assert [item.quantity for item in result.items] == [3.0, 2.0]
    assert [item.amount for item in result.items] == [10500.0, 13800.0]


def test_parser_parses_compact_gift_with_merged_unit_price_and_quantity() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤크림 11,6001증정품", confidence=0.95, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "허쉬쿠키앤크림"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount is None


def test_parser_prefers_following_barcode_detail_over_noisy_compact_single_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="라라스윗 초코파인트474ml6,9002 13,800", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="8800274000123 6,900 2", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "라라스윗 초코파인트474ml"
    assert result.items[0].quantity == 2.0
    assert result.items[0].amount == 13800.0


def test_parser_prefers_following_barcode_detail_for_compact_gift_row() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파9901 증정품", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="8800282000123 990 1", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "양파"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount is None


def test_parser_prefers_name_qty_then_amount_before_cross_item_columnar_stack() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="아몬드초코볼 3", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="6,000", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="1", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="990", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert result.items[0].raw_name == "아몬드초코볼"
    assert result.items[0].quantity == 3.0
    assert result.items[0].amount == 6000.0
    assert result.items[0].parse_pattern == "name_qty_then_amount"


def test_parser_does_not_infer_amount_for_two_line_gift_barcode_detail() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤크림 11,6001증정품", confidence=0.97, line_id=0, page_order=0),
            OcrLine(text="8800270000123 1,600 1", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "허쉬쿠키앤크림"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount is None


def test_parser_parses_spaced_compact_unit_price_qty_amount_without_digit_in_name() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="허쉬쿠키앤초코 1,6002 3,200", confidence=0.96, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "허쉬쿠키앤초코"
    assert result.items[0].quantity == 2.0
    assert result.items[0].amount == 3200.0
    assert result.items[0].parse_pattern == "compact_unit_price_qty_amount"


def test_parser_parses_short_compact_name_qty_amount_without_space() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파32,970", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="대파2,48012,480", confidence=0.96, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == ["양파", "대파"]
    assert [item.quantity for item in result.items] == [3.0, 1.0]
    assert [item.amount for item in result.items] == [2970.0, 2480.0]


def test_parser_parses_compact_name_qty_amount_with_spaced_name_prefix() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="라라스윗 바닐라파인트474320,700", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="속이편한누륨지316,800", confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "라라스윗 바닐라파인트474",
        "속이편한누룽지",
    ]
    assert [item.quantity for item in result.items] == [3.0, 3.0]
    assert [item.amount for item in result.items] == [20700.0, 16800.0]


def test_parser_strips_redundant_unit_price_from_name_qty_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파990 1 990", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="계란10구 4,590 1 4,590", confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "양파",
        "계란10구",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0]
    assert [item.amount for item in result.items] == [990.0, 4590.0]


def test_parser_parses_spaced_compact_gift_rows_with_unit_price_suffix() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="계란 10구 4,5901 증정품", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="롯데 앤디카페조릿 다크 4,8001 증정품", confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "계란 10구",
        "롯데 앤디카페조릿 다크",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0]
    assert [item.amount for item in result.items] == [None, None]


def test_parser_strips_unit_price_from_spaced_single_line_gift_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="계란 10구 4,590 1 증정품", confidence=0.95, line_id=0, page_order=0),
            OcrLine(text="허쉬쿠키앤초코 1,600 1 증정품", confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "계란 10구",
        "허쉬쿠키앤초코",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0]
    assert [item.amount for item in result.items] == [None, None]


def test_parser_recovers_name_from_two_line_barcode_when_name_line_contains_price_and_total_tail() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="양파99032,970", confidence=0.98, line_id=0, page_order=0),
            OcrLine(text="8800272000123 990 3", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "양파"
    assert result.items[0].quantity == 3.0
    assert result.items[0].amount == 2970.0


def test_parser_normalizes_trailing_m_unit_to_ml() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="호가든캔330m 1 증정품", confidence=0.95, line_id=0, page_order=0),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "호가든캔330ml"


def test_parser_does_not_keep_vendor_or_summary_line_as_item() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="이마트", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="호가든캔330ml 3,500", confidence=0.97, line_id=1, page_order=1),
            OcrLine(text="1", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="3,500", confidence=0.99, line_id=3, page_order=3),
            OcrLine(text="묶롬Y 10,470", confidence=0.88, line_id=4, page_order=4),
            OcrLine(text="부가세 1,047", confidence=0.98, line_id=5, page_order=5),
            OcrLine(text="합계 11,517", confidence=0.99, line_id=6, page_order=6),
        ]
    )

    assert [item.raw_name for item in result.items] == ["호가든캔330ml"]
    assert result.totals["total"] == 11517.0


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


def test_parser_inferrs_quantity_from_code_times_price_amount_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="드시모네2500억", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="680577 1× 89,900 89,900 T", confidence=0.92, line_id=1, page_order=1),
            OcrLine(text="국산한우채끝1+", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="618911 1×121,670 12',670", confidence=0.95, line_id=3, page_order=3),
            OcrLine(text="미국부채스테이크", confidence=0.98, line_id=4, page_order=4),
            OcrLine(text="534759 1×/50,810 50,810", confidence=0.97, line_id=5, page_order=5),
        ]
    )

    assert [item.raw_name for item in result.items] == [
        "드시모네2500억",
        "국산한우채끝1+",
        "미국부채스테이크",
    ]
    assert [item.quantity for item in result.items] == [1.0, 1.0, 1.0]
    assert [item.amount for item in result.items] == [89900.0, 121670.0, 50810.0]


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


def test_parser_filters_member_expiry_metadata_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="회원만료일:2026-06", confidence=0.96, line_id=0, page_order=0),
            OcrLine(text="드시모네2500억", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="680577 1× 89,900 89,900 T", confidence=0.92, line_id=2, page_order=2),
        ]
    )

    assert [item.raw_name for item in result.items] == ["드시모네2500억"]


def test_parser_filters_low_confidence_short_unknown_hangul_items() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="피그 1 2,480", confidence=0.75, line_id=0, page_order=0),
            OcrLine(text="금루금", confidence=0.76, line_id=1, page_order=1),
            OcrLine(text="은", confidence=0.78, line_id=2, page_order=2),
            OcrLine(text="양파 1 990", confidence=0.76, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == ["피그", "양파"]


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
def test_parser_filters_pack_size_single_line_without_amount() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="이클립스 페퍼민트향 34g 770 1 770", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="미클립스 피치향 34g", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="합계 770", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert [item.raw_name for item in result.items] == ["이클립스 페퍼민트향 34g"]


def test_parser_does_not_treat_trailing_pack_size_as_price() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="024 미클립스 피치향 34g", confidence=0.99, line_id=0, page_order=0),
        ]
    )

    assert result.items == []


def test_parser_parses_two_line_item_when_name_contains_food_packaging_phrase() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="농심 쌀국수 용기면 6입", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="5,940 1 5,940", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="합계 5,940", confidence=0.99, line_id=3, page_order=3),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "농심 쌀국수 용기면 6입"
    assert result.items[0].amount == 5940.0
    assert result.items[0].parse_pattern == "name_then_numeric_detail"


def test_parser_diagnostics_exclude_filtered_non_food_rows_from_consumed_ids() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="농심 새우탕 컵 3,750 1 3,750", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="OnlyPrice 삼중스펀지 수세미", confidence=0.98, line_id=2, page_order=2),
            OcrLine(text="1,000 1 1,000", confidence=0.98, line_id=3, page_order=3),
            OcrLine(text="합계 4,750", confidence=0.99, line_id=4, page_order=4),
        ]
    )

    assert [item.raw_name for item in result.items] == ["농심 새우탕 컵"]
    assert result.diagnostics["consumed_line_ids"] == [1]


def test_parser_normalizes_real_receipt_aliases_before_candidate_stripping() -> None:
    parser = ReceiptParser()

    assert parser._normalize_item_name("× 파프리카")[0] == "파프리카"
    assert parser._normalize_item_name("* 완숙토마토 4kg/박스")[0] == "완숙토마토"
    assert parser._normalize_item_name("* 국내산 양상추 2입")[0] == "양상추"
    assert parser._normalize_item_name("갈바니'리코타치느4")[0] == "갈바니 리코타 치즈4"


def test_parser_strips_leading_receipt_markers_from_item_raw_names() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="× 파프리카(팩)", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="2500000007828 6,480 1 6,480", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="* 국내산 양상추 2입", confidence=0.98, line_id=3, page_order=3),
            OcrLine(text="2500000006425 4,780 1 4,780", confidence=0.99, line_id=4, page_order=4),
        ]
    )

    assert [item.raw_name for item in result.items] == ["파프리카", "국내산 양상추 2입"]


def test_parser_infers_quantity_from_t_placeholder_code_detail_row() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="024 미클립스 피치향 34g", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="210032 790 T 790", confidence=0.99, line_id=1, page_order=1),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "미클립스 피치향 34g"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount == 790.0
    assert result.items[0].parse_pattern == "name_then_code_amount_inferred_qty"


def test_parser_extracts_tax_from_punctuated_bugae_line() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text='과세물품가액 12,545', confidence=0.99, line_id=0, page_order=0),
            OcrLine(text='부 "가 세 1,255', confidence=0.95, line_id=1, page_order=1),
        ]
    )

    assert result.totals["subtotal"] == 12545.0
    assert result.totals["tax"] == 1255.0


def test_parser_corrects_pack_count_quantity_when_unit_price_matches_amount() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="* 국내산 양상추2입", confidence=0.89, line_id=1, page_order=1),
            OcrLine(text="2500000006425 4,780 7 4,780", confidence=0.89, line_id=2, page_order=2),
        ]
    )

    assert len(result.items) == 1
    assert result.items[0].raw_name == "국내산 양상추2입"
    assert result.items[0].quantity == 1.0
    assert result.items[0].amount == 4780.0


def test_parser_prefers_discount_adjusted_unlabeled_final_amount_after_total() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="계 117,580", confidence=0.99, line_id=0, page_order=0),
            OcrLine(text="삼성카드할인 -5,000", confidence=0.98, line_id=1, page_order=1),
            OcrLine(text="112,580", confidence=0.99, line_id=2, page_order=2),
        ]
    )

    assert result.totals["total"] == 117580.0
    assert result.totals["payment_amount"] == 112580.0


def test_parser_prunes_totals_metadata_false_positive_in_oip9_style_receipt() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="상품명 단가 수량 금액", confidence=0.90, line_id=0, page_order=0),
            OcrLine(text="* 완숙토마토 4kg/박스", confidence=0.93, line_id=1, page_order=1),
            OcrLine(text="2500000013522 17,980 1 17,980", confidence=0.99, line_id=2, page_order=2),
            OcrLine(text="() IY 27,740", confidence=0.98, line_id=3, page_order=3),
            OcrLine(text="JY 물 손어머 81,673", confidence=0.78, line_id=4, page_order=4),
            OcrLine(text="가 8,167", confidence=0.99, line_id=5, page_order=5),
            OcrLine(text="계 117,580", confidence=0.96, line_id=6, page_order=6),
            OcrLine(text="삼성카드할인 -5,000", confidence=0.98, line_id=7, page_order=7),
            OcrLine(text="112,580", confidence=0.99, line_id=8, page_order=8),
        ]
    )

    assert [item.raw_name for item in result.items] == ["완숙토마토 4kg/박스"]
    assert result.totals["subtotal"] == 81673.0
    assert result.totals["tax"] == 8167.0
    assert result.totals["total"] == 117580.0
    assert result.totals["payment_amount"] == 112580.0


def test_parser_recovers_leading_item_before_broken_second_item_in_oip9_style_receipt() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="B몸 B 가 수량 문 Ho", confidence=0.66, line_id=0, page_order=0),
            OcrLine(text="양념등심돈까스", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="1500000141394 16, 980 - 16,980", confidence=0.94, line_id=2, page_order=2),
            OcrLine(text="()2", confidence=0.63, line_id=3, page_order=3),
            OcrLine(text="2500000007828 6,480 1 6,480", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="2021채소S-POINT -1,500", confidence=0.97, line_id=5, page_order=5),
            OcrLine(text="* 완숙토마토 4kg/박스", confidence=0.93, line_id=6, page_order=6),
            OcrLine(text="2500000013522 17,980 1 17,980", confidence=0.99, line_id=7, page_order=7),
        ]
    )

    assert [item.raw_name for item in result.items][:2] == [
        "양념등심돈까스",
        "완숙토마토 4kg/박스",
    ]
    assert result.items[0].amount == 16980.0


def test_parser_keeps_leading_item_when_full_oip9_style_receipt_contains_broken_following_rows() -> None:
    parser = ReceiptParser()

    result = parser.parse_lines(
        [
            OcrLine(text="B몸 B 가 수량 문 Ho", confidence=0.66, line_id=0, page_order=0),
            OcrLine(text="양념등심돈까스", confidence=0.99, line_id=1, page_order=1),
            OcrLine(text="1500000141394 16, 980 - 16,980", confidence=0.94, line_id=2, page_order=2),
            OcrLine(text="()2", confidence=0.63, line_id=3, page_order=3),
            OcrLine(text="2500000007828 6,480 1 6,480", confidence=0.99, line_id=4, page_order=4),
            OcrLine(text="2021채소S-POINT -1,500", confidence=0.97, line_id=5, page_order=5),
            OcrLine(text="* 완숙토마토 4kg/박스", confidence=0.93, line_id=6, page_order=6),
            OcrLine(text="2500000013522 17,980 1 17,980", confidence=0.99, line_id=7, page_order=7),
            OcrLine(text="양념닭주물럭2.2kg", confidence=0.94, line_id=8, page_order=8),
            OcrLine(text="2500000284861 27,980 1 27,980", confidence=0.99, line_id=9, page_order=9),
            OcrLine(text="-2,500", confidence=0.99, line_id=10, page_order=10),
            OcrLine(text="청정원서해안까나리", confidence=0.89, line_id=11, page_order=11),
            OcrLine(text="8801052993485 6,780 1 6,780", confidence=0.99, line_id=12, page_order=12),
        ]
    )

    assert [item.raw_name for item in result.items][:3] == [
        "양념등심돈까스",
        "완숙토마토 4kg/박스",
        "양념닭주물럭2.2kg",
    ]
