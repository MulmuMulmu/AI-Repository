from __future__ import annotations

import importlib.util
import json
import os
import urllib.error
import urllib.request

from .env import load_local_env


load_local_env()


DEFAULT_QWEN_MODEL_ID = "Qwen/Qwen2.5-1.5B-Instruct"
DEFAULT_RECEIPT_EXTRACT_MAX_NEW_TOKENS = 160
DEFAULT_RECEIPT_ITEM_MAX_NEW_TOKENS = 64
DEFAULT_RECIPE_EXPLANATION_MAX_NEW_TOKENS = 160


def extract_json_object(text: str) -> dict | None:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None

    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _filter_receipt_refinement_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None

    filtered: dict = {}
    purchased_at = payload.get("purchased_at")
    if isinstance(purchased_at, str) and purchased_at.strip():
        filtered["purchased_at"] = purchased_at

    items = payload.get("items")
    if isinstance(items, list):
        filtered_items = []
        for item in items:
            if not isinstance(item, dict):
                continue

            cleaned: dict = {}
            index = item.get("index")
            if isinstance(index, int) and not isinstance(index, bool):
                cleaned["index"] = index

            for key in (
                "raw_name",
                "normalized_name",
                "category",
                "storage_type",
                "unit",
            ):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value

            for key in ("quantity", "amount", "confidence"):
                value = item.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cleaned[key] = value

            is_low_confidence = item.get("is_low_confidence")
            if isinstance(is_low_confidence, bool):
                cleaned["is_low_confidence"] = is_low_confidence

            if cleaned:
                filtered_items.append(cleaned)

        filtered["items"] = filtered_items

    return filtered if filtered else None


def _filter_receipt_extraction_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None

    filtered: dict = {}
    for key in ("vendor_name", "purchased_at"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            filtered[key] = value.strip()

    confidence = payload.get("confidence")
    if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
        filtered["confidence"] = confidence

    review_required = payload.get("review_required")
    if isinstance(review_required, bool):
        filtered["review_required"] = review_required

    review_reasons = payload.get("review_reasons")
    if isinstance(review_reasons, list):
        cleaned_reasons = [value.strip() for value in review_reasons if isinstance(value, str) and value.strip()]
        if cleaned_reasons:
            filtered["review_reasons"] = cleaned_reasons

    totals = payload.get("totals")
    if isinstance(totals, dict):
        cleaned_totals: dict[str, float] = {}
        for key in ("subtotal", "tax", "total", "payment_amount"):
            value = totals.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cleaned_totals[key] = float(value)
        if cleaned_totals:
            filtered["totals"] = cleaned_totals

    items = payload.get("items")
    if isinstance(items, list):
        filtered_items = []
        for item in items:
            if not isinstance(item, dict):
                continue

            cleaned: dict = {}
            for key in ("raw_name", "normalized_name", "category", "storage_type", "unit"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    cleaned[key] = value.strip()

            for key in ("quantity", "amount", "confidence", "match_confidence"):
                value = item.get(key)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    cleaned[key] = value

            source_line_ids = item.get("source_line_ids")
            if isinstance(source_line_ids, list):
                cleaned_line_ids = [value for value in source_line_ids if isinstance(value, int) and not isinstance(value, bool)]
                if cleaned_line_ids:
                    cleaned["source_line_ids"] = cleaned_line_ids

            if cleaned:
                filtered_items.append(cleaned)

        filtered["items"] = filtered_items

    return filtered if filtered else None


def _filter_receipt_header_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None

    filtered: dict = {}
    for key in ("vendor_name", "purchased_at"):
        value = payload.get(key)
        if value is None:
            filtered[key] = None
        elif isinstance(value, str):
            cleaned = value.strip()
            filtered[key] = cleaned or None

    return filtered if filtered else None


def _filter_receipt_item_normalization_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None

    items = payload.get("items")
    rescued_items = payload.get("rescued_items")
    if not isinstance(items, list):
        items = []
    if not isinstance(rescued_items, list):
        rescued_items = []
    if not items and not rescued_items:
        return None

    filtered_items = []
    for item in items:
        if not isinstance(item, dict):
            continue

        cleaned: dict = {}
        index = item.get("index")
        if isinstance(index, int) and not isinstance(index, bool):
            cleaned["index"] = index

        for key in ("raw_name", "normalized_name", "unit"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                cleaned[key] = value.strip()

        for key in ("quantity", "amount"):
            value = item.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cleaned[key] = value

        if cleaned:
            filtered_items.append(cleaned)

    filtered_rescued_items = []
    for item in rescued_items:
        if not isinstance(item, dict):
            continue

        cleaned: dict = {}
        for key in ("raw_name", "normalized_name", "unit"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                cleaned[key] = value.strip()

        for key in ("quantity", "amount"):
            value = item.get(key)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cleaned[key] = value

        source_line_ids = item.get("source_line_ids")
        if isinstance(source_line_ids, list):
            cleaned_line_ids = [value for value in source_line_ids if isinstance(value, int) and not isinstance(value, bool)]
            if cleaned_line_ids:
                cleaned["source_line_ids"] = cleaned_line_ids

        if cleaned:
            filtered_rescued_items.append(cleaned)

    filtered: dict[str, object] = {}
    if filtered_items:
        filtered["items"] = filtered_items
    if filtered_rescued_items:
        filtered["rescued_items"] = filtered_rescued_items
    return filtered or None


def _filter_recipe_explanation_payload(payload: object) -> dict | None:
    if not isinstance(payload, dict):
        return None

    filtered: dict = {}

    recommendation_reason = payload.get("recommendation_reason")
    if isinstance(recommendation_reason, str) and recommendation_reason.strip():
        filtered["recommendation_reason"] = recommendation_reason

    substitute_ingredients = payload.get("substitute_ingredients")
    if isinstance(substitute_ingredients, list):
        cleaned_substitutes = [
            value
            for value in substitute_ingredients
            if isinstance(value, str) and value.strip()
        ]
        filtered["substitute_ingredients"] = cleaned_substitutes

    share_message = payload.get("share_message")
    if isinstance(share_message, str) and share_message.strip():
        filtered["share_message"] = share_message

    return filtered if filtered else None


class NoopQwenProvider:
    def rescue_receipt_header(self, payload: dict) -> dict | None:
        return None

    def extract_receipt(self, payload: dict) -> dict | None:
        return None

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        return None

    def refine_receipt(self, payload: dict) -> dict | None:
        return self.extract_receipt(payload)

    def explain_recipe(self, payload: dict) -> dict | None:
        return None

    def describe_recipe(self, payload: dict) -> dict | None:
        return self.explain_recipe(payload)


class LocalTransformersQwenProvider:
    def __init__(
        self,
        model_id: str | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.model_id = model_id or os.environ.get("LOCAL_QWEN_MODEL_ID", DEFAULT_QWEN_MODEL_ID)
        self.enabled = enabled if enabled is not None else os.environ.get("ENABLE_LOCAL_QWEN") == "1"
        self._tokenizer = None
        self._model = None

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_header_prompt(payload)
        return _filter_receipt_header_payload(
            extract_json_object(
                self._call_generate_text(
                    prompt,
                    max_new_tokens=32,
                )
            )
        )

    def extract_receipt(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_prompt(payload)
        return _filter_receipt_extraction_payload(
            extract_json_object(
                self._call_generate_text(
                    prompt,
                    max_new_tokens=self._receipt_extract_max_new_tokens(),
                )
            )
        )

    def refine_receipt(self, payload: dict) -> dict | None:
        return self.extract_receipt(payload)

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_item_prompt(payload)
        return _filter_receipt_item_normalization_payload(
            extract_json_object(
                self._call_generate_text(
                    prompt,
                    max_new_tokens=self._receipt_item_max_new_tokens(),
                )
            )
        )

    def explain_recipe(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_recipe_prompt(payload)
        return _filter_recipe_explanation_payload(
            extract_json_object(
                self._call_generate_text(
                    prompt,
                    max_new_tokens=self._recipe_explanation_max_new_tokens(),
                )
            )
        )

    def describe_recipe(self, payload: dict) -> dict | None:
        return self.explain_recipe(payload)

    def _build_receipt_prompt(self, payload: dict) -> str:
        return (
            "receipt extraction\n"
            "Return strict JSON only with keys vendor_name, purchased_at, items, totals, confidence, review_required, review_reasons.\n"
            "Each item may include raw_name, normalized_name, category, storage_type, quantity, unit, amount, source_line_ids.\n"
            "Use only OCR evidence from merged rows and raw tokens. Omit uncertain fields instead of inventing values.\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _build_receipt_header_prompt(self, payload: dict) -> str:
        return (
            "receipt header rescue\n"
            "Return one-line minified JSON only.\n"
            "Schema: {\"vendor_name\":null,\"purchased_at\":null}\n"
            "Examples:\n"
            "Input: {\"top_strip_rows\":[\"GS25\",\"2023-11-24 00:01:04\"]}\n"
            "Output: {\"vendor_name\":\"GS25\",\"purchased_at\":\"2023-11-24\"}\n"
            "Input: {\"top_strip_rows\":[\"re-MART\",\"2024-09-12 18:59\"]}\n"
            "Output: {\"vendor_name\":\"re-MART\",\"purchased_at\":\"2024-09-12\"}\n"
            "Rules:\n"
            "- Use only OCR evidence from merged_rows, raw_tokens, top_strip_rows.\n"
            "- Prefer top_strip_rows over merged_rows.\n"
            "- purchased_at must be YYYY-MM-DD or null.\n"
            "- If an exact date is visible, do not return null.\n"
            "- vendor_name must be a short plausible store name or null.\n"
            "- Never echo raw OCR gibberish, product names, item headers, or numeric fragments as vendor_name.\n"
            "- If uncertain, return null.\n"
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _build_receipt_item_prompt(self, payload: dict) -> str:
        return (
            "receipt item normalization\n"
            "Return one-line minified JSON only.\n"
            "Schema: {\"items\":[{\"index\":0,\"normalized_name\":\"\",\"quantity\":0,\"unit\":\"\",\"amount\":0}],\"rescued_items\":[{\"raw_name\":\"\",\"normalized_name\":\"\",\"quantity\":0,\"unit\":\"\",\"amount\":0,\"source_line_ids\":[0,1]}]}\n"
            "Use source_lines first, then context_lines if source_lines are incomplete.\n"
            "If collapsed_item_name_rows are provided, you may return rescued_items only when the OCR detail row clearly supports a missing product.\n"
            "Do not copy collapsed name_text like ()2 as raw_name. Use a plausible product name or omit rescued_items.\n"
            "For rescued_items, unit must be a plausible merchandise unit such as 개, 봉, 팩, 병, 캔, 입, g, kg, ml, L. Never return a numeric unit like 1.\n"
            "You may correct OCR typos in normalized_name when review_reasons include low_confidence.\n"
            "Prefer current numeric values unless a field is missing. Do not invent extra items beyond collapsed_item_name_rows.\n"
            "Use only OCR rows. No English slugs, product codes, or unrelated guesses.\n"
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _build_recipe_prompt(self, payload: dict) -> str:
        return (
            "recipe explanation\n"
            "Return strict JSON only with keys recommendation_reason, substitute_ingredients, share_message.\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _runtime_available(self) -> bool:
        return (
            self.enabled
            and importlib.util.find_spec("transformers") is not None
            and importlib.util.find_spec("torch") is not None
            and os.environ.get("ALLOW_MODEL_DOWNLOAD") == "1"
        )

    def _receipt_extract_max_new_tokens(self) -> int:
        return int(os.environ.get("LOCAL_QWEN_RECEIPT_EXTRACT_MAX_NEW_TOKENS", DEFAULT_RECEIPT_EXTRACT_MAX_NEW_TOKENS))

    def _receipt_item_max_new_tokens(self) -> int:
        return int(os.environ.get("LOCAL_QWEN_RECEIPT_ITEM_MAX_NEW_TOKENS", DEFAULT_RECEIPT_ITEM_MAX_NEW_TOKENS))

    def _recipe_explanation_max_new_tokens(self) -> int:
        return int(os.environ.get("LOCAL_QWEN_RECIPE_EXPLANATION_MAX_NEW_TOKENS", DEFAULT_RECIPE_EXPLANATION_MAX_NEW_TOKENS))

    def _generate_text(self, prompt: str, *, max_new_tokens: int) -> str:
        tokenizer, model = self._load_model()
        if hasattr(tokenizer, "apply_chat_template"):
            model_inputs = tokenizer.apply_chat_template(
                [
                    {"role": "system", "content": "Return strict JSON only."},
                    {"role": "user", "content": prompt},
                ],
                tokenize=True,
                add_generation_prompt=True,
                return_tensors="pt",
            )
            if hasattr(model_inputs, "__getitem__") and "input_ids" in model_inputs:
                prompt_input_ids = model_inputs["input_ids"]
                outputs = model.generate(
                    **model_inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
            else:
                prompt_input_ids = model_inputs
                outputs = model.generate(
                    model_inputs,
                    max_new_tokens=max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
            prompt_length = prompt_input_ids.shape[-1]
            generated_ids = outputs[0][prompt_length:]
            return tokenizer.decode(generated_ids, skip_special_tokens=True)

        inputs = tokenizer(prompt, return_tensors="pt")
        prompt_length = inputs["input_ids"].shape[-1]
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
        generated_ids = outputs[0][prompt_length:]
        return tokenizer.decode(generated_ids, skip_special_tokens=True)

    def _call_generate_text(self, prompt: str, *, max_new_tokens: int) -> str:
        try:
            return self._generate_text(prompt, max_new_tokens=max_new_tokens)
        except TypeError:
            return self._generate_text(prompt)  # type: ignore[misc]

    def _load_model(self):
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model

        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(self.model_id, trust_remote_code=True)
        self._model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            trust_remote_code=True,
        )
        return self._tokenizer, self._model


def local_qwen_enabled() -> bool:
    return os.environ.get("ENABLE_LOCAL_QWEN") == "1"


def local_qwen_runtime_available() -> bool:
    return (
        local_qwen_enabled()
        and importlib.util.find_spec("transformers") is not None
        and importlib.util.find_spec("torch") is not None
        and os.environ.get("ALLOW_MODEL_DOWNLOAD") == "1"
    )


def openai_compatible_qwen_enabled() -> bool:
    return bool(
        os.environ.get("QWEN_OPENAI_COMPATIBLE_BASE_URL", "").strip()
        and os.environ.get("QWEN_OPENAI_COMPATIBLE_API_KEY", "").strip()
        and os.environ.get("QWEN_OPENAI_COMPATIBLE_MODEL", "").strip()
    )


class OpenAICompatibleQwenProvider:
    def __init__(self) -> None:
        self.base_url = os.environ.get("QWEN_OPENAI_COMPATIBLE_BASE_URL", "").strip()
        self.api_key = os.environ.get("QWEN_OPENAI_COMPATIBLE_API_KEY", "").strip()
        self.model = os.environ.get("QWEN_OPENAI_COMPATIBLE_MODEL", "").strip()
        timeout_value = os.environ.get("QWEN_OPENAI_COMPATIBLE_TIMEOUT_SECONDS", "30").strip()
        self.timeout_seconds = float(timeout_value) if timeout_value else 30.0

    def rescue_receipt_header(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_header_prompt(payload)
        return _filter_receipt_header_payload(
            extract_json_object(self._generate_text(prompt))
        )

    def extract_receipt(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_prompt(payload)
        return _filter_receipt_extraction_payload(
            extract_json_object(self._generate_text(prompt))
        )

    def refine_receipt(self, payload: dict) -> dict | None:
        return self.extract_receipt(payload)

    def normalize_receipt_items(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_receipt_item_prompt(payload)
        return _filter_receipt_item_normalization_payload(
            extract_json_object(self._generate_text(prompt))
        )

    def explain_recipe(self, payload: dict) -> dict | None:
        if not self._runtime_available():
            return None
        prompt = self._build_recipe_prompt(payload)
        return _filter_recipe_explanation_payload(
            extract_json_object(self._generate_text(prompt))
        )

    def describe_recipe(self, payload: dict) -> dict | None:
        return self.explain_recipe(payload)

    def _runtime_available(self) -> bool:
        return bool(self.base_url and self.api_key and self.model)

    def _build_receipt_prompt(self, payload: dict) -> str:
        return (
            "receipt extraction\n"
            "Return strict JSON only with keys vendor_name, purchased_at, items, totals, confidence, review_required, review_reasons.\n"
            "Each item may include raw_name, normalized_name, category, storage_type, quantity, unit, amount, source_line_ids.\n"
            "Use only OCR evidence from merged rows and raw tokens. Omit uncertain fields instead of inventing values.\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _build_receipt_header_prompt(self, payload: dict) -> str:
        return (
            "receipt header rescue\n"
            "Return one-line minified JSON only.\n"
            "Schema: {\"vendor_name\":null,\"purchased_at\":null}\n"
            "Examples:\n"
            "Input: {\"top_strip_rows\":[\"GS25\",\"2023-11-24 00:01:04\"]}\n"
            "Output: {\"vendor_name\":\"GS25\",\"purchased_at\":\"2023-11-24\"}\n"
            "Input: {\"top_strip_rows\":[\"re-MART\",\"2024-09-12 18:59\"]}\n"
            "Output: {\"vendor_name\":\"re-MART\",\"purchased_at\":\"2024-09-12\"}\n"
            "Rules:\n"
            "- Use only OCR evidence from merged_rows, raw_tokens, top_strip_rows.\n"
            "- Prefer top_strip_rows over merged_rows.\n"
            "- purchased_at must be YYYY-MM-DD or null.\n"
            "- If an exact date is visible, do not return null.\n"
            "- vendor_name must be a short plausible store name or null.\n"
            "- Never echo raw OCR gibberish, product names, item headers, or numeric fragments as vendor_name.\n"
            "- If uncertain, return null.\n"
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _build_receipt_item_prompt(self, payload: dict) -> str:
        return (
            "receipt item normalization\n"
            "Return strict JSON only with key items.\n"
            "Return strict JSON only with keys items and optional rescued_items.\n"
            "Each item must include index and may include normalized_name, quantity, unit, amount.\n"
            "Each rescued_item may include raw_name, normalized_name, quantity, unit, amount, source_line_ids.\n"
            "Use source_lines first, then context_lines if source_lines are incomplete.\n"
            "If collapsed_item_name_rows are provided, only rescue a missing item when the OCR detail row clearly supports it.\n"
            "Do not copy collapsed name_text like ()2 as raw_name. Use a plausible product name or omit rescued_items.\n"
            "For rescued_items, unit must be a plausible merchandise unit such as 개, 봉, 팩, 병, 캔, 입, g, kg, ml, L. Never return a numeric unit like 1.\n"
            "You may correct OCR typos in normalized_name when review_reasons include low_confidence.\n"
            "Prefer current numeric values unless a field is missing. Do not invent extra items beyond collapsed_item_name_rows.\n"
            "Use only the provided OCR rows. Do not invent English slugs, product codes, or unrelated guesses.\n"
            f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
        )

    def _build_recipe_prompt(self, payload: dict) -> str:
        return (
            "recipe explanation\n"
            "Return strict JSON only with keys recommendation_reason, substitute_ingredients, share_message.\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

    def _generate_text(self, prompt: str) -> str | None:
        response = self._post_chat_completion(
            messages=[
                {
                    "role": "system",
                    "content": "Return strict JSON only.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ]
        )
        if not response:
            return None
        return response

    def _post_chat_completion(self, messages: list[dict[str, str]]) -> str | None:
        url = self._chat_completions_url()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0,
        }
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except (urllib.error.URLError, TimeoutError, ValueError):
            return None

        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            return None

        if not isinstance(parsed, dict):
            return None

        choices = parsed.get("choices")
        if not isinstance(choices, list) or not choices:
            return None

        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            return None

        message = first_choice.get("message")
        if not isinstance(message, dict):
            return None

        content = message.get("content")
        if isinstance(content, str):
            return content

        return None

    def _chat_completions_url(self) -> str:
        base_url = self.base_url.rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        return f"{base_url}/chat/completions"


def build_default_qwen_provider() -> object:
    if openai_compatible_qwen_enabled():
        return OpenAICompatibleQwenProvider()
    if local_qwen_enabled():
        return LocalTransformersQwenProvider()
    return NoopQwenProvider()


def qwen_runtime_available() -> bool:
    return openai_compatible_qwen_enabled() or local_qwen_runtime_available()
