from __future__ import annotations

import asyncio

import httpx

import main
from ocr_qwen.receipt_rules import ReceiptRules


def test_match_product_to_ingredient_uses_receipt_rule_mapping() -> None:
    result = main._match_product_to_ingredient("호가든캔330ml")

    assert result is not None
    assert result["ingredientName"] == "맥주"
    assert result["mapping_source"] == "receipt_rule_product_mapping"


def test_match_product_to_ingredient_applies_alias_before_rule_mapping() -> None:
    result = main._match_product_to_ingredient("어쉬밀크클릿 [")

    assert result is not None
    assert result["ingredientName"] == "초콜릿"
    assert result["mapping_source"] == "receipt_rule_product_mapping"


def test_ingredient_match_endpoint_is_not_public_contract() -> None:
    async def _request() -> httpx.Response:
        transport = httpx.ASGITransport(app=main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.post(
                "/ai/ingredient/match",
                json={"product_names": ["호가든캔330ml", "어쉬밀크클릿 ["]},
            )

    response = asyncio.run(_request())

    assert response.status_code == 404


def test_match_product_to_ingredient_uses_new_brand_product_mappings() -> None:
    assert main._match_product_to_ingredient("농심 신라면 소컵 4,500")["ingredientName"] == "라면"
    assert main._match_product_to_ingredient("농심 너구리 컵 3,750")["ingredientName"] == "라면"
    assert main._match_product_to_ingredient("오뚜기 옛날참기름 4,480")["ingredientName"] == "참기름"
    assert main._match_product_to_ingredient("Koukakis 그릭요거트")["ingredientName"] == "요거트"
    assert main._match_product_to_ingredient("* 완숙토마토 4kg/박스")["ingredientName"] == "토마토"
    assert main._match_product_to_ingredient("초이스엘 생와사비 2,350")["ingredientName"] == "와사비"
    assert main._match_product_to_ingredient("청정원 순창 찰고추장12,780")["ingredientName"] == "고추장"
    assert main._match_product_to_ingredient("청정원 순창 초고추장 2,980")["ingredientName"] == "고추장"
    assert main._match_product_to_ingredient("갈바니'리코타치느4")["ingredientName"] == "리코타 치즈"
    assert main._match_product_to_ingredient("이클립스 페퍼민트향 34g")["ingredientName"] == "민트"
    assert main._match_product_to_ingredient("쿠크다스커피144G")["ingredientName"] == "커피"
    assert main._match_product_to_ingredient("유기농 바나나콘")["ingredientName"] == "바나나"
    assert main._match_product_to_ingredient("해태구문감자4")["ingredientName"] == "감자"
    assert main._match_product_to_ingredient("양념닭주물럭2.2kg")["ingredientName"] == "닭고기"
    assert main._match_product_to_ingredient("청정원 서해안 까나리")["ingredientName"] == "까나리액젓"
    assert main._match_product_to_ingredient("하인즈 유기농케찹 90")["ingredientName"] == "케찹"
    assert main._match_product_to_ingredient("멜오에이지 파마산분")["ingredientName"] == "파마산치즈"
    assert main._match_product_to_ingredient("속이편한 누룽지(5입)")["ingredientName"] == "누룽지"
    assert main._match_product_to_ingredient("*국내산 양상추 2입")["ingredientName"] == "양상추"
    assert main._match_product_to_ingredient("*완숙토마토 4kg/박스")["ingredientName"] == "토마토"
    assert main._match_product_to_ingredient("갈바니 리코타 치즈4")["ingredientName"] == "리코타 치즈"
    assert main._match_product_to_ingredient("블렌드 슈레드 치즈1kg")["ingredientName"] == "치즈"


def test_match_product_to_ingredient_does_not_match_single_char_substring_false_positive() -> None:
    assert main._match_product_to_ingredient("초코파이") is None


def test_receipt_rules_mark_discount_and_packaging_noise_as_non_items() -> None:
    rules = ReceiptRules.load_default()

    assert rules.matches_non_item("가공에누리 -2,500")
    assert rules.matches_non_item("1 채소S-POINT -1,500")
    assert rules.matches_non_item("*종량10L")
    assert rules.matches_non_item("비보험조제: 20,010원")
    assert rules.matches_non_item("OnlyPrice 삼중스편지 수세미")
    assert rules.matches_non_item("구글홈미니")
    assert rules.matches_non_item("샤오미이라이트")
    assert rules.matches_non_item("시스테마스텐다드칫속")
