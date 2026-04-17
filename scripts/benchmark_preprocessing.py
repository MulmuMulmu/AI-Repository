"""
전처리 개선 전/후 OCR 성능 비교 벤치마크

동일한 깨끗한 합성 영수증에 4가지 단계의 열화를 적용한 뒤,
OLD 전처리(grayscale + autocontrast)와 NEW 전처리(고도화 파이프라인)를
각각 거친 OCR 결과를 ground truth와 비교한다.

열화 단계:
  clean  - 원본 그대로
  mild   - 약한 노이즈 + 밝기 변동
  medium - 노이즈 + 블러 + 회전 + 조명 그라데이션
  severe - 강한 노이즈 + 블러 + 저해상도 + 조명 불균일 + 회전

사용법:
  python scripts/benchmark_preprocessing.py
  python scripts/benchmark_preprocessing.py --samples 15
"""

from __future__ import annotations

import json
import os
import random
import sys
import tempfile
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageChops

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")


# ── 합성 영수증 생성 ─────────────────────────────────────────────
FONT_SEARCH_PATHS = [
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
]

PRODUCTS = [
    "국산 삼겹살 600g", "한돈 목살 500g", "계란 30구", "한우 앞다리 300g",
    "서울우유 1L", "빙그레 바나나맛우유", "덴마크 플레인요거트",
    "양파 1.5kg", "깻잎 1봉", "대파 1단", "감자 1kg",
    "브로콜리 1송이", "바나나 1송이", "딸기 500g", "사과 3개입",
    "새우 냉동 500g", "오징어 1마리", "동원 참치캔 150g",
    "CJ 햇반 210g", "신라면 5입", "진비빔면 4입",
    "고추장 500g", "청정원 올리브유 500ml", "스팸 340g",
    "비타김밥단무지", "느타리버섯", "백오이", "인큐애호박",
]


def _find_font(size=22):
    from PIL import ImageFont
    for p in FONT_SEARCH_PATHS:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue
    return ImageFont.load_default()


def make_clean_receipt(items: list[str], width=580) -> Image.Image:
    """순수 PIL로 깨끗한 영수증 이미지를 렌더링한다."""
    font = _find_font(22)
    font_sm = _find_font(18)
    margin, y = 30, 30
    lines = []

    lines.append((y, "테스트마트", _find_font(26), "center")); y += 36
    lines.append((y, f"[구매] 2026-04-17 12:00", font_sm, "left")); y += 28
    lines.append((y, "─" * 38, font_sm, "left")); y += 22
    lines.append((y, "  상품명            단가  수량    금액", font_sm, "left")); y += 26
    lines.append((y, "─" * 38, font_sm, "left")); y += 22

    for idx, name in enumerate(items, 1):
        price = random.randint(800, 15000)
        qty = 1
        text = f"{idx:02d} {name:<16s} {price:>6,d}   {qty}  {price*qty:>7,d}"
        lines.append((y, text, font, "left")); y += 30

    lines.append((y, "─" * 38, font_sm, "left")); y += 22
    total = random.randint(10000, 80000)
    lines.append((y, f"{'합 계':>20s}{total:>18,d}", font, "left")); y += 40

    img = Image.new("L", (width, y + 20), color=245)
    draw = ImageDraw.Draw(img)
    for (ly, text, f, align) in lines:
        try:
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
        except Exception:
            tw = len(text) * 11
        x = (width - tw) // 2 if align == "center" else margin
        draw.text((x, ly), text, fill=20, font=f)
    return img


# ── 열화 함수 ──────────────────────────────────────────────────
def degrade_clean(img: Image.Image) -> Image.Image:
    return img.copy()


def degrade_mild(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    arr += np.random.normal(0, 8, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(arr)
    result = ImageEnhance.Brightness(result).enhance(random.uniform(0.9, 1.1))
    return result


def degrade_medium(img: Image.Image) -> Image.Image:
    arr = np.array(img.convert("RGB"), dtype=np.float32)
    arr += np.random.normal(0, 18, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(arr)
    result = result.filter(ImageFilter.GaussianBlur(radius=0.8))
    result = result.rotate(random.uniform(-2.5, 2.5), expand=True, fillcolor=(230, 230, 230))
    result = ImageEnhance.Brightness(result).enhance(random.uniform(0.75, 1.15))
    result = ImageEnhance.Contrast(result).enhance(random.uniform(0.7, 1.1))

    w, h = result.size
    gradient = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(gradient)
    for i in range(h):
        val = int(35 * (i / h))
        gd.line([(0, i), (w, i)], fill=val)
    result = ImageChops.subtract(result, gradient.convert("RGB"))
    return result


def degrade_severe(img: Image.Image) -> Image.Image:
    w, h = img.size
    small = img.convert("RGB").resize((int(w * 0.45), int(h * 0.45)), Image.LANCZOS)
    upscaled = small.resize((w, h), Image.LANCZOS)

    arr = np.array(upscaled, dtype=np.float32)
    arr += np.random.normal(0, 30, arr.shape)
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    result = Image.fromarray(arr)
    result = result.filter(ImageFilter.GaussianBlur(radius=1.5))
    result = result.rotate(random.uniform(-4, 4), expand=True, fillcolor=(220, 220, 220))
    result = ImageEnhance.Brightness(result).enhance(random.uniform(0.6, 1.3))
    result = ImageEnhance.Contrast(result).enhance(random.uniform(0.5, 0.9))

    w2, h2 = result.size
    gradient = Image.new("L", (w2, h2), 0)
    gd = ImageDraw.Draw(gradient)
    for i in range(w2):
        val = int(50 * abs(i - w2 // 2) / (w2 // 2))
        gd.line([(i, 0), (i, h2)], fill=val)
    result = ImageChops.subtract(result, gradient.convert("RGB"))
    return result


DEGRADATIONS = {
    "clean": degrade_clean,
    "mild": degrade_mild,
    "medium": degrade_medium,
    "severe": degrade_severe,
}


# ── 전처리 ────────────────────────────────────────────────────
def preprocess_raw(image_path: str) -> str:
    """전처리 없음: 원본 그대로 OCR에 전달"""
    return image_path


def preprocess_old(image_path: str) -> str:
    """기존 v0.1: grayscale → autocontrast → contrast enhance 1.5x"""
    img = Image.open(image_path)
    img = ImageOps.exif_transpose(img)
    gray = ImageOps.grayscale(img)
    enhanced = ImageEnhance.Contrast(ImageOps.autocontrast(gray)).enhance(1.5)
    out = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    enhanced.save(out.name, format="PNG")
    return out.name


def preprocess_new(image_path: str) -> str:
    """고도화: 품질 기반 적응형 전처리 (upscale + denoise + 로컬 대비)"""
    from ocr_qwen.preprocess import preprocess_receipt
    result = preprocess_receipt(image_path, persist=True)
    return result.output_path


PREPROCESSORS = {
    "RAW": preprocess_raw,
    "OLD": preprocess_old,
    "NEW": preprocess_new,
}


# ── OCR 실행 ──────────────────────────────────────────────────
def run_ocr(engine, image_path: str) -> list[str]:
    texts = []
    try:
        for page in engine.predict(image_path):
            if isinstance(page, dict) and "rec_texts" in page:
                texts.extend(page["rec_texts"])
            elif hasattr(page, "rec_texts"):
                texts.extend(page.rec_texts)
    except Exception:
        pass
    return texts


# ── 평가 메트릭 ───────────────────────────────────────────────
def match_names(gt_names: list[str], ocr_texts: list[str]) -> tuple[int, int, list[dict]]:
    """상품명 매칭: 정밀도와 재현율을 동시에 측정한다."""
    matched = 0
    details = []
    for gt in gt_names:
        gt_c = gt.replace(" ", "").lower()
        best_score, best_match = 0.0, ""
        for t in ocr_texts:
            tc = t.replace(" ", "").lower()
            if gt_c in tc or tc in gt_c:
                s = max(0.9, SequenceMatcher(None, gt_c, tc).ratio())
            else:
                s = SequenceMatcher(None, gt_c, tc).ratio()
            if s > best_score:
                best_score, best_match = s, t
        hit = best_score >= 0.5
        if hit:
            matched += 1
        details.append({"gt": gt, "best": best_match, "sim": round(best_score, 3), "hit": hit})
    return matched, len(gt_names), details


def char_accuracy(ref: str, hyp: str) -> float:
    """문자 정확도: 1 - (편집거리 / 참조길이)."""
    r = ref.replace(" ", "")
    h = hyp.replace(" ", "")
    if not r:
        return 1.0 if not h else 0.0
    n, m = len(r), len(h)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            cost = 0 if r[i - 1] == h[j - 1] else 1
            tmp = dp[j]
            dp[j] = min(dp[j] + 1, dp[j - 1] + 1, prev + cost)
            prev = tmp
    return max(0.0, 1.0 - dp[m] / n)


# ── 메인 벤치마크 ─────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=10,
                        help="생성할 영수증 수 (각각에 4가지 열화 적용)")
    args = parser.parse_args()

    random.seed(42)
    np.random.seed(42)

    from paddleocr import PaddleOCR
    print("PaddleOCR 엔진 로딩 중...")
    engine = PaddleOCR(use_textline_orientation=True, lang="korean")
    print("엔진 준비 완료\n")

    total_tests = args.samples * len(DEGRADATIONS)
    print(f"벤치마크: {args.samples}건 × {len(DEGRADATIONS)}단계 열화 × 3가지 전처리\n")

    all_results = {pp: {d: [] for d in DEGRADATIONS} for pp in PREPROCESSORS}

    output_dir = PROJECT_ROOT / "data" / "benchmark_output"
    output_dir.mkdir(parents=True, exist_ok=True)

    test_num = 0
    for i in range(args.samples):
        n_items = random.randint(4, 10)
        items = random.sample(PRODUCTS, n_items)
        clean_img = make_clean_receipt(items)
        gt_names = items

        for deg_name, deg_fn in DEGRADATIONS.items():
            test_num += 1
            degraded = deg_fn(clean_img)
            tmp_path = str(output_dir / f"tmp_{i}_{deg_name}.png")
            degraded.save(tmp_path)

            pp_line_parts = []
            for pp_name, pp_fn in PREPROCESSORS.items():
                t0 = time.time()
                pp_path = pp_fn(tmp_path)
                pp_ms = (time.time() - t0) * 1000
                t0 = time.time()
                texts = run_ocr(engine, pp_path)
                ocr_ms = (time.time() - t0) * 1000
                m, t, d = match_names(gt_names, texts)
                recall = m / t if t else 0
                hit_accs = [char_accuracy(di["gt"], di["best"]) for di in d if di["hit"]]
                acc = sum(hit_accs) / len(hit_accs) if hit_accs else 0.0
                if pp_path != tmp_path:
                    Path(pp_path).unlink(missing_ok=True)

                all_results[pp_name][deg_name].append({
                    "recall": recall, "char_acc": acc,
                    "pp_ms": pp_ms, "ocr_ms": ocr_ms,
                })
                pp_line_parts.append(f"{pp_name}={recall:.0%}")

            Path(tmp_path).unlink(missing_ok=True)
            print(f"  [{test_num:02d}/{total_tests}] s={i+1:02d} {deg_name:>7s} | "
                  f"{' | '.join(pp_line_parts)}")

    # ── 종합 결과 ──
    def avg(lst, key):
        return sum(x[key] for x in lst) / len(lst) if lst else 0

    pp_names = list(PREPROCESSORS.keys())

    print("\n" + "═" * 80)
    print("                 전처리 방식별 OCR 성능 비교 (상품명 Recall)")
    print("═" * 80)
    header = f"  {'열화 단계':<10s}"
    for pp in pp_names:
        header += f" │ {pp:>10s}"
    header += f" │ {'RAW→OLD':>8s} │ {'OLD→NEW':>8s}"
    print(header)
    print(f"  {'─'*10}" + f" │ {'─'*10}" * len(pp_names) + f" │ {'─'*8} │ {'─'*8}")

    totals = {pp: [] for pp in pp_names}

    for deg in DEGRADATIONS:
        line = f"  {deg:<10s}"
        vals = {}
        for pp in pp_names:
            v = avg(all_results[pp][deg], "recall")
            vals[pp] = v
            totals[pp].extend([x["recall"] for x in all_results[pp][deg]])
            line += f" │ {v:>9.1%}"
        d1 = vals.get("OLD", 0) - vals.get("RAW", 0)
        d2 = vals.get("NEW", 0) - vals.get("OLD", 0)
        line += f" │ {d1:>+7.1%} │ {d2:>+7.1%}"
        print(line)

    print(f"  {'─'*10}" + f" │ {'─'*10}" * len(pp_names) + f" │ {'─'*8} │ {'─'*8}")
    line = f"  {'전체 평균':<10s}"
    overall = {}
    for pp in pp_names:
        v = sum(totals[pp]) / len(totals[pp]) if totals[pp] else 0
        overall[pp] = v
        line += f" │ {v:>9.1%}"
    d1 = overall.get("OLD", 0) - overall.get("RAW", 0)
    d2 = overall.get("NEW", 0) - overall.get("OLD", 0)
    line += f" │ {d1:>+7.1%} │ {d2:>+7.1%}"
    print(line)

    print(f"\n  문자 정확도 (매칭된 상품명의 글자 수준 정확도):")
    for deg in DEGRADATIONS:
        parts = []
        for pp in pp_names:
            v = avg(all_results[pp][deg], "char_acc")
            parts.append(f"{pp}={v:.0%}")
        print(f"    {deg:>7s}: {' | '.join(parts)}")

    print(f"\n  전처리 시간 (평균):")
    for deg in DEGRADATIONS:
        parts = []
        for pp in pp_names:
            v = avg(all_results[pp][deg], "pp_ms")
            parts.append(f"{pp}={v:.0f}ms")
        print(f"    {deg:>7s}: {' | '.join(parts)}")

    print("═" * 80)

    report = {"preprocessors": pp_names, "degradations": list(DEGRADATIONS.keys())}
    for pp in pp_names:
        report[pp] = {}
        for deg in DEGRADATIONS:
            report[pp][deg] = {
                "recall": round(avg(all_results[pp][deg], "recall"), 4),
                "char_acc": round(avg(all_results[pp][deg], "char_acc"), 4),
            }
        report[pp]["overall"] = round(overall.get(pp, 0), 4)

    report_path = output_dir / "benchmark_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  리포트 저장: {report_path}")


if __name__ == "__main__":
    main()
