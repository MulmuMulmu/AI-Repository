"""
Qwen 보조 모듈.

기본 동작은 즉시 rule fallback이며, 명시적으로 환경변수를 켠 경우에만
Qwen 보조 경로를 동기 호출한다. 이렇게 해야 API 경로가
로컬 CPU LLM 때문에 멈추지 않는다.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_args: Any, **_kwargs: Any) -> bool:
        return False


SYSTEM_PROMPT = """당신은 한국 영수증 OCR 구조화 보조기입니다.

규칙:
- 입력에 없는 상품을 만들지 마세요.
- 출력은 JSON 배열만 허용됩니다.
- 각 원소는 product_name, amount_krw, notes만 가집니다.
- 식품이 아닌 항목은 제외하세요.
- amount_krw는 금액(원)만 사용하고, 불확실하면 null로 두세요.
"""


def _strip_json_fence(text: str) -> str:
    value = text.strip()
    if "<think>" in value and "</think>" in value:
        value = value.split("</think>", 1)[1].strip()
    if "```json" in value:
        value = value.split("```json", 1)[1]
        value = value.rsplit("```", 1)[0]
    elif "```" in value:
        value = value.split("```", 1)[1]
        value = value.rsplit("```", 1)[0]
    return value.strip()


class QwenReceiptAssistant:
    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        load_dotenv(Path(__file__).resolve().parent / ".env")

        self.enabled = os.getenv("ENABLE_SYNC_QWEN_RECEIPT_ASSISTANT", "0") == "1"
        self.base_url = (base_url or os.getenv("QWEN_BASE_URL") or "").strip()
        self.api_key = (
            api_key
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ""
        ).strip()
        self.model = (model or os.getenv("QWEN_MODEL") or "qwen2.5:latest").strip()
        self.timeout_seconds = float(os.getenv("QWEN_TIMEOUT_SECONDS", "8"))
        self.max_tokens = int(os.getenv("QWEN_RECEIPT_MAX_TOKENS", "256"))
        self._client = self._build_client()

    def _build_client(self) -> Any:
        if not self.enabled:
            return None
        if OpenAI is None:
            return None
        if not self.base_url or not self.api_key:
            return None
        try:
            return OpenAI(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout_seconds,
            )
        except Exception:
            return None

    def is_active(self) -> bool:
        return self._client is not None

    def status_summary(self) -> str:
        if self._client is not None:
            return f"configured:{self.model}"
        if not self.enabled:
            return "disabled_by_default"
        if OpenAI is None:
            return "disabled(openai_missing)"
        if not self.base_url:
            return "disabled(base_url_missing)"
        if not self.api_key:
            return "disabled(api_key_missing)"
        return "disabled(init_failed)"

    def refine_ocr_lines(
        self,
        ocr_lines: List[Dict[str, Any]],
        *,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        analysis = {
            "all_texts": ocr_lines,
            "food_items": [],
            "model": "ocr_only",
        }
        return self.refine_analysis(analysis, temperature=temperature)

    def refine_analysis(
        self,
        analysis: Dict[str, Any],
        *,
        temperature: float = 0.1,
    ) -> Dict[str, Any]:
        fallback = self._build_rule_fallback(analysis)
        if self._client is None:
            return fallback

        merged_rows = []
        for row in analysis.get("all_texts", []):
            if not isinstance(row, dict):
                continue
            text = str(row.get("text", "")).strip()
            if not text:
                continue
            merged_rows.append(text)

        if not merged_rows:
            return fallback

        try:
            raw_text = self._request_qwen(merged_rows, temperature=temperature)
            items = self._parse_response_items(raw_text)
            normalized = self._normalize_items(items)
            if not normalized:
                return fallback
            return {
                "items": normalized,
                "model": self.model,
                "raw_text": raw_text,
            }
        except Exception:
            return fallback

    def _request_qwen(self, merged_rows: list[str], *, temperature: float) -> str:
        prompt = (
            "다음 영수증 OCR 행에서 실제 식품 상품만 골라 JSON 배열로 반환하세요.\n"
            '[{"product_name":"", "amount_krw": null, "notes": ""}]\n'
            "OCR 행:\n"
            + "\n".join(f"- {row}" for row in merged_rows)
        )
        response = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=temperature,
            max_tokens=self.max_tokens,
        )
        return (response.choices[0].message.content or "").strip()

    def _parse_response_items(self, raw_text: str) -> list[dict[str, Any]]:
        payload = _strip_json_fence(raw_text)
        data = json.loads(payload)
        return data if isinstance(data, list) else []

    def _normalize_items(self, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        seen: set[tuple[str, Optional[int]]] = set()
        for item in items:
            if not isinstance(item, dict):
                continue
            product_name = str(item.get("product_name", "")).strip()
            if not product_name:
                continue
            if self._looks_invalid_name(product_name):
                continue

            amount_krw = item.get("amount_krw")
            if amount_krw is not None and amount_krw != "":
                try:
                    amount_krw = int(str(amount_krw).replace(",", ""))
                except (TypeError, ValueError):
                    amount_krw = None
            else:
                amount_krw = None

            dedupe_key = (product_name, amount_krw)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            normalized.append(
                {
                    "product_name": product_name,
                    "amount_krw": amount_krw,
                    "notes": str(item.get("notes", "")).strip(),
                }
            )
        return normalized

    def _build_rule_fallback(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, Optional[int]]] = set()
        for item in analysis.get("food_items", []):
            if not isinstance(item, dict):
                continue
            product_name = str(item.get("product_name") or item.get("name") or "").strip()
            if not product_name:
                continue
            amount_krw = item.get("amount_krw")
            if amount_krw is not None and amount_krw != "":
                try:
                    amount_krw = int(str(amount_krw).replace(",", ""))
                except (TypeError, ValueError):
                    amount_krw = None
            else:
                amount_krw = None

            dedupe_key = (product_name, amount_krw)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)

            items.append(
                {
                    "product_name": product_name,
                    "amount_krw": amount_krw,
                    "notes": str(item.get("notes", "")).strip(),
                }
            )

        return {
            "items": items,
            "model": f"rule_fallback ({self.status_summary()})",
            "raw_text": "",
        }

    def _looks_invalid_name(self, value: str) -> bool:
        blocked = (
            "봉투",
            "비닐",
            "카드",
            "결제",
            "합계",
            "과세",
            "면세",
            "부가세",
            "승인",
        )
        return any(token in value for token in blocked)


def print_refined_summary(refined: Dict[str, Any]) -> None:
    print("\n" + "=" * 50)
    print(" Qwen 보정 결과")
    print("=" * 50)
    print(f"모델: {refined.get('model')}")
    items = refined.get("items") or []
    print(f"\n[정리된 상품] ({len(items)}개)")
    print("-" * 50)
    for index, item in enumerate(items, 1):
        amount = item.get("amount_krw")
        amount_text = f"{amount:,}원" if isinstance(amount, int) else "-"
        notes = item.get("notes", "")
        notes_text = f"  ({notes})" if notes else ""
        print(f"  {index}. {item['product_name']:<30s}  {amount_text:>10s}{notes_text}")
    print("=" * 50)


def main() -> None:
    import sys

    if len(sys.argv) < 2:
        print("사용법: python qwen_receipt_assistant.py <영수증_이미지>")
        return

    from receipt_ocr import ReceiptOCR

    image_path = sys.argv[1]
    ocr = ReceiptOCR()
    analysis = ocr.analyze_receipt(image_path)

    assistant = QwenReceiptAssistant()
    refined = assistant.refine_analysis(analysis)
    print_refined_summary(refined)


if __name__ == "__main__":
    main()
