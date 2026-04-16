from __future__ import annotations

from ocr_qwen.rule_candidates import build_rule_candidate_report


def test_build_rule_candidate_report_separates_alias_unmapped_and_weak_matches() -> None:
    parsed_receipts = [
        {
            "file_name": "img2.jpg",
            "items": [
                {
                    "raw_name": "투썸알밀크티",
                    "normalized_name": "투썸로얄밀크티",
                    "confidence": 0.71,
                    "parse_pattern": "single_line",
                },
                {
                    "raw_name": "아몬드빼빼로",
                    "normalized_name": "아몬드빼빼로",
                    "confidence": 0.91,
                    "parse_pattern": "single_line",
                },
                {
                    "raw_name": "호가든캔330ml",
                    "normalized_name": "호가든캔330ml",
                    "confidence": 0.94,
                    "parse_pattern": "single_line",
                },
            ],
        }
    ]

    def ingredient_matcher(name: str):
        if name == "투썸로얄밀크티":
            return {
                "ingredientName": "밀크티",
                "mapping_source": "receipt_rule_product_mapping",
                "similarity": 1.0,
            }
        if name == "호가든캔330ml":
            return {
                "ingredientName": "맥주",
                "mapping_source": "fuzzy_similarity",
                "similarity": 0.72,
            }
        return None

    report = build_rule_candidate_report(parsed_receipts, ingredient_matcher)

    assert report["summary"]["receipt_count"] == 1
    assert report["summary"]["item_count"] == 3

    alias_candidate = report["alias_candidates"][0]
    assert alias_candidate["raw_name"] == "투썸알밀크티"
    assert alias_candidate["normalized_name"] == "투썸로얄밀크티"
    assert alias_candidate["count"] == 1

    unmapped_candidate = report["unmapped_products"][0]
    assert unmapped_candidate["product_name"] == "아몬드빼빼로"
    assert unmapped_candidate["count"] == 1

    weak_candidate = report["weak_match_products"][0]
    assert weak_candidate["product_name"] == "호가든캔330ml"
    assert weak_candidate["ingredient_name"] == "맥주"
    assert weak_candidate["mapping_source"] == "fuzzy_similarity"


def test_build_rule_candidate_report_ignores_clean_rule_mapped_items() -> None:
    parsed_receipts = [
        {
            "file_name": "img3.jpg",
            "items": [
                {
                    "raw_name": "속이편한 누룽지",
                    "normalized_name": "속이편한 누룽지",
                    "confidence": 0.96,
                    "parse_pattern": "single_line",
                }
            ],
        }
    ]

    def ingredient_matcher(name: str):
        assert name == "속이편한 누룽지"
        return {
            "ingredientName": "누룽지",
            "mapping_source": "receipt_rule_product_mapping",
            "similarity": 1.0,
        }

    report = build_rule_candidate_report(parsed_receipts, ingredient_matcher)

    assert report["alias_candidates"] == []
    assert report["unmapped_products"] == []
    assert report["weak_match_products"] == []


def test_build_rule_candidate_report_separates_false_positive_noise_items() -> None:
    parsed_receipts = [
        {
            "file_name": "image.png",
            "items": [
                {
                    "raw_name": "가공에누리 -2,500",
                    "normalized_name": "가공에누리 -2,500",
                    "confidence": 0.96,
                    "parse_pattern": "single_line",
                },
                {
                    "raw_name": ") GA00210-KR 1 지점",
                    "normalized_name": ") GA00210-KR 1 지점",
                    "confidence": 0.97,
                    "parse_pattern": "single_line",
                },
            ],
        }
    ]

    report = build_rule_candidate_report(parsed_receipts, lambda _: None)

    assert report["unmapped_products"] == []
    assert report["weak_match_products"] == []
    assert [row["product_name"] for row in report["false_positive_item_candidates"]] == [
        ") GA00210-KR 1 지점",
        "가공에누리 -2,500",
    ]


def test_build_rule_candidate_report_does_not_treat_packaged_products_as_false_positive() -> None:
    parsed_receipts = [
        {
            "file_name": "R.jpg",
            "items": [
                {
                    "raw_name": "맛밤42G*10",
                    "normalized_name": "맛밤42G*10",
                    "confidence": 0.96,
                    "parse_pattern": "single_line",
                }
            ],
        }
    ]

    report = build_rule_candidate_report(parsed_receipts, lambda _: None)

    assert report["false_positive_item_candidates"] == []
    assert report["unmapped_products"][0]["product_name"] == "맛밤42G*10"
