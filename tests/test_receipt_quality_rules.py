from __future__ import annotations

from ocr_qwen.receipts import OcrLine, ReceiptParser


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
        "속이면한 누룸지",
        "속이면한 누룸지",
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
        "호가든캔330ML",
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
        "호가든캔330ML",
        "아몬드코볼",
    ]
    assert result.items[0].amount == 1600.0
    assert result.items[1].amount is None
    assert result.items[2].amount == 3500.0
    assert result.totals["total"] == 24090.0
