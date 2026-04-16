"""
소비기한 계산 모듈 — GPT-4o-mini 기반 + 규칙 기반 fallback

설계서 요구사항:
  - GPT-4o-mini를 이용해 백그라운드로 소비기한 계산
  - 결과는 D-Day와 함께 반환
  - 임박 품목은 알림 스케줄과 연결
"""

from __future__ import annotations

import os
import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

# ═══════════════════════════════════════════════════════════════
#  카테고리별 기본 보관일수 (규칙 기반 fallback)
# ═══════════════════════════════════════════════════════════════

DEFAULT_SHELF_LIFE: Dict[str, Dict[str, int]] = {
    "정육/계란": {
        "냉장": 3, "냉동": 90, "상온": 0,
        "items": {
            "계란": {"냉장": 21}, "달걀": {"냉장": 21},
            "삼겹살": {"냉장": 3, "냉동": 60},
            "닭가슴살": {"냉장": 2, "냉동": 60},
            "소고기": {"냉장": 3, "냉동": 90},
        },
    },
    "해산물": {
        "냉장": 2, "냉동": 60, "상온": 0,
        "items": {
            "연어": {"냉장": 2, "냉동": 90},
            "새우": {"냉장": 2, "냉동": 90},
            "오징어": {"냉장": 2, "냉동": 60},
        },
    },
    "채소/과일": {
        "냉장": 7, "냉동": 30, "상온": 5,
        "items": {
            "양파": {"냉장": 30, "상온": 14},
            "감자": {"냉장": 21, "상온": 14},
            "당근": {"냉장": 14},
            "대파": {"냉장": 7},
            "시금치": {"냉장": 3},
            "상추": {"냉장": 3},
            "깻잎": {"냉장": 5},
            "콩나물": {"냉장": 3},
            "버섯": {"냉장": 5},
            "토마토": {"냉장": 7, "상온": 5},
            "사과": {"냉장": 30, "상온": 7},
            "바나나": {"상온": 5},
            "딸기": {"냉장": 3},
        },
    },
    "유제품": {
        "냉장": 7, "냉동": 30, "상온": 0,
        "items": {
            "우유": {"냉장": 7},
            "치즈": {"냉장": 30},
            "버터": {"냉장": 60, "냉동": 180},
            "요구르트": {"냉장": 14},
        },
    },
    "가공식품": {
        "냉장": 14, "냉동": 60, "상온": 30,
        "items": {
            "두부": {"냉장": 5},
            "어묵": {"냉장": 7, "냉동": 60},
            "햄": {"냉장": 14},
            "소시지": {"냉장": 14},
            "만두": {"냉동": 90},
        },
    },
    "쌀/면/빵": {
        "냉장": 7, "냉동": 90, "상온": 30,
        "items": {
            "빵": {"냉장": 5, "상온": 3},
            "쌀": {"상온": 180},
            "라면": {"상온": 180},
        },
    },
    "소스/조미료/오일": {
        "냉장": 180, "상온": 180,
        "items": {
            "간장": {"상온": 365},
            "된장": {"냉장": 90},
            "고추장": {"냉장": 90},
            "식용유": {"상온": 365},
            "참기름": {"상온": 180},
        },
    },
    "김치/절임": {
        "냉장": 30, "상온": 7,
        "items": {
            "김치": {"냉장": 30},
        },
    },
}


class ExpiryCalculator:
    """소비기한 계산 엔진 — GPT-4o-mini + 규칙 기반 fallback."""

    def __init__(self):
        self._openai_client = None
        self._model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self._api_key = os.getenv("OPENAI_API_KEY", "")

    def _get_openai_client(self):
        if self._openai_client is None and self._api_key:
            try:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self._api_key)
            except ImportError:
                pass
        return self._openai_client

    def calculate(
        self,
        item_name: str,
        purchase_date: str,
        storage_method: str = "냉장",
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        소비기한을 계산한다.

        Returns:
            {
                "item_name": str,
                "purchase_date": str,
                "storage_method": str,
                "expiry_date": str,
                "d_day": int,
                "risk_level": str,  # safe / caution / danger / expired
                "confidence": float,
                "method": str,  # gpt-4o-mini / rule-based
                "reason": str,
            }
        """
        try:
            pdate = datetime.strptime(purchase_date, "%Y-%m-%d")
        except ValueError:
            pdate = datetime.now()
            purchase_date = pdate.strftime("%Y-%m-%d")

        result = self._try_gpt(item_name, purchase_date, storage_method)
        if result is None:
            result = self._rule_based(item_name, purchase_date, storage_method, category)

        try:
            exp_date = datetime.strptime(result["expiry_date"], "%Y-%m-%d")
            d_day = (exp_date - datetime.now()).days
        except ValueError:
            d_day = 0

        result["d_day"] = d_day
        result["risk_level"] = self._assess_risk(d_day)
        return result

    def calculate_batch(
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """여러 품목의 소비기한을 일괄 계산."""
        return [
            self.calculate(
                item_name=it.get("item_name", ""),
                purchase_date=it.get("purchase_date", datetime.now().strftime("%Y-%m-%d")),
                storage_method=it.get("storage_method", "냉장"),
                category=it.get("category"),
            )
            for it in items
        ]

    def _try_gpt(
        self, item_name: str, purchase_date: str, storage_method: str
    ) -> Optional[Dict[str, Any]]:
        client = self._get_openai_client()
        if client is None:
            return None

        prompt = (
            f"식재료 '{item_name}'의 소비기한을 계산해주세요.\n"
            f"- 구매일: {purchase_date}\n"
            f"- 보관방법: {storage_method}\n\n"
            f"JSON 형식으로 답변해주세요:\n"
            f'{{"shelf_life_days": 정수, "reason": "간단한 이유"}}'
        )

        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": "식품 안전 전문가입니다. 소비기한을 보수적으로 계산합니다."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_tokens=256,
            )
            text = response.choices[0].message.content.strip()
            text = text.replace("```json", "").replace("```", "").strip()
            data = json.loads(text)
            days = int(data.get("shelf_life_days", 7))
            reason = data.get("reason", "")

            pdate = datetime.strptime(purchase_date, "%Y-%m-%d")
            exp_date = pdate + timedelta(days=days)

            return {
                "item_name": item_name,
                "purchase_date": purchase_date,
                "storage_method": storage_method,
                "expiry_date": exp_date.strftime("%Y-%m-%d"),
                "confidence": 0.85,
                "method": "gpt-4o-mini",
                "reason": reason,
            }
        except Exception:
            return None

    def _rule_based(
        self, item_name: str, purchase_date: str,
        storage_method: str, category: Optional[str] = None,
    ) -> Dict[str, Any]:
        days = 7
        reason = "기본 보관 기준"

        for cat_name, cat_data in DEFAULT_SHELF_LIFE.items():
            items_dict = cat_data.get("items", {})
            for food, shelf in items_dict.items():
                if food in item_name:
                    if storage_method in shelf:
                        days = shelf[storage_method]
                        reason = f"{food} {storage_method} 기준 {days}일"
                    elif "냉장" in shelf:
                        days = shelf["냉장"]
                        reason = f"{food} 냉장 기준 {days}일 (기본값)"
                    break
            else:
                continue
            break
        else:
            if category:
                for cat_name, cat_data in DEFAULT_SHELF_LIFE.items():
                    if category in cat_name or cat_name in category:
                        days = cat_data.get(storage_method, cat_data.get("냉장", 7))
                        reason = f"{cat_name} 카테고리 {storage_method} 기준 {days}일"
                        break

        pdate = datetime.strptime(purchase_date, "%Y-%m-%d")
        exp_date = pdate + timedelta(days=days)

        return {
            "item_name": item_name,
            "purchase_date": purchase_date,
            "storage_method": storage_method,
            "expiry_date": exp_date.strftime("%Y-%m-%d"),
            "confidence": 0.7,
            "method": "rule-based",
            "reason": reason,
        }

    @staticmethod
    def _assess_risk(d_day: int) -> str:
        if d_day < 0:
            return "expired"
        if d_day <= 1:
            return "danger"
        if d_day <= 3:
            return "caution"
        return "safe"

    def generate_alerts(
        self, items: List[Dict[str, Any]], threshold_days: int = 3
    ) -> List[Dict[str, Any]]:
        """임박 품목을 탐지해 알림 트리거를 생성한다."""
        alerts = []
        for item in items:
            d_day = item.get("d_day", 999)
            if d_day <= threshold_days:
                alerts.append({
                    "item_name": item["item_name"],
                    "expiry_date": item.get("expiry_date", ""),
                    "d_day": d_day,
                    "risk_level": item.get("risk_level", "caution"),
                    "alert_type": "expiry_imminent",
                    "message": f"'{item['item_name']}'의 소비기한이 {d_day}일 남았습니다."
                               if d_day >= 0
                               else f"'{item['item_name']}'의 소비기한이 지났습니다.",
                })
        return alerts
