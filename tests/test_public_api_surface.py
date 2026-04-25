from __future__ import annotations

import asyncio

import httpx

import main


def test_ingredient_match_endpoint_returns_match_result(monkeypatch) -> None:
    def _stub_match(product_name: str) -> dict | None:
        if product_name == "국산콩 두부":
            return {
                "product_name": product_name,
                "ingredientId": "ingredient-1",
                "ingredientName": "두부",
                "category": "가공식품",
                "similarity": 0.92,
            }
        return None

    monkeypatch.setattr(main, "_match_product_to_ingredient", _stub_match)
    monkeypatch.setattr(main, "_find_suggestions", lambda product_name: ["두부", "순두부"])

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/match",
                json={"product_names": ["국산콩 두부", "알수없는상품"]},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    data = payload["data"]
    assert data["matched_count"] == 1
    assert data["unmatched_count"] == 1
    assert data["matched"][0]["ingredientName"] == "두부"
    assert data["matched"][0]["mapping_status"] == "MAPPED"
    assert data["matched"][0]["item_type"] == "INGREDIENT"
    assert data["unmatched"][0]["suggestions"] == ["두부", "순두부"]
    assert data["unmatched"][0]["mapping_status"] == "UNMAPPED"
    assert data["unmatched"][0]["item_type"] == "UNKNOWN"


def test_ingredient_match_endpoint_keeps_non_food_as_excluded(monkeypatch) -> None:
    monkeypatch.setattr(main, "_match_product_to_ingredient", lambda product_name: None)
    monkeypatch.setattr(main, "_find_suggestions", lambda product_name: [])

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/match",
                json={"product_names": ["구글홈미니"]},
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["matched_count"] == 0
    assert payload["unmatched_count"] == 1
    assert payload["unmatched"][0]["mapping_status"] == "EXCLUDED"
    assert payload["unmatched"][0]["item_type"] == "NON_FOOD"


def test_legacy_api_routes_are_not_exposed() -> None:
    async def _request() -> tuple[httpx.Response, httpx.Response, httpx.Response]:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            ocr_response = await client.post("/api/ocr/receipt")
            match_response = await client.post("/api/ingredients/match", json={"product_names": []})
            health_response = await client.get("/api/health")
            return ocr_response, match_response, health_response

    ocr_response, match_response, health_response = asyncio.run(_request())

    assert ocr_response.status_code == 404
    assert match_response.status_code == 404
    assert health_response.status_code == 404


def test_sharing_check_endpoint_returns_filter_result(monkeypatch) -> None:
    class _StubSharingFilter:
        def check(self, item_names):
            assert item_names == ["생고기 모둠", "통조림 참치"]
            return {
                "blocked": [{"item_name": "생고기 모둠", "category": "생고기/생선"}],
                "review_required": [],
                "allowed": [{"item_name": "통조림 참치"}],
                "summary": {"blocked": 1, "review": 0, "allowed": 1},
            }

    monkeypatch.setattr(main, "_get_sharing_filter", lambda: _StubSharingFilter())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/ai/sharing/check", json={"item_names": ["생고기 모둠", "통조림 참치"]})

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["summary"]["blocked"] == 1
    assert payload["allowed"][0]["item_name"] == "통조림 참치"


def test_ingredient_prediction_endpoint_returns_expiry_result(monkeypatch) -> None:
    class _StubIngredientPredictionService:
        def calculate(self, item_name, purchase_date, storage_method, category):
            assert item_name == "양파"
            assert purchase_date == "2026-04-10"
            assert storage_method == "냉장"
            assert category == "채소/과일"
            return {
                "item_name": item_name,
                "purchase_date": purchase_date,
                "storage_method": storage_method,
                "expiry_date": "2026-05-10",
                "d_day": 10,
                "risk_level": "safe",
                "confidence": 0.7,
                "method": "rule-based",
                "reason": "양파 냉장 기준 30일",
            }

    monkeypatch.setattr(main, "_get_ingredient_prediction_service", lambda: _StubIngredientPredictionService())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/prediction",
                json={
                    "item_name": "양파",
                    "purchase_date": "2026-04-10",
                    "storage_method": "냉장",
                    "category": "채소/과일",
                },
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["expiry_date"] == "2026-05-10"
    assert payload["method"] == "rule-based"


def test_ingredient_prediction_endpoint_supports_notion_batch_contract(monkeypatch) -> None:
    calls: list[tuple[str, str, str, str | None]] = []

    class _StubIngredientPredictionService:
        def calculate(self, item_name, purchase_date, storage_method, category):
            calls.append((item_name, purchase_date, storage_method, category))
            return {
                "item_name": item_name,
                "purchase_date": purchase_date,
                "storage_method": storage_method,
                "expiry_date": "2026-06-16",
                "d_day": 10,
                "risk_level": "safe",
                "confidence": 0.7,
                "method": "rule-based",
                "reason": "테스트",
            }

    monkeypatch.setattr(main, "_get_ingredient_prediction_service", lambda: _StubIngredientPredictionService())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(
                "GET",
                "/ai/ingredient/prediction",
                json={
                    "purchaseDate": "2026-04-09",
                    "ingredients": ["우유", "당근", "상추"],
                },
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()
    assert payload == {
        "success": True,
        "result": {
            "purchaseDate": "2026-04-09",
            "ingredients": [
                {"ingredientName": "우유", "expirationDate": "2026-06-16"},
                {"ingredientName": "당근", "expirationDate": "2026-06-16"},
                {"ingredientName": "상추", "expirationDate": "2026-06-16"},
            ],
        },
    }
    assert calls == [
        ("우유", "2026-04-09", "냉장", None),
        ("당근", "2026-04-09", "냉장", None),
        ("상추", "2026-04-09", "냉장", None),
    ]


def test_ingredient_prediction_endpoint_supports_get_query_contract(monkeypatch) -> None:
    class _StubIngredientPredictionService:
        def calculate(self, item_name, purchase_date, storage_method, category):
            return {
                "item_name": item_name,
                "purchase_date": purchase_date,
                "storage_method": storage_method,
                "expiry_date": "2026-06-16",
                "d_day": 10,
                "risk_level": "safe",
                "confidence": 0.7,
                "method": "rule-based",
                "reason": "테스트",
            }

    monkeypatch.setattr(main, "_get_ingredient_prediction_service", lambda: _StubIngredientPredictionService())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get(
                "/ai/ingredient/prediction",
                params=[
                    ("purchaseDate", "2026-04-09"),
                    ("ingredients", "우유"),
                    ("ingredients", "당근"),
                ],
            )

    response = asyncio.run(_request())

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "result": {
            "purchaseDate": "2026-04-09",
            "ingredients": [
                {"ingredientName": "우유", "expirationDate": "2026-06-16"},
                {"ingredientName": "당근", "expirationDate": "2026-06-16"},
            ],
        },
    }


def test_quality_metrics_endpoint_returns_monitor_snapshot(monkeypatch) -> None:
    class _StubQualityMonitor:
        def get_metrics(self, window="1h"):
            assert window == "24h"
            return {
                "window": window,
                "total_requests": 3,
                "error_count": 1,
                "error_rate": 0.3333,
                "avg_response_ms": 123.0,
                "p95_response_ms": 240.0,
                "endpoints": {"/ai/ocr/analyze": {"count": 3, "errors": 1, "avg_ms": 123.0}},
            }

    monkeypatch.setattr(main, "_get_quality_monitor", lambda: _StubQualityMonitor())

    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/ai/quality/metrics?window=24h")

    response = asyncio.run(_request())

    assert response.status_code == 200
    payload = response.json()["data"]
    assert payload["window"] == "24h"
    assert payload["total_requests"] == 3


def test_recommend_endpoint_is_not_exposed_from_ocr_app() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post("/ai/recommend", json={"ingredientIds": ["ingredient-1"]})

    response = asyncio.run(_request())

    assert response.status_code == 404


def test_recipe_detail_endpoint_is_not_exposed_from_ocr_app() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/ai/recipes/recipe-1")

    response = asyncio.run(_request())

    assert response.status_code == 404


def test_ingredient_search_endpoint_is_not_exposed_from_ocr_app() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.get("/ai/ingredients/search?q=양파")

    response = asyncio.run(_request())

    assert response.status_code == 404


def test_connected_routes_log_quality_metrics(monkeypatch) -> None:
    logged: list[tuple[str, int]] = []

    class _StubQualityMonitor:
        def log_request(self, endpoint, elapsed_ms, status_code=200, error=None, trace_id=None):
            logged.append((endpoint, status_code))

        def get_metrics(self, window="1h"):
            return {"window": window, "total_requests": 0, "error_count": 0, "error_rate": 0.0, "avg_response_ms": 0.0, "p95_response_ms": 0.0, "endpoints": {}}

    monkeypatch.setattr(main, "_get_quality_monitor", lambda: _StubQualityMonitor())
    monkeypatch.setattr(main, "_match_product_to_ingredient", lambda product_name: None)
    monkeypatch.setattr(main, "_find_suggestions", lambda product_name: [])

    async def _request() -> list[httpx.Response]:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            responses = []
            responses.append(await client.post("/ai/ingredient/match", json={"product_names": ["알수없는상품"]}))
            responses.append(await client.post("/ai/sharing/check", json={"item_names": ["통조림 참치"]}))
            responses.append(await client.get("/ai/quality/metrics"))
            return responses

    responses = asyncio.run(_request())

    assert all(response.status_code == 200 for response in responses)
    assert [endpoint for endpoint, _ in logged] == [
        "/ai/ingredient/match",
        "/ai/sharing/check",
        "/ai/quality/metrics",
    ]
