from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Iterable


@dataclass(frozen=True)
class NonItemCategoryRule:
    name: str
    contains: tuple[str, ...]
    regex: tuple[str, ...]
    compiled_regex: tuple[re.Pattern[str], ...]

    def matches(self, text: str) -> bool:
        candidate = text.strip()
        if not candidate:
            return False
        lowered = candidate.lower()
        for token in self.contains:
            if token and token.lower() in lowered:
                return True
        return any(pattern.search(candidate) for pattern in self.compiled_regex)


@dataclass(frozen=True)
class ReceiptRules:
    non_item_rules: tuple[NonItemCategoryRule, ...]
    product_aliases: dict[str, str]
    product_alias_replacements: tuple[tuple[str, str], ...]
    product_to_ingredient: dict[str, str]
    source_dir: Path

    @property
    def non_item_categories(self) -> dict[str, NonItemCategoryRule]:
        return {rule.name: rule for rule in self.non_item_rules}

    def match_non_item_category(self, text: str) -> str | None:
        for rule in self.non_item_rules:
            if rule.matches(text):
                return rule.name
        return None

    def matches_non_item(self, text: str) -> bool:
        return self.match_non_item_category(text) is not None

    def apply_product_alias(self, product_name: str) -> str:
        direct_candidate = product_name.strip()
        for source, target in self.product_alias_replacements:
            if source and source in direct_candidate:
                direct_candidate = direct_candidate.replace(source, target)

        candidate = _normalize_key(product_name).casefold()
        if not candidate:
            return direct_candidate
        return self.product_aliases.get(candidate, direct_candidate)

    def lookup_product_to_ingredient(self, product_name: str) -> dict[str, str] | None:
        normalized = self.apply_product_alias(product_name)
        candidate = _normalize_key(normalized).casefold()
        if not candidate:
            return None
        ingredient_name = self.product_to_ingredient.get(candidate)
        if ingredient_name is None:
            return None
        return {
            "standard_product_name": normalized,
            "ingredient_name": ingredient_name,
        }

    @classmethod
    def load_default(cls) -> "ReceiptRules":
        return load_receipt_rules()

    @classmethod
    def load_from_directory(cls, rule_dir: Path) -> "ReceiptRules":
        return load_receipt_rules(rule_dir)


def default_rule_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "receipt_rules"


def load_receipt_rules(rule_dir: Path | None = None) -> ReceiptRules:
    base_dir = rule_dir or default_rule_dir()
    non_item_data = _load_json(base_dir / "non_item_exclusions.json")
    alias_data = _load_json(base_dir / "product_aliases.json")
    product_to_ingredient_data = _load_json(base_dir / "product_to_ingredient.json")

    categories = non_item_data.get("categories", [])
    if isinstance(categories, dict):
        category_rows = [
            {
                "name": name,
                **(config if isinstance(config, dict) else {}),
            }
            for name, config in categories.items()
        ]
    else:
        category_rows = list(categories)

    non_item_rules = tuple(
        NonItemCategoryRule(
            name=str(category["name"]),
            contains=tuple(str(value).strip() for value in category.get("contains", []) if str(value).strip()),
            regex=tuple(str(value).strip() for value in category.get("regex", []) if str(value).strip()),
            compiled_regex=tuple(
                re.compile(str(value), re.IGNORECASE)
                for value in category.get("regex", [])
                if str(value).strip()
            ),
        )
        for category in category_rows
        if isinstance(category, dict) and category.get("name")
    )

    alias_rows = alias_data.get("aliases", [])
    product_aliases = _build_lookup_map(
        alias_rows,
        key_fields=("raw", "source"),
        value_fields=("standard", "target"),
    )
    product_alias_replacements = tuple(
        (
            str(row.get("raw") or row.get("source") or "").strip(),
            str(row.get("standard") or row.get("target") or "").strip(),
        )
        for row in alias_rows
        if isinstance(row, dict)
        and str(row.get("raw") or row.get("source") or "").strip()
        and str(row.get("standard") or row.get("target") or "").strip()
    )
    product_to_ingredient = _build_lookup_map(
        product_to_ingredient_data.get("mappings", []),
        key_fields=("product", "standard_product_name"),
        value_fields=("ingredient", "ingredient_name"),
    )

    return ReceiptRules(
        non_item_rules=non_item_rules,
        product_aliases=product_aliases,
        product_alias_replacements=product_alias_replacements,
        product_to_ingredient=product_to_ingredient,
        source_dir=base_dir,
    )


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _normalize_key(value: str) -> str:
    return re.sub(r"\s+", "", value or "").strip()


def _build_lookup_map(
    rows: Iterable[dict[str, object]],
    *,
    key_fields: tuple[str, ...],
    value_fields: tuple[str, ...],
) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for row in rows:
        key = ""
        value = ""
        for field_name in key_fields:
            candidate = str(row.get(field_name, "")).strip()
            if candidate:
                key = candidate
                break
        for field_name in value_fields:
            candidate = str(row.get(field_name, "")).strip()
            if candidate:
                value = candidate
                break
        if not key or not value:
            continue
        for candidate in (key, _normalize_key(key), _normalize_key(key).casefold()):
            if candidate and candidate not in lookup:
                lookup[candidate] = value
    return lookup
