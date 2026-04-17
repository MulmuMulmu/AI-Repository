from __future__ import annotations

import importlib.util
import os
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .qwen import build_default_qwen_provider, local_qwen_enabled, qwen_runtime_available
from .services import ExpiryService, ReceiptParseService, RecipeService


class ReceiptParseRequest(BaseModel):
    receipt_image_url: Optional[str] = None
    s3_key: Optional[str] = None


class ReceiptItemInput(BaseModel):
    normalized_name: str
    category: str
    storage_type: str
    purchased_at: str


class ExpiryEvaluateRequest(BaseModel):
    items: List[ReceiptItemInput]


class RecommendationItemInput(BaseModel):
    normalized_name: str
    risk_level: str = "safe"
    is_expired: bool = False


class RecommendationRequest(BaseModel):
    items: List[RecommendationItemInput]


def create_app(
    receipt_service: Optional[object] = None,
    expiry_service: Optional[object] = None,
    recipe_service: Optional[object] = None,
) -> FastAPI:
    qwen_provider = build_default_qwen_provider()
    app = FastAPI(title="mulmumulmu-ai", version="1.0.0")
    app.state.receipt_service = receipt_service or ReceiptParseService(qwen_provider=qwen_provider)
    app.state.expiry_service = expiry_service or ExpiryService()
    app.state.recipe_service = recipe_service or RecipeService(qwen_provider=qwen_provider)

    @app.on_event("startup")
    def warm_up_receipt_backend() -> None:
        if os.environ.get("PREWARM_PADDLEOCR_ON_STARTUP", "1") != "1":
            return
        backend = getattr(app.state.receipt_service, "ocr_backend", None)
        warm_up = getattr(backend, "warm_up", None)
        if callable(warm_up):
            warm_up()

    @app.post("/ai/v1/receipts/parse")
    def parse_receipt(request: ReceiptParseRequest) -> dict:
        if not request.receipt_image_url and not request.s3_key:
            raise HTTPException(status_code=422, detail="receipt_image_url or s3_key is required.")
        try:
            return app.state.receipt_service.parse(request.model_dump(exclude_none=True))
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ModuleNotFoundError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/ai/v1/expiry/evaluate")
    def evaluate_expiry(request: ExpiryEvaluateRequest) -> dict:
        try:
            return app.state.expiry_service.evaluate(request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.post("/ai/v1/recommendations/recipes")
    def recommend_recipes(request: RecommendationRequest) -> dict:
        try:
            return app.state.recipe_service.recommend(request.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @app.get("/ai/v1/health")
    def health() -> dict:
        return {
            "status": "ok",
            "dependencies": {
                "paddleocr_installed": importlib.util.find_spec("paddleocr") is not None,
                "preprocess_available": importlib.util.find_spec("PIL") is not None,
                "bbox_contract": True,
                "qwen_runtime_available": qwen_runtime_available(),
            },
            "config": {
                "s3_public_base_url_configured": bool(os.environ.get("S3_PUBLIC_BASE_URL")),
                "local_qwen_enabled": local_qwen_enabled(),
            },
        }

    return app


app = create_app()
