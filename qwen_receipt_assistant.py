"""
Qwen(오픈AI 호환 API) 영수증 OCR 보조 모듈

PaddleOCR 등으로 읽은 줄 텍스트를 넘겨 오타 보정·상품명 정리·비식품 제거를 수행합니다.
지원: Alibaba DashScope 호환 엔드포인트, Ollama(/v1), 기타 OpenAI 호환 서버.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore

try:
    from dotenv import load_dotenv
except ImportError:
    def load_dotenv(*_a: Any, **_k: Any) -> bool:
        return False


SYSTEM_PROMPT = """당신은 한국 마트 영수증 OCR 결과를 다듬는 도구입니다.

규칙:
- 입력 줄에서만 판단. 영수증에 없는 품목을 만들지 마세요.
- 명백한 OCR 오류만 고치세요. 예: 깨잎→깻잎, 감급→감귤, 500me→500ml, 방가루→빵가루.
- 실제 구매 식품만 넣으세요. 매장정보·헤더·바코드·합계·카드 줄은 제외.
- amount_krw는 결제 금액(원)입니다. 용량(g,ml) 숫자가 아닙니다. 불확실하면 null.
- 같은 상품을 중복 출력하지 마세요.
- JSON 배열만 출력하세요."""


def _strip_json_fence(text: str) -> str:
    text = text.strip()
    # Qwen3 <think>...</think> 태그 제거
    if "<think>" in text:
        think_end = text.rfind("</think>")
        if think_end != -1:
            text = text[think_end + len("</think>"):].strip()
        else:
            text = text.split("<think>")[0].strip()
    # ```json ... ``` 코드펜스 제거
    if "```json" in text:
        inner = text.split("```json", 1)[1]
        # 닫는 ``` 찾기 (마지막 것)
        close = inner.rfind("```")
        if close != -1:
            text = inner[:close]
        else:
            text = inner
    elif "```" in text:
        parts = text.split("```")
        if len(parts) >= 3:
            text = parts[1]
        elif len(parts) == 2:
            text = parts[1]
    return text.strip()


def _parse_llm_json(text: str) -> Dict[str, Any]:
    raw = _strip_json_fence(text)
    # 배열([...])로 바로 시작하는 경우 → {"items": [...]} 로 감싸기
    arr_start = raw.find("[")
    obj_start = raw.find("{")
    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        end = raw.rfind("]")
        if end == -1:
            raise json.JSONDecodeError("No closing bracket", raw, 0)
        items = json.loads(raw[arr_start:end + 1])
        return {"items": items}
    if obj_start == -1:
        raise json.JSONDecodeError("No JSON found", raw, 0)
    end = raw.rfind("}")
    if end == -1:
        raise json.JSONDecodeError("No closing brace", raw, 0)
    return json.loads(raw[obj_start:end + 1])


class QwenReceiptAssistant:
    """OCR 줄 목록을 Qwen에 넘겨 상품명 정리·오타 보정."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        load_dotenv(Path(__file__).resolve().parent / ".env")

        if OpenAI is None:
            raise ImportError("openai 패키지가 필요합니다. pip install openai")

        self.base_url = (
            base_url
            or (os.getenv("QWEN_BASE_URL") or "").strip()
            or self._detect_ollama_url()
            or None
        )
        self.api_key = (
            api_key
            or os.getenv("QWEN_API_KEY")
            or os.getenv("DASHSCOPE_API_KEY")
            or ("ollama" if self.base_url and "11434" in self.base_url else None)
        )
        self.model = (model or os.getenv("QWEN_MODEL", "qwen3:latest")).strip()

        # DashScope 키만 있고 URL 미지정이면 호환 엔드포인트 자동
        dash = os.getenv("DASHSCOPE_API_KEY")
        if not self.base_url and dash and self.api_key == dash:
            self.base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"

        if not self.api_key:
            raise ValueError(
                "API 키가 없습니다.\n"
                "  Ollama: ollama serve 실행 후 재시도\n"
                "  DashScope: DASHSCOPE_API_KEY 환경변수 설정\n"
                "  .env 파일에 QWEN_BASE_URL / QWEN_API_KEY / QWEN_MODEL 설정"
            )

        client_kw: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            client_kw["base_url"] = self.base_url
        self._client = OpenAI(**client_kw)

    @staticmethod
    def _prefilter_lines(ocr_lines: List[Dict[str, Any]]) -> List[tuple]:
        """OCR 줄에서 상품명+가격을 묶어 (idx, '상품명 | 가격원') 형태로 반환."""
        _SKIP = re.compile(
            r"사업자|전화|번호|주소|카드|승인|가맹점|계산대"
            r"|합\s*계|소\s*계|부가세|과세|면세|총액|지불|할인"
            r"|상품명|단가|수량|금액|판매일|신용|면세물품|과세물품"
        )
        _BARCODE = re.compile(r"^\d{8,}")
        _PRICE = re.compile(r"^[\d,]+\s*[#\*]?$")
        _ITEM_NO = re.compile(r"^\d{3}\s")

        texts = [str(l.get("text", "")).strip() for l in ocr_lines]
        result: List[tuple] = []
        i = 0
        while i < len(texts):
            t = texts[i]
            if not t or len(t) <= 1 or _SKIP.search(t) or _BARCODE.match(t) or _PRICE.match(t):
                i += 1
                continue
            # 상품번호 패턴(001, 002...)이거나 한글 포함 텍스트 → 상품 후보
            has_korean = any("\uac00" <= c <= "\ud7a3" for c in t)
            if has_korean or _ITEM_NO.match(t):
                price_str = ""
                # 다음 몇 줄에서 가격 찾기
                for j in range(i + 1, min(i + 4, len(texts))):
                    nxt = texts[j].replace("#", "").replace("*", "").replace("$", "").strip()
                    if _PRICE.match(nxt) or re.match(r"^[\d,]+$", nxt):
                        price_str = nxt
                        break
                    if _BARCODE.match(texts[j]):
                        continue
                    break
                display = t if not price_str else f"{t} | {price_str}원"
                result.append((i, display))
            i += 1
        return result

    @staticmethod
    def _detect_ollama_url() -> Optional[str]:
        """로컬 Ollama가 떠 있으면 URL을 반환, 아니면 None."""
        import urllib.request
        try:
            req = urllib.request.Request("http://localhost:11434/api/tags", method="GET")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    return "http://localhost:11434/v1"
        except Exception:
            pass
        return None

    def refine_ocr_lines(
        self,
        ocr_lines: List[Dict[str, Any]],
        *,
        temperature: float = 0.15,
        max_tokens: int = 16384,
    ) -> Dict[str, Any]:
        """
        Args:
            ocr_lines: [{"text": str, "confidence": float}, ...] 또는 run_ocr 결과와 동일 키

        Returns:
            {
                "items": [{"product_name", "amount_krw", "source_indices", "original_text_joined", "notes"}],
                "excluded_summary": str | None,
                "model": str,
                "raw_text": str (모델 원문),
            }
        """
        filtered = self._prefilter_lines(ocr_lines)

        numbered: List[str] = []
        for idx, t in filtered:
            numbered.append(f"{idx}\t{t}")

        user_content = (
            "아래는 영수증 OCR 줄입니다(번호\\t텍스트).\n"
            "실제 구매 식품만 골라 상품명의 OCR 오타를 보정하세요.\n"
            "amount_krw는 해당 상품의 결제 금액(원)입니다. 용량(g,ml)이 아닙니다. "
            "금액을 확신할 수 없으면 null로 두세요.\n"
            "JSON만 출력. 코드블록·설명 금지.\n"
            '[{"product_name":"보정된 상품명","amount_krw":금액정수 또는 null,'
            '"notes":"오타 수정 등, 없으면 빈 문자열"}]\n\n'
            + "\n".join(numbered)
        )

        resp = self._client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        raw_text = (resp.choices[0].message.content or "").strip()

        try:
            data = _parse_llm_json(raw_text)
        except json.JSONDecodeError:
            data = {"items": [], "parse_error": True}

        items = data.get("items") or []
        if not isinstance(items, list):
            items = []

        normalized: List[Dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            name = str(it.get("product_name", "")).strip()
            if not name:
                continue
            amt = it.get("amount_krw")
            if amt is not None and amt != "":
                try:
                    amt = int(str(amt).replace(",", ""))
                except (TypeError, ValueError):
                    amt = None
            else:
                amt = None
            normalized.append({
                "product_name": name,
                "amount_krw": amt,
                "notes": str(it.get("notes", "")).strip(),
            })

        return {
            "items": normalized,
            "model": self.model,
            "raw_text": raw_text,
        }

    def refine_analysis(
        self,
        analysis: Dict[str, Any],
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """receipt_ocr.analyze_receipt() 결과 dict에 넣어 호출."""
        texts = analysis.get("all_texts") or []
        lines: List[Dict[str, Any]] = []
        for t in texts:
            if isinstance(t, dict):
                lines.append({
                    "text": t.get("text", ""),
                    "confidence": t.get("confidence", 0),
                })
        return self.refine_ocr_lines(lines, **kwargs)


def print_refined_summary(refined: Dict[str, Any]) -> None:
    print("\n" + "=" * 50)
    print(" Qwen 보정 결과")
    print("=" * 50)
    print(f"모델: {refined.get('model')}")
    items = refined.get("items") or []
    print(f"\n[정리된 상품] ({len(items)}개)")
    print("-" * 50)
    for i, it in enumerate(items, 1):
        amt = it.get("amount_krw")
        amt_s = f"{amt:,}원" if isinstance(amt, int) else "-"
        notes = it.get("notes", "")
        notes_s = f"  ({notes})" if notes else ""
        print(f"  {i}. {it['product_name']:<30s}  {amt_s:>10s}{notes_s}")
    print("=" * 50)


def main() -> None:
    if len(sys.argv) < 2:
        print("사용법:")
        print("  python qwen_receipt_assistant.py <영수증_이미지>")
        print("  (선택) 환경변수: QWEN_API_KEY, QWEN_BASE_URL, QWEN_MODEL")
        print("  DashScope 예: QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1")
        print("  Ollama 예: QWEN_BASE_URL=http://localhost:11434/v1 QWEN_API_KEY=ollama QWEN_MODEL=qwen2.5:latest")
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
