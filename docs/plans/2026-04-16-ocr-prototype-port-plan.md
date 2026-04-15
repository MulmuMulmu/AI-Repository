# OCR Prototype Port Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Keep the current AI repository API surface, but replace the OCR internals with the prototype receipt pipeline so runtime behavior and accuracy are aligned with the prototype baseline.

**Architecture:** Add the prototype `ocr_qwen` package to this repository with its supporting generated ingredient data. Keep `main.py` as the public FastAPI entrypoint, but route `/api/ocr/receipt` through the prototype-style `ReceiptParseService` and adapt its richer parse result to the current legacy contract. Keep root wrapper files for backward compatibility, but make them delegate into the ported package.

**Tech Stack:** FastAPI, PaddleOCR, Pillow, httpx, pytest

---

### Task 1: Port the prototype OCR package and generated ingredient assets

**Files:**
- Create: `ocr_qwen/__init__.py`
- Create: `ocr_qwen/app.py`
- Create: `ocr_qwen/env.py`
- Create: `ocr_qwen/ingredient_dictionary.py`
- Create: `ocr_qwen/preprocess.py`
- Create: `ocr_qwen/qwen.py`
- Create: `ocr_qwen/receipts.py`
- Create: `ocr_qwen/services.py`
- Create: `ocr_qwen/expiry.py`
- Create: `ocr_qwen/recommendations.py`
- Create: `data/ingredient_master.generated.json`
- Create: `data/ingredient_alias.generated.json`

**Step 1: Copy prototype OCR runtime modules into the AI repository**

Source modules from:
- `C:\Users\USER-PC\Desktop\jp\.worktrees\codex-ai-multi-agent\prototype\ocr_qwen`

**Step 2: Copy generated ingredient lookup data into the AI repository**

Source files from:
- `C:\Users\USER-PC\Desktop\jp\.worktrees\codex-ai-multi-agent\prototype\data\ingredient_master.generated.json`
- `C:\Users\USER-PC\Desktop\jp\.worktrees\codex-ai-multi-agent\prototype\data\ingredient_alias.generated.json`

**Step 3: Verify imports resolve locally**

Run:

```powershell
python -c "from ocr_qwen.services import ReceiptParseService; print('ok')"
```

Expected: `ok`

### Task 2: Replace current OCR endpoint internals with the prototype parse service

**Files:**
- Modify: `main.py`
- Modify: `receipt_ocr.py`
- Modify: `qwen_receipt_assistant.py`

**Step 1: Keep current endpoint path and response contract**

The endpoint must remain:

```text
POST /api/ocr/receipt
```

The response must still contain:
- `ocr_texts`
- `food_items`
- `food_count`
- `model`

**Step 2: Add adapter functions from prototype parse output to current legacy output**

Map prototype parse result fields into:

```json
{
  "ocr_texts": [{"text":"", "confidence":0.0}],
  "food_items": [{"product_name":"", "amount_krw": null, "notes": ""}],
  "food_count": 0,
  "model": "..."
}
```

**Step 3: Keep warm-up and singleton caching**

At startup:
- initialize receipt service once
- warm up PaddleOCR once

**Step 4: Keep Qwen optional**

Default path must still work with no Qwen runtime configured.

### Task 3: Add verification tests in the AI repository

**Files:**
- Create: `tests/test_ocr_api_contract.py`
- Create: `tests/test_ocr_health.py`
- Create: `tests/test_ocr_service_adapter.py`
- Modify: `requirements.txt`

**Step 1: Port the essential prototype tests**

Minimum coverage:
- parse result adapter keeps required keys
- health endpoint reports preprocess and bbox contract
- Qwen fallback does not break response shape
- service returns review flags and totals when present

**Step 2: Add pytest dependency if missing**

Update:
- `requirements.txt`

**Step 3: Run the targeted tests**

```powershell
pytest tests/test_ocr_api_contract.py tests/test_ocr_health.py tests/test_ocr_service_adapter.py -q
```

Expected: all pass

### Task 4: Run repository-level smoke verification with real images

**Files:**
- Reuse existing runtime files only

**Step 1: Run OCR directly on known sample crops**

```powershell
python receipt_ocr.py "C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비\img2.items-crop.jpg"
python receipt_ocr.py "C:\Users\USER-PC\Desktop\jp\.worktrees\codex-hwpx-proposal-patch\output\제비\img3.items-crop.jpg"
```

**Step 2: Run endpoint-level smoke**

Use ASGI transport against:
- `/api/ocr/receipt`

Validate:
- status code `200`
- required response keys exist
- warm request is materially faster than cold request

### Task 5: Review and finalize

**Files:**
- Modify only files already touched during implementation

**Step 1: Run static verification**

```powershell
python -m py_compile main.py receipt_ocr.py qwen_receipt_assistant.py
python -m py_compile ocr_qwen\app.py ocr_qwen\services.py ocr_qwen\receipts.py ocr_qwen\qwen.py
```

**Step 2: Review for accidental contract drift**

Check:
- no endpoint path changes
- no removed legacy keys
- Qwen still optional
- generated ingredient assets resolve from the ported package

**Step 3: Update docs**

Document:
- where OCR now lives
- which files are wrappers
- how to enable Qwen
