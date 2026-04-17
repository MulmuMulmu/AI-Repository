"""
합성 영수증 데이터 생성기 + OCR 평가 프레임워크

기능:
  1) PIL로 실제 영수증과 유사한 이미지를 합성 (ground truth 포함)
  2) 노이즈, 블러, 회전, 원근변환, 조명 불균일 등 현실적 왜곡 적용
  3) PaddleOCR 결과와 ground truth 비교 → 정확도 측정
  4) 전처리 파라미터 튜닝에 활용

사용법:
  python scripts/generate_synthetic_receipts.py --count 50
  python scripts/generate_synthetic_receipts.py --count 20 --evaluate
"""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

FONT_SEARCH_PATHS = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "C:/Windows/Fonts/malgun.ttf",
]

STORE_NAMES = [
    "이마트", "홈플러스", "롯데마트", "GS25", "CU", "세븐일레븐",
    "하나로마트", "농협하나로", "나루식자재마트", "메가마트",
    "노브랜드", "코스트코", "트레이더스", "롯데슈퍼",
]

PRODUCT_CATALOG = [
    ("국산 삼겹살 600g", 12900, "정육/계란"),
    ("한돈 목살 500g", 9800, "정육/계란"),
    ("신선 닭가슴살 1kg", 7900, "정육/계란"),
    ("계란 30구", 6980, "정육/계란"),
    ("한우 앞다리 300g", 15800, "정육/계란"),
    ("서울우유 1L", 2800, "유제품"),
    ("매일 저지방우유 900ml", 2500, "유제품"),
    ("빙그레 바나나맛우유 240ml", 1500, "유제품"),
    ("덴마크 플레인요거트", 3200, "유제품"),
    ("서울 체다치즈 200g", 4500, "유제품"),
    ("양파 1.5kg", 3980, "채소/과일"),
    ("깻잎 1봉", 1500, "채소/과일"),
    ("대파 1단", 2500, "채소/과일"),
    ("감자 1kg", 3500, "채소/과일"),
    ("브로콜리 1송이", 1980, "채소/과일"),
    ("바나나 1송이", 3980, "채소/과일"),
    ("딸기 500g", 6980, "채소/과일"),
    ("사과 3개입", 5900, "채소/과일"),
    ("산딸기 500g/박스", 6980, "채소/과일"),
    ("방울토마토 500g", 4980, "채소/과일"),
    ("새우 냉동 500g", 8900, "해산물"),
    ("오징어 1마리", 5500, "해산물"),
    ("고등어 1마리", 3800, "해산물"),
    ("동원 참치캔 150g", 2500, "해산물"),
    ("프레시참치 120g", 1900, "해산물"),
    ("호주곡물오이스터블", 14720, "해산물"),
    ("CJ 햇반 210g", 1680, "쌀/면/빵"),
    ("신라면 5입", 3980, "쌀/면/빵"),
    ("진비빔면 (156gx4)", 2500, "쌀/면/빵"),
    ("오뚜기 콤비네이션", 5980, "쌀/면/빵"),
    ("밀가루 1kg", 1500, "쌀/면/빵"),
    ("고추장 500g", 4500, "소스/조미료/오일"),
    ("청정원 올리브유 500ml", 7300, "소스/조미료/오일"),
    ("맛선생 참치액 560g", 3740, "소스/조미료/오일"),
    ("청정원허브맛솔트", 1980, "소스/조미료/오일"),
    ("농심 올리브짜파게", 3850, "소스/조미료/오일"),
    ("스팸 340g", 3600, "가공식품"),
    ("CJ미니드레싱골라담", 3980, "가공식품"),
    ("비타김밥단무지 35", 1350, "가공식품"),
    ("스팸클래식", 3600, "가공식품"),
    ("하림챔오리지널", 3600, "가공식품"),
    ("노브랜드 굿밀크우", 1680, "기타"),
    ("바리스타 쇼콜라 32", 2250, "기타"),
    ("롯데 수박바젤리 56", 980, "기타"),
    ("커피빈 카페라떼", 1760, "기타"),
    ("칠성사이다 1.5L", 1660, "기타"),
]


@dataclass
class SyntheticReceiptItem:
    product_name: str
    unit_price: int
    quantity: int
    total_price: int
    category: str


@dataclass
class SyntheticReceipt:
    store_name: str
    date: str
    pos_id: str
    items: List[SyntheticReceiptItem]
    total: int
    image_path: str = ""
    ground_truth_path: str = ""


def find_korean_font(size: int = 20) -> ImageFont.FreeTypeFont:
    for path in FONT_SEARCH_PATHS:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def generate_receipt_data(item_count: int = 0) -> SyntheticReceipt:
    store = random.choice(STORE_NAMES)
    year = random.randint(2020, 2026)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    hour = random.randint(8, 22)
    minute = random.randint(0, 59)
    date_str = f"{year}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}"
    pos_id = f"POS:{random.randint(1, 9):03d}-{random.randint(10000, 99999)}"

    if item_count <= 0:
        item_count = random.randint(3, 15)

    selected = random.sample(PRODUCT_CATALOG, min(item_count, len(PRODUCT_CATALOG)))
    items = []
    for name, price, category in selected:
        qty = random.choices([1, 2, 3, 4], weights=[70, 20, 7, 3])[0]
        items.append(SyntheticReceiptItem(
            product_name=name,
            unit_price=price,
            quantity=qty,
            total_price=price * qty,
            category=category,
        ))
    total = sum(it.total_price for it in items)
    return SyntheticReceipt(store_name=store, date=date_str, pos_id=pos_id, items=items, total=total)


def render_receipt_image(
    receipt: SyntheticReceipt,
    *,
    width: int = 580,
    font_size: int = 22,
    line_spacing: int = 6,
) -> Image.Image:
    font = find_korean_font(font_size)
    font_small = find_korean_font(font_size - 4)
    font_header = find_korean_font(font_size + 4)

    margin_x = 30
    content_width = width - margin_x * 2
    y = 30
    lines_to_draw: list[tuple[int, str, ImageFont.FreeTypeFont, str]] = []

    def add_line(text: str, f: ImageFont.FreeTypeFont = font, align: str = "left"):
        nonlocal y
        lines_to_draw.append((y, text, f, align))
        y += font_size + line_spacing

    def add_separator():
        nonlocal y
        lines_to_draw.append((y, "─" * (content_width // (font_size // 2)), font_small, "left"))
        y += font_size // 2 + line_spacing

    add_line(receipt.store_name, font_header, "center")
    y += 4
    add_line(f"[구 매]{receipt.date}", font_small)
    add_line(f"       {receipt.pos_id}", font_small)
    y += 4
    add_separator()
    add_line("  상 품 명          단가   수량     금액", font_small)
    add_separator()

    for idx, item in enumerate(receipt.items, 1):
        name_part = f"{idx:02d} {item.product_name}"
        price_part = f"{item.unit_price:>7,d} {item.quantity:>3d}  {item.total_price:>8,d}"
        if len(name_part) > 20:
            add_line(name_part)
            add_line(f"{'':>20s}{price_part}", font)
        else:
            combined = f"{name_part:<20s}{price_part}"
            add_line(combined)

    add_separator()
    add_line(f"{'합    계':>20s}{receipt.total:>20,d}", font)
    add_line(f"{'결제대상금액':>20s}{receipt.total:>20,d}", font)
    y += 10

    height = y + 40
    img = Image.new("L", (width, height), color=245)
    draw = ImageDraw.Draw(img)

    for (ly, text, f, align) in lines_to_draw:
        try:
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(text) * font_size // 2

        if align == "center":
            x = (width - tw) // 2
        elif align == "right":
            x = width - margin_x - tw
        else:
            x = margin_x
        draw.text((x, ly), text, fill=random.randint(10, 40), font=f)

    return img


def apply_augmentation(
    img: Image.Image,
    difficulty: str = "medium",
) -> Image.Image:
    """현실적인 왜곡을 적용해 합성 영수증을 실사처럼 만든다."""
    import numpy as np

    augmented = img.copy()
    if augmented.mode != "RGB":
        augmented = augmented.convert("RGB")

    w, h = augmented.size

    if difficulty == "easy":
        noise_level, blur_radius, rotation_range = 8, 0.3, 1.0
        brightness_range, contrast_range = (0.95, 1.05), (0.95, 1.05)
    elif difficulty == "hard":
        noise_level, blur_radius, rotation_range = 30, 1.5, 5.0
        brightness_range, contrast_range = (0.6, 1.3), (0.5, 1.4)
    else:
        noise_level, blur_radius, rotation_range = 15, 0.7, 2.5
        brightness_range, contrast_range = (0.8, 1.15), (0.7, 1.2)

    arr = np.array(augmented, dtype=np.float32)
    noise = np.random.normal(0, noise_level, arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype(np.uint8)
    augmented = Image.fromarray(arr)

    if blur_radius > 0:
        augmented = augmented.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    angle = random.uniform(-rotation_range, rotation_range)
    if abs(angle) > 0.2:
        augmented = augmented.rotate(angle, expand=True, fillcolor=(240, 240, 240))

    brightness = random.uniform(*brightness_range)
    augmented = ImageEnhance.Brightness(augmented).enhance(brightness)

    contrast = random.uniform(*contrast_range)
    augmented = ImageEnhance.Contrast(augmented).enhance(contrast)

    if difficulty in ("medium", "hard"):
        gradient = Image.new("L", augmented.size, 0)
        gradient_draw = ImageDraw.Draw(gradient)
        direction = random.choice(["top", "bottom", "left", "right"])
        for i in range(h if direction in ("top", "bottom") else w):
            if direction == "top":
                intensity = int(40 * (1 - i / h))
            elif direction == "bottom":
                intensity = int(40 * (i / h))
            elif direction == "left":
                intensity = int(40 * (1 - i / w))
            else:
                intensity = int(40 * (i / w))
            if direction in ("top", "bottom"):
                gradient_draw.line([(0, i), (w, i)], fill=intensity)
            else:
                gradient_draw.line([(i, 0), (i, h)], fill=intensity)
        gradient_rgb = gradient.convert("RGB")
        from PIL import ImageChops
        augmented = ImageChops.subtract(augmented, gradient_rgb)

    if difficulty == "hard" and random.random() < 0.3:
        augmented = augmented.resize(
            (int(w * 0.6), int(h * 0.6)), Image.LANCZOS
        ).resize((w, h), Image.LANCZOS)

    return augmented


def generate_dataset(
    output_dir: Path,
    count: int = 50,
    difficulty: str = "medium",
) -> list[dict]:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "images").mkdir(exist_ok=True)
    (output_dir / "labels").mkdir(exist_ok=True)

    manifest = []
    for i in range(count):
        receipt = generate_receipt_data()
        clean_img = render_receipt_image(receipt)

        diff = random.choice(["easy", "medium", "hard"]) if difficulty == "mixed" else difficulty
        augmented = apply_augmentation(clean_img, difficulty=diff)

        img_name = f"synth_{i:04d}.png"
        label_name = f"synth_{i:04d}.json"
        augmented.save(output_dir / "images" / img_name)

        ground_truth = {
            "image": img_name,
            "difficulty": diff,
            "store_name": receipt.store_name,
            "date": receipt.date,
            "total": receipt.total,
            "items": [
                {
                    "product_name": it.product_name,
                    "category": it.category,
                    "unit_price": it.unit_price,
                    "quantity": it.quantity,
                    "total_price": it.total_price,
                }
                for it in receipt.items
            ],
        }
        with open(output_dir / "labels" / label_name, "w", encoding="utf-8") as f:
            json.dump(ground_truth, f, ensure_ascii=False, indent=2)

        manifest.append(ground_truth)
        if (i + 1) % 10 == 0:
            print(f"  생성 완료: {i + 1}/{count}")

    with open(output_dir / "manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"\n합성 데이터 {count}건 생성 완료 → {output_dir}")
    return manifest


def evaluate_ocr_on_synthetic(dataset_dir: Path, sample_limit: int = 10) -> dict:
    """합성 데이터에 OCR을 돌려 정확도를 측정한다."""
    from difflib import SequenceMatcher

    manifest_path = dataset_dir / "manifest.json"
    if not manifest_path.exists():
        print("manifest.json이 없습니다. --count로 먼저 생성하세요.")
        return {}

    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    try:
        from ocr_qwen.preprocess import preprocess_receipt
        from paddleocr import PaddleOCR
    except ImportError as e:
        print(f"평가에 필요한 모듈을 찾을 수 없습니다: {e}")
        return {}

    ocr_engine = PaddleOCR(use_angle_cls=True, lang="korean", show_log=False)
    samples = manifest[:sample_limit]

    results = []
    for entry in samples:
        img_path = str(dataset_dir / "images" / entry["image"])
        gt_items = [it["product_name"] for it in entry["items"]]

        raw_result = ocr_engine.ocr(img_path, cls=True)
        ocr_texts = []
        if raw_result and raw_result[0]:
            for line in raw_result[0]:
                if len(line) >= 2:
                    ocr_texts.append(line[1][0])

        ocr_joined = " ".join(ocr_texts).lower()
        matched = 0
        for gt_name in gt_items:
            gt_clean = gt_name.replace(" ", "").lower()
            best = max(
                (SequenceMatcher(None, gt_clean, ocr_t.replace(" ", "").lower()).ratio()
                 for ocr_t in ocr_texts),
                default=0.0,
            )
            if best >= 0.6:
                matched += 1

        precision = matched / len(gt_items) if gt_items else 0
        results.append({
            "image": entry["image"],
            "difficulty": entry["difficulty"],
            "gt_count": len(gt_items),
            "matched": matched,
            "recall": round(precision, 4),
        })
        status = "OK" if precision >= 0.7 else "LOW"
        print(f"  [{status}] {entry['image']} | {entry['difficulty']:>6s} | "
              f"recall={precision:.0%} ({matched}/{len(gt_items)})")

    avg_recall = sum(r["recall"] for r in results) / len(results) if results else 0
    by_difficulty = {}
    for r in results:
        d = r["difficulty"]
        by_difficulty.setdefault(d, []).append(r["recall"])
    difficulty_avg = {d: round(sum(v) / len(v), 4) for d, v in by_difficulty.items()}

    summary = {
        "total_samples": len(results),
        "avg_recall": round(avg_recall, 4),
        "by_difficulty": difficulty_avg,
        "details": results,
    }

    report_path = dataset_dir / "eval_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    print(f"\n=== OCR 평가 결과 ===")
    print(f"  전체 평균 recall: {avg_recall:.1%}")
    for d, v in difficulty_avg.items():
        print(f"  {d}: {v:.1%}")
    print(f"  리포트 저장: {report_path}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="합성 영수증 데이터 생성 및 OCR 평가")
    parser.add_argument("--count", type=int, default=50, help="생성할 합성 영수증 수")
    parser.add_argument("--difficulty", choices=["easy", "medium", "hard", "mixed"],
                        default="mixed", help="왜곡 난이도")
    parser.add_argument("--output", type=str, default=None, help="출력 디렉터리")
    parser.add_argument("--evaluate", action="store_true", help="생성 후 OCR 평가 실행")
    parser.add_argument("--eval-only", action="store_true", help="기존 데이터셋으로 평가만 실행")
    parser.add_argument("--eval-limit", type=int, default=20, help="평가할 샘플 수")
    args = parser.parse_args()

    output_dir = Path(args.output) if args.output else PROJECT_ROOT / "data" / "synthetic_receipts"

    if args.eval_only:
        evaluate_ocr_on_synthetic(output_dir, sample_limit=args.eval_limit)
        return

    generate_dataset(output_dir, count=args.count, difficulty=args.difficulty)

    if args.evaluate:
        evaluate_ocr_on_synthetic(output_dir, sample_limit=args.eval_limit)


if __name__ == "__main__":
    main()
