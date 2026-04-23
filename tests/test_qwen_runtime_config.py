from __future__ import annotations

import sys
import types

import ocr_qwen.qwen as qwen_module
from ocr_qwen.qwen import LocalTransformersQwenProvider


def test_local_qwen_provider_honors_device_map_and_torch_dtype_env(monkeypatch) -> None:
    captured: dict[str, object] = {}

    fake_transformers = types.SimpleNamespace(
        AutoTokenizer=types.SimpleNamespace(from_pretrained=lambda *args, **kwargs: object()),
        AutoModelForCausalLM=types.SimpleNamespace(
            from_pretrained=lambda model_id, **kwargs: captured.update(
                {"model_id": model_id, **kwargs}
            )
            or types.SimpleNamespace(device="cuda:0")
        ),
    )
    fake_torch = types.SimpleNamespace(float16="float16-dtype")

    monkeypatch.setitem(sys.modules, "transformers", fake_transformers)
    monkeypatch.setitem(sys.modules, "torch", fake_torch)
    monkeypatch.setattr(
        qwen_module.importlib.util,
        "find_spec",
        lambda name: object() if name == "torch" else None,
    )
    monkeypatch.setenv("LOCAL_QWEN_DEVICE_MAP", "auto")
    monkeypatch.setenv("LOCAL_QWEN_TORCH_DTYPE", "float16")

    provider = LocalTransformersQwenProvider(model_id="Qwen/test-model", enabled=True)

    provider._load_model()

    assert captured["model_id"] == "Qwen/test-model"
    assert captured["trust_remote_code"] is True
    assert captured["device_map"] == "auto"
    assert captured["torch_dtype"] == "float16-dtype"


def test_local_qwen_provider_prefers_cuda_device_from_hf_device_map() -> None:
    provider = LocalTransformersQwenProvider(enabled=True)
    model = types.SimpleNamespace(hf_device_map={"model.embed_tokens": "cuda:0"})

    assert provider._resolve_input_device(model) == "cuda:0"
