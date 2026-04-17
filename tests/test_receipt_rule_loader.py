from __future__ import annotations

import json
from pathlib import Path

from ocr_qwen.receipt_rules import ReceiptRules


def test_receipt_rules_load_bundled_rule_files() -> None:
    rules = ReceiptRules.load_default()

    assert "payment" in rules.non_item_categories
    assert "packaging" in rules.non_item_categories
    assert rules.apply_product_alias("투썸딸기피지") == "투썸딸기피치"
    assert rules.apply_product_alias("어쉬밀크클릿 [") == "허쉬밀크초콜릿"

    mapping = rules.lookup_product_to_ingredient("호가든캔330ml")
    assert mapping is not None
    assert mapping["ingredient_name"] == "맥주"


def test_receipt_rules_load_custom_rule_files(tmp_path: Path) -> None:
    rule_dir = tmp_path / "receipt_rules"
    rule_dir.mkdir()

    (rule_dir / "non_item_exclusions.json").write_text(
        json.dumps(
            {
                "categories": {
                    "payment": {
                        "contains": ["카드"],
                        "regex": [r"승인번호\d+"],
                    }
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (rule_dir / "product_aliases.json").write_text(
        json.dumps(
            {
                "aliases": [
                    {"source": "테스트오타", "target": "테스트표준", "match": "contains"},
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (rule_dir / "product_to_ingredient.json").write_text(
        json.dumps(
            {
                "mappings": [
                    {
                        "standard_product_name": "테스트표준",
                        "ingredient_name": "테스트재료",
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    rules = ReceiptRules.load_from_directory(rule_dir)

    assert rules.matches_non_item("신용카드")
    assert rules.matches_non_item("승인번호1234")
    assert rules.apply_product_alias("abc테스트오타xyz") == "abc테스트표준xyz"

    mapping = rules.lookup_product_to_ingredient("테스트표준")
    assert mapping is not None
    assert mapping["ingredient_name"] == "테스트재료"
