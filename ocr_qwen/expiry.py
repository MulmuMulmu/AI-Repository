from __future__ import annotations

from dataclasses import dataclass
from datetime import date


DEFAULT_SHELF_LIFE_DAYS = {
    ("vegetable", "room"): 7,
    ("fruit", "room"): 7,
    ("dairy", "refrigerated"): 7,
    ("meat", "refrigerated"): 3,
    ("seafood", "refrigerated"): 2,
    ("egg", "refrigerated"): 14,
    ("tofu_bean", "refrigerated"): 5,
    ("sauce", "room"): 30,
    ("sauce", "refrigerated"): 14,
    ("beverage", "room"): 30,
    ("beverage", "refrigerated"): 7,
    ("frozen", "frozen"): 30,
    ("other", "room"): 7,
}

CTA_BY_RISK = {
    "safe": "보관",
    "consume_soon": "오늘 소비",
    "urgent": "오늘 소비 우선",
    "share_now": "나눔 등록 권장",
}


@dataclass(frozen=True)
class InventoryItem:
    normalized_name: str
    category: str
    storage_type: str
    purchased_at: str


@dataclass
class ExpiryEvaluationResult:
    normalized_name: str
    days_since_purchase: int
    default_shelf_life_days: int
    risk_level: str
    recommended_cta: str
    is_expired: bool


class ExpiryEvaluator:
    def __init__(self, today: date | None = None) -> None:
        self.today = today or date.today()

    def evaluate(self, items: list[InventoryItem]) -> list[ExpiryEvaluationResult]:
        return [self._evaluate_item(item) for item in items]

    def _evaluate_item(self, item: InventoryItem) -> ExpiryEvaluationResult:
        purchased_at = date.fromisoformat(item.purchased_at)
        days_since_purchase = (self.today - purchased_at).days
        shelf_life = DEFAULT_SHELF_LIFE_DAYS.get(
            (item.category, item.storage_type),
            DEFAULT_SHELF_LIFE_DAYS[("other", "room")],
        )
        remaining_days = shelf_life - days_since_purchase
        is_expired = remaining_days < 0

        if remaining_days >= 4:
            risk_level = "safe"
        elif remaining_days >= 2:
            risk_level = "consume_soon"
        elif remaining_days >= 1:
            risk_level = "share_now"
        else:
            risk_level = "urgent"
        recommended_cta = "폐기 검토" if is_expired else CTA_BY_RISK[risk_level]

        return ExpiryEvaluationResult(
            normalized_name=item.normalized_name,
            days_since_purchase=days_since_purchase,
            default_shelf_life_days=shelf_life,
            risk_level=risk_level,
            recommended_cta=recommended_cta,
            is_expired=is_expired,
        )
