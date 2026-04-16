"""
나눔 금지 품목 1차 필터링 모듈

설계서 요구사항:
  - 나눔 게시글 작성 시 이름 기반으로 금지 품목을 1차 필터링
  - 위험 식품 후보는 운영 검수 흐름으로 전달
  - 개봉된 반찬·생고기·생선·조리된 음식 필터링
"""

from __future__ import annotations

import re
from typing import Any, Dict, List


BLOCKED_CATEGORIES: Dict[str, List[str]] = {
    "생고기/생선": [
        "생고기", "생선회", "회", "육회", "생닭", "생삼겹",
        "날고기", "생등심", "생갈비",
    ],
    "개봉 반찬/조리 음식": [
        "반찬", "조리음식", "밑반찬", "국", "찌개", "볶음",
        "조림", "무침", "샐러드", "도시락",
    ],
    "유제품(개봉)": [
        "개봉우유", "개봉요거트",
    ],
}

REVIEW_REQUIRED_KEYWORDS: List[str] = [
    "수제", "직접만든", "홈메이드", "집밥",
    "개봉", "뜯은",
    "냉장", "냉동", "해동",
]

_BLOCKED_RE = re.compile(
    "|".join(
        kw for keywords in BLOCKED_CATEGORIES.values() for kw in keywords
    ),
    re.IGNORECASE,
)

_REVIEW_RE = re.compile(
    "|".join(re.escape(kw) for kw in REVIEW_REQUIRED_KEYWORDS),
    re.IGNORECASE,
)

SAFE_CATEGORIES: List[str] = [
    "미개봉 가공식품",
    "건강기능식품",
    "통조림",
    "건조식품",
    "곡류",
    "과일/채소(미가공)",
]


class SharingFilter:
    """나눔 금지 품목 1차 필터링 엔진."""

    def check(self, item_names: List[str]) -> Dict[str, Any]:
        """
        품목명 목록을 검사하여 차단/검수/허용을 판별한다.

        Returns:
            {
                "blocked": [{"item_name": str, "reason": str, "category": str}],
                "review_required": [{"item_name": str, "reason": str}],
                "allowed": [{"item_name": str}],
                "summary": {"blocked": int, "review": int, "allowed": int},
            }
        """
        blocked = []
        review_required = []
        allowed = []

        for name in item_names:
            result = self._check_single(name)
            if result["status"] == "blocked":
                blocked.append(result)
            elif result["status"] == "review_required":
                review_required.append(result)
            else:
                allowed.append({"item_name": name})

        return {
            "blocked": blocked,
            "review_required": review_required,
            "allowed": allowed,
            "summary": {
                "blocked": len(blocked),
                "review": len(review_required),
                "allowed": len(allowed),
            },
        }

    def _check_single(self, item_name: str) -> Dict[str, Any]:
        m = _BLOCKED_RE.search(item_name)
        if m:
            matched_kw = m.group()
            category = self._find_block_category(matched_kw)
            return {
                "item_name": item_name,
                "status": "blocked",
                "reason": f"나눔 금지 품목: {category}",
                "category": category,
            }

        m = _REVIEW_RE.search(item_name)
        if m:
            return {
                "item_name": item_name,
                "status": "review_required",
                "reason": f"검수 필요 키워드 포함: '{m.group()}'",
            }

        return {"item_name": item_name, "status": "allowed"}

    @staticmethod
    def _find_block_category(keyword: str) -> str:
        for cat, keywords in BLOCKED_CATEGORIES.items():
            if keyword in keywords:
                return cat
        return "기타 금지 품목"
