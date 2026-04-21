from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
import math
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


DEFAULT_DATASET_NAME = "receipt-synthetic-v1"
DEFAULT_CANVAS_SIZE = (900, 1600)
DEFAULT_MARGIN_X = 56
DEFAULT_MARGIN_Y = 48
DEFAULT_ROW_GAP = 18
VALID_LAYOUT_TYPES = {"convenience_pos", "mart_column", "barcode_detail", "compact_single_line", "mixed_noise"}
VALID_NOISE_KEYS = {"blur", "contrast", "skew", "crop", "shadow"}
DEFAULT_NOISE_PROFILE = {
    "blur": "none",
    "contrast": "normal",
    "skew": "none",
    "crop": "none",
    "shadow": "none",
}
DEFAULT_LAYOUT_WEIGHTS = {
    "convenience_pos": 0.30,
    "mart_column": 0.30,
    "barcode_detail": 0.20,
    "compact_single_line": 0.10,
    "mixed_noise": 0.10,
}
ITEM_POOL: list[dict[str, Any]] = [
    {"raw_name": "허쉬쿠키앤크림", "normalized_name": "허쉬쿠키앤크림", "unit": "개", "unit_price": 1600.0},
    {"raw_name": "허쉬쿠키앤초코", "normalized_name": "허쉬쿠키앤초코", "unit": "개", "unit_price": 1600.0},
    {"raw_name": "호가든캔330ml", "normalized_name": "호가든캔330ml", "unit": "캔", "unit_price": 3500.0},
    {"raw_name": "아몬드초코볼", "normalized_name": "아몬드초코볼", "unit": "개", "unit_price": 2000.0},
    {"raw_name": "양파", "normalized_name": "양파", "unit": "개", "unit_price": 990.0},
    {"raw_name": "대파", "normalized_name": "대파", "unit": "단", "unit_price": 2480.0},
    {"raw_name": "계란 10구", "normalized_name": "계란 10구", "unit": "팩", "unit_price": 4590.0},
    {"raw_name": "라라스윗 바닐라파인트474", "normalized_name": "라라스윗 바닐라파인트474", "unit": "개", "unit_price": 6900.0},
    {"raw_name": "라라스윗 초코파인트474ml", "normalized_name": "라라스윗 초코파인트474ml", "unit": "개", "unit_price": 6900.0},
    {"raw_name": "속이편한 누룽지", "normalized_name": "속이편한 누룽지", "unit": "봉", "unit_price": 5600.0},
    {"raw_name": "롯데 앤디카페조릿 다크", "normalized_name": "롯데 앤디카페조릿 다크", "unit": "개", "unit_price": 4800.0},
    {"raw_name": "청양고추", "normalized_name": "청양고추", "unit": "봉", "unit_price": 1980.0},
    {"raw_name": "사과", "normalized_name": "사과", "unit": "봉", "unit_price": 5980.0},
    {"raw_name": "우유 1L", "normalized_name": "우유", "unit": "팩", "unit_price": 2980.0},
    {"raw_name": "두부", "normalized_name": "두부", "unit": "모", "unit_price": 1980.0},
    {"raw_name": "햇반200g", "normalized_name": "햇반", "unit": "개", "unit_price": 1980.0},
    {"raw_name": "맛밤42G*10", "normalized_name": "맛밤42G*10", "unit": "봉", "unit_price": 4990.0},
    {"raw_name": "오예스336g", "normalized_name": "오예스336g", "unit": "박스", "unit_price": 4980.0},
    {"raw_name": "닭주물럭2.2kg", "normalized_name": "닭주물럭", "unit": "팩", "unit_price": 14900.0},
    {"raw_name": "토마토", "normalized_name": "토마토", "unit": "팩", "unit_price": 3980.0},
]
VENDOR_BY_LAYOUT = {
    "convenience_pos": ("GS25", "CU", "세븐일레븐"),
    "mart_column": ("이마트", "홈플러스", "롯데마트"),
    "barcode_detail": ("7-ELEVEN", "GS25"),
    "compact_single_line": ("GS25", "CU"),
    "mixed_noise": ("이마트", "홈플러스", "GS25"),
}
NOISE_VARIANTS = (
    {"blur": "none", "contrast": "normal", "skew": "none", "crop": "none", "shadow": "none"},
    {"blur": "low", "contrast": "normal", "skew": "none", "crop": "none", "shadow": "none"},
    {"blur": "none", "contrast": "low", "skew": "none", "crop": "none", "shadow": "none"},
    {"blur": "none", "contrast": "normal", "skew": "small", "crop": "none", "shadow": "none"},
    {"blur": "none", "contrast": "normal", "skew": "none", "crop": "top_small", "shadow": "none"},
    {"blur": "none", "contrast": "normal", "skew": "none", "crop": "bottom_small", "shadow": "low"},
)


@dataclass(frozen=True)
class SyntheticReceiptSpec:
    file_stem: str
    vendor_name: str
    purchased_at: str
    layout_type: str
    items: list[dict[str, Any]]
    totals: dict[str, float] = field(default_factory=dict)
    noise_profile: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_NOISE_PROFILE))
    variant: str = "default"
    currency: str = "KRW"
    width: int = DEFAULT_CANVAS_SIZE[0]
    min_height: int = DEFAULT_CANVAS_SIZE[1]

    def __post_init__(self) -> None:
        if self.layout_type not in VALID_LAYOUT_TYPES:
            raise ValueError(f"Unsupported layout_type: {self.layout_type}")
        if not self.file_stem.strip():
            raise ValueError("file_stem is required")
        if not self.vendor_name.strip():
            raise ValueError("vendor_name is required")
        if not self.purchased_at.strip():
            raise ValueError("purchased_at is required")
        if not self.items:
            raise ValueError("items must not be empty")
        merged_noise = dict(DEFAULT_NOISE_PROFILE)
        merged_noise.update({key: str(value) for key, value in self.noise_profile.items() if key in VALID_NOISE_KEYS})
        object.__setattr__(self, "noise_profile", merged_noise)


def build_synthetic_dataset_plan(target_count: int) -> dict[str, int]:
    if target_count <= 0:
        raise ValueError("target_count must be positive")

    base_counts: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    allocated = 0
    for layout_type, weight in DEFAULT_LAYOUT_WEIGHTS.items():
        raw = target_count * weight
        count = int(math.floor(raw))
        base_counts[layout_type] = count
        allocated += count
        remainders.append((raw - count, layout_type))

    remaining = target_count - allocated
    for _, layout_type in sorted(remainders, key=lambda item: (-item[0], item[1]))[:remaining]:
        base_counts[layout_type] += 1

    return dict(sorted(base_counts.items()))


def build_synthetic_sample_specs(target_count: int = 15) -> list[SyntheticReceiptSpec]:
    plan = build_synthetic_dataset_plan(target_count)
    specs: list[SyntheticReceiptSpec] = []
    for layout_type, count in plan.items():
        for index in range(count):
            global_index = len(specs)
            specs.append(_build_layout_spec(layout_type=layout_type, index=index, global_index=global_index))
    return specs


def render_synthetic_receipt(
    *,
    spec: SyntheticReceiptSpec,
    output_dir: Path | str,
    dataset_name: str = DEFAULT_DATASET_NAME,
    generated_at: str | None = None,
) -> tuple[Path, dict[str, Any]]:
    root = Path(output_dir)
    images_dir = root / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    image = _render_receipt_image(spec)
    image = _apply_noise_profile(image, spec.noise_profile)

    image_path = images_dir / f"{spec.file_stem}.png"
    image.save(image_path, format="PNG")

    annotation = build_synthetic_annotation(
        spec=spec,
        image_path=image_path,
        dataset_name=dataset_name,
        generated_at=generated_at,
    )
    return image_path, annotation


def build_synthetic_annotation(
    *,
    spec: SyntheticReceiptSpec,
    image_path: Path,
    dataset_name: str = DEFAULT_DATASET_NAME,
    generated_at: str | None = None,
) -> dict[str, Any]:
    timestamp = generated_at or _utc_now_isoformat()
    return {
        "dataset_name": dataset_name,
        "label_source": "synthetic-template-v1",
        "generated_at": timestamp,
        "image": {
            "file_name": image_path.name,
            "source_path": str(image_path),
        },
        "metadata": {
            "layout_type": spec.layout_type,
            "variant": spec.variant,
            "noise_profile": dict(spec.noise_profile),
            "source_type": "synthetic",
            "version": "v1",
        },
        "expected": {
            "vendor_name": spec.vendor_name,
            "purchased_at": spec.purchased_at,
            "items": [dict(item) for item in spec.items],
            "totals": dict(spec.totals),
            "review_required": False,
            "review_reasons": [],
            "diagnostics": {
                "synthetic": True,
                "layout_type": spec.layout_type,
            },
        },
    }


def build_synthetic_manifest(
    *,
    dataset_name: str,
    output_dir: Path | str,
    annotations: list[dict[str, Any]],
) -> dict[str, Any]:
    layout_counts = Counter(
        str(annotation.get("metadata", {}).get("layout_type"))
        for annotation in annotations
        if annotation.get("metadata", {}).get("layout_type")
    )
    return {
        "dataset_name": dataset_name,
        "output_dir": str(Path(output_dir)),
        "image_count": len(annotations),
        "total_item_count": sum(len(annotation.get("expected", {}).get("items", [])) for annotation in annotations),
        "layout_counts": dict(sorted(layout_counts.items())),
        "images": [
            {
                "file_name": annotation.get("image", {}).get("file_name"),
                "source_path": annotation.get("image", {}).get("source_path"),
            }
            for annotation in annotations
        ],
    }


def _render_receipt_image(spec: SyntheticReceiptSpec) -> Image.Image:
    width = max(spec.width, 700)
    provisional_height = max(spec.min_height, 1200)
    image = Image.new("RGB", (width, provisional_height), color=(238, 234, 225))
    draw = ImageDraw.Draw(image)

    fonts = _FontBundle.load()
    x = DEFAULT_MARGIN_X
    y = DEFAULT_MARGIN_Y

    title = spec.vendor_name
    y = _draw_centered(draw, title, fonts.title, y, width)
    y += 16
    y = _draw_text(draw, f"[주문] {spec.purchased_at} 18:59", x, y, fonts.body)
    y += 8
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12

    if spec.layout_type == "convenience_pos":
        y = _draw_convenience_layout(draw, spec, x, y, width, fonts)
    elif spec.layout_type == "mart_column":
        y = _draw_mart_layout(draw, spec, x, y, width, fonts)
    elif spec.layout_type == "barcode_detail":
        y = _draw_barcode_layout(draw, spec, x, y, width, fonts)
    elif spec.layout_type == "compact_single_line":
        y = _draw_compact_single_line_layout(draw, spec, x, y, width, fonts)
    elif spec.layout_type == "mixed_noise":
        y = _draw_mixed_noise_layout(draw, spec, x, y, width, fonts)

    y += 10
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 18
    y = _draw_totals(draw, spec, x, y, width, fonts)
    y += 20
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 16
    y = _draw_text(draw, "카드결제", x, y, fonts.body)
    y = _draw_text(draw, "승인번호 123456", width - 280, y - 40, fonts.body_small)

    final_height = min(max(int(y + 90), 1200), provisional_height)
    return image.crop((0, 0, width, final_height))


def _draw_convenience_layout(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    variant = spec.variant
    if variant == "header_noise":
        y = _draw_text(draw, "금루금", x, y, fonts.body_small)
        y -= 6
        y = _draw_text(draw, "은", x + 24, y, fonts.body_small)
        y -= 8
    y = _draw_text(draw, "상품명", x, y, fonts.header)
    y = _draw_text(draw, "수량", width - 240, y - 44, fonts.header)
    y = _draw_text(draw, "금액", width - 110, y, fonts.header)
    y += 10
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12

    for index, item in enumerate(spec.items):
        amount = item.get("amount")
        amount_text = "증정품" if amount is None else _format_money(float(amount))
        quantity_text = _format_quantity(item)

        if variant == "split_rows" and index % 2 == 0:
            y = _draw_text(draw, f"{item['raw_name']} {quantity_text}", x, y, fonts.body)
            y -= 6
            y = _draw_text(draw, amount_text, x + 24, y, fonts.body)
            y += 2
            continue

        if variant == "narrow_columns":
            row_text = f"{item['raw_name']}{quantity_text}{amount_text}"
            y = _draw_text(draw, row_text, x, y, fonts.body)
            y += 2
            continue

        y = _draw_text(draw, str(item["raw_name"]), x, y, fonts.body)
        y = _draw_text(draw, quantity_text, width - 230, y - 38, fonts.body)
        y = _draw_text(draw, amount_text, width - 170, y, fonts.body)
        y += 8
    return y


def _draw_mart_layout(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    headers = [("상품명", x), ("단가", width - 360), ("수량", width - 220), ("금액", width - 100)]
    for label, position_x in headers:
        y = _draw_text(draw, label, position_x, y, fonts.header)
    y += 8
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12
    for item in spec.items:
        y = _draw_text(draw, str(item["raw_name"]), x, y, fonts.body)
        unit_price = float(item.get("unit_price") or item.get("amount") or 0.0)
        y = _draw_text(draw, _format_money(unit_price), width - 360, y - 38, fonts.body)
        y = _draw_text(draw, _format_quantity(item), width - 220, y, fonts.body)
        y = _draw_text(draw, _format_money(float(item.get("amount") or 0.0)), width - 130, y, fonts.body)
        y += 8
    return y


def _draw_barcode_layout(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    y = _draw_text(draw, "상품명", x, y, fonts.header)
    y = _draw_text(draw, "수량", width - 220, y - 44, fonts.header)
    y = _draw_text(draw, "금액", width - 100, y, fonts.header)
    y += 8
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12
    for item in spec.items:
        barcode = str(item.get("barcode") or "8800000000000")
        unit_price = float(item.get("unit_price") or item.get("amount") or 0.0)
        amount = float(item.get("amount") or 0.0)
        y = _draw_text(draw, str(item["raw_name"]), x, y, fonts.body)
        y += 4
        detail = f"{barcode}  {_format_money(unit_price)}  {_format_quantity(item)}  {_format_money(amount)}"
        y = _draw_text(draw, detail, x + 16, y, fonts.body_small)
        y += 10
    return y


def _draw_compact_single_line_layout(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    y = _draw_text(draw, "상품명 수량 금액", x, y, fonts.header)
    y += 8
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12
    for item in spec.items:
        amount = item.get("amount")
        amount_text = "증정품" if amount is None else _format_money(float(amount))
        row_text = f"{item['raw_name']}  {_format_quantity(item)}  {amount_text}"
        y = _draw_text(draw, row_text, x, y, fonts.body)
        y += 4
    return y


def _draw_mixed_noise_layout(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    y = _draw_text(draw, "상품명 단가 수량 금액", x, y, fonts.header)
    y += 8
    y = _draw_rule(draw, x, y, width - DEFAULT_MARGIN_X)
    y += 12
    for index, item in enumerate(spec.items):
        if index == 1:
            y = _draw_text(draw, "[행사쿠폰] -1,500", x, y, fonts.body_small)
            y += 2
        if index == 2:
            y = _draw_text(draw, "재사용봉투 1 500", x, y, fonts.body_small)
            y += 2
        unit_price = float(item.get("unit_price") or item.get("amount") or 0.0)
        amount = item.get("amount")
        amount_text = "증정품" if amount is None else _format_money(float(amount))
        row_text = f"{item['raw_name']}  {_format_money(unit_price)}  {_format_quantity(item)}  {amount_text}"
        y = _draw_text(draw, row_text, x, y, fonts.body)
        y += 4
        if index == 0:
            barcode = str(item.get("barcode") or "8800000000000")
            y = _draw_text(draw, f"{barcode}  {_format_money(unit_price)}  {_format_quantity(item)}", x + 10, y, fonts.body_small)
            y += 2
    y = _draw_text(draw, "신용카드 전표(고객용)", x, y, fonts.body_small)
    return y


def _draw_totals(
    draw: ImageDraw.ImageDraw,
    spec: SyntheticReceiptSpec,
    x: int,
    y: int,
    width: int,
    fonts: "_FontBundle",
) -> int:
    total_rows = [
        ("과세물품", spec.totals.get("subtotal")),
        ("부가세", spec.totals.get("tax")),
        ("합계", spec.totals.get("total")),
        ("결제금액", spec.totals.get("payment_amount")),
    ]
    for label, value in total_rows:
        if value is None:
            continue
        y = _draw_text(draw, label, x, y, fonts.body)
        y = _draw_text(draw, _format_money(float(value)), width - 180, y - 38, fonts.body)
        y += 8
    return y


def _apply_noise_profile(image: Image.Image, noise_profile: dict[str, str]) -> Image.Image:
    result = image
    blur = noise_profile.get("blur", "none")
    if blur == "low":
        result = result.filter(ImageFilter.GaussianBlur(radius=0.6))
    elif blur == "medium":
        result = result.filter(ImageFilter.GaussianBlur(radius=1.2))

    contrast = noise_profile.get("contrast", "normal")
    if contrast == "low":
        result = ImageEnhance.Contrast(result).enhance(0.82)

    shadow = noise_profile.get("shadow", "none")
    if shadow == "low":
        overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)
        overlay_draw.rectangle((0, 0, int(result.width * 0.22), result.height), fill=(0, 0, 0, 24))
        result = Image.alpha_composite(result.convert("RGBA"), overlay).convert("RGB")

    skew = noise_profile.get("skew", "none")
    if skew == "small":
        result = result.rotate(1.4, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(238, 234, 225))
    elif skew == "medium":
        result = result.rotate(2.8, resample=Image.Resampling.BICUBIC, expand=True, fillcolor=(238, 234, 225))

    crop = noise_profile.get("crop", "none")
    if crop == "top_small":
        result = result.crop((0, 32, result.width, result.height))
    elif crop == "bottom_small":
        result = result.crop((0, 0, result.width, max(result.height - 40, 100)))

    return result


def _draw_centered(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, y: int, width: int) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    x = max((width - text_width) // 2, DEFAULT_MARGIN_X)
    draw.text((x, y), text, fill="black", font=font)
    return y + (bbox[3] - bbox[1])


def _draw_text(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font: ImageFont.ImageFont) -> int:
    draw.text((x, y), text, fill="black", font=font)
    bbox = draw.textbbox((x, y), text, font=font)
    return y + (bbox[3] - bbox[1]) + DEFAULT_ROW_GAP


def _draw_rule(draw: ImageDraw.ImageDraw, x1: int, y: int, x2: int) -> int:
    draw.line((x1, y, x2, y), fill="black", width=2)
    return y


def _format_money(value: float) -> str:
    return f"{int(round(value)):,}"


def _format_quantity(item: dict[str, Any]) -> str:
    quantity = float(item.get("quantity") or 0.0)
    if quantity.is_integer():
        return str(int(quantity))
    return f"{quantity:g}"


def _item(
    raw_name: str,
    quantity: float,
    unit: str,
    amount: float | None,
    *,
    normalized_name: str | None = None,
    unit_price: float | None = None,
    barcode: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "raw_name": raw_name,
        "normalized_name": normalized_name or raw_name,
        "quantity": quantity,
        "unit": unit,
        "amount": amount,
    }
    if unit_price is not None:
        result["unit_price"] = unit_price
    if barcode is not None:
        result["barcode"] = barcode
    return result


@dataclass(frozen=True)
class _FontBundle:
    title: ImageFont.ImageFont
    header: ImageFont.ImageFont
    body: ImageFont.ImageFont
    body_small: ImageFont.ImageFont

    @classmethod
    def load(cls) -> "_FontBundle":
        title = _load_font(72, bold=True)
        header = _load_font(34, bold=True)
        body = _load_font(30, bold=False)
        body_small = _load_font(24, bold=False)
        return cls(title=title, header=header, body=body, body_small=body_small)


def _load_font(size: int, *, bold: bool) -> ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates.extend(
            [
                Path(r"C:\Windows\Fonts\malgunbd.ttf"),
                Path(r"C:\Windows\Fonts\gulim.ttc"),
            ]
        )
    else:
        candidates.extend(
            [
                Path(r"C:\Windows\Fonts\malgun.ttf"),
                Path(r"C:\Windows\Fonts\gulim.ttc"),
            ]
        )
    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    return ImageFont.load_default()


def _utc_now_isoformat() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _build_layout_spec(*, layout_type: str, index: int, global_index: int) -> SyntheticReceiptSpec:
    vendor_name = _cycle_pick(VENDOR_BY_LAYOUT[layout_type], index)
    purchased_at = _build_date(global_index)
    noise_profile = dict(NOISE_VARIANTS[global_index % len(NOISE_VARIANTS)])
    variant = _build_layout_variant(layout_type=layout_type, index=index, global_index=global_index)
    if layout_type == "convenience_pos":
        if variant == "header_noise":
            noise_profile["contrast"] = "low"
        elif variant == "narrow_columns":
            noise_profile["blur"] = "low"
        elif variant == "split_rows":
            noise_profile["shadow"] = "low"
    items = _build_items_for_layout(layout_type=layout_type, index=index, global_index=global_index)
    totals = _build_totals(items)
    file_stem = f"{layout_type}-{global_index + 1:04d}"
    return SyntheticReceiptSpec(
        file_stem=file_stem,
        vendor_name=vendor_name,
        purchased_at=purchased_at,
        layout_type=layout_type,
        items=items,
        totals=totals,
        noise_profile=noise_profile,
        variant=variant,
    )


def _build_items_for_layout(*, layout_type: str, index: int, global_index: int) -> list[dict[str, Any]]:
    item_count = 3 + (global_index % 3)
    start = (global_index * 2) % len(ITEM_POOL)
    source_items = [ITEM_POOL[(start + offset) % len(ITEM_POOL)] for offset in range(item_count)]
    built: list[dict[str, Any]] = []
    for offset, base_item in enumerate(source_items):
        quantity = float(((global_index + offset) % 3) + 1)
        if base_item["unit"] in {"팩", "박스", "모", "단"}:
            quantity = 1.0
        unit_price = float(base_item["unit_price"])
        amount = round(unit_price * quantity, 2)
        built_item = _item(
            str(base_item["raw_name"]),
            quantity,
            str(base_item["unit"]),
            amount,
            normalized_name=str(base_item["normalized_name"]),
            unit_price=unit_price,
            barcode=f"880{global_index:04d}{offset:03d}123",
        )
        built.append(built_item)

    if layout_type in {"convenience_pos", "mixed_noise"} and built:
        gift_index = (index + global_index) % len(built)
        built[gift_index]["amount"] = None
        built[gift_index]["quantity"] = 1.0
        built[gift_index]["unit"] = "개"

    return built


def _build_layout_variant(*, layout_type: str, index: int, global_index: int) -> str:
    if layout_type != "convenience_pos":
        return "default"
    variants = ("default", "header_noise", "narrow_columns", "split_rows")
    return variants[index % len(variants)]


def _build_totals(items: list[dict[str, Any]]) -> dict[str, float]:
    subtotal = sum(float(item["amount"]) for item in items if item.get("amount") is not None)
    tax = float(int(round(subtotal * 0.1)))
    total = subtotal + tax
    return {
        "subtotal": float(subtotal),
        "tax": float(tax),
        "total": float(total),
        "payment_amount": float(total),
    }


def _build_date(global_index: int) -> str:
    year = 2023 + ((global_index // 120) % 4)
    month = (global_index % 12) + 1
    day = (global_index % 27) + 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def _cycle_pick(values: tuple[str, ...], index: int) -> str:
    return values[index % len(values)]
