from __future__ import annotations

from dataclasses import dataclass, field
from io import BytesIO
import math
import tempfile
from pathlib import Path
from typing import Final

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageStat


DEFAULT_CONTRAST_FACTOR: Final[float] = 1.5
DEFAULT_LOW_CONTRAST_THRESHOLD: Final[float] = 24.0
DEFAULT_BLUR_THRESHOLD: Final[float] = 0.25
DEFAULT_MIN_SHORT_SIDE: Final[int] = 420
DEFAULT_UPSCALE_TARGET_SHORT: Final[int] = 800
DEFAULT_OUTPUT_FORMAT: Final[str] = "PNG"


@dataclass(frozen=True)
class PreprocessOptions:
    rotation_hint: int = 0
    contrast_factor: float = DEFAULT_CONTRAST_FACTOR
    low_contrast_threshold: float = DEFAULT_LOW_CONTRAST_THRESHOLD
    blur_threshold: float = DEFAULT_BLUR_THRESHOLD
    min_short_side: int = DEFAULT_MIN_SHORT_SIDE
    output_format: str = DEFAULT_OUTPUT_FORMAT
    persist: bool = False
    output_dir: Path | None = None


@dataclass(frozen=True)
class PreprocessResult:
    image_bytes: bytes | None
    output_path: str | None
    quality_score: float
    rotation_applied: int
    perspective_corrected: bool = False
    low_quality_reasons: list[str] = field(default_factory=list)


class ReceiptPreprocessor:
    def __init__(self, options: PreprocessOptions | None = None) -> None:
        self.options = options or PreprocessOptions()

    def preprocess(
        self,
        source: Image.Image | bytes | bytearray | str | Path,
        *,
        rotation_hint: int | None = None,
        persist: bool | None = None,
        output_dir: Path | str | None = None,
        output_format: str | None = None,
    ) -> PreprocessResult:
        image = self._load_image(source)
        requested_rotation = self.options.rotation_hint if rotation_hint is None else rotation_hint
        persisted = self.options.persist if persist is None else persist
        target_output_dir = self.options.output_dir if output_dir is None else Path(output_dir)
        target_output_format = self.options.output_format if output_format is None else output_format

        normalized_rotation = self._normalize_rotation(requested_rotation)
        rotated = self._apply_rotation(image, normalized_rotation)
        quality_score, low_quality_reasons = self._score_image(rotated)

        processed = self._boost_contrast(self._to_grayscale(rotated))
        image_bytes = self._encode_image(processed, target_output_format)

        output_path: str | None = None
        if persisted:
            output_path = self._persist_image(image_bytes, target_output_dir, target_output_format)

        return PreprocessResult(
            image_bytes=image_bytes,
            output_path=output_path,
            quality_score=quality_score,
            rotation_applied=normalized_rotation,
            perspective_corrected=False,
            low_quality_reasons=low_quality_reasons,
        )

    def _load_image(self, source: Image.Image | bytes | bytearray | str | Path) -> Image.Image:
        if isinstance(source, Image.Image):
            return source.copy()

        if isinstance(source, (bytes, bytearray)):
            return Image.open(BytesIO(bytes(source)))

        path = Path(source)
        return Image.open(path)

    def _normalize_rotation(self, rotation_hint: int) -> int:
        rotation = int(rotation_hint) % 360
        if rotation % 90 != 0:
            raise ValueError("rotation_hint must be a multiple of 90 degrees.")
        return rotation

    def _apply_rotation(self, image: Image.Image, rotation: int) -> Image.Image:
        if rotation == 0:
            return ImageOps.exif_transpose(image)
        return ImageOps.exif_transpose(image).rotate(-rotation, expand=True)

    def _to_grayscale(self, image: Image.Image) -> Image.Image:
        return ImageOps.grayscale(image)

    def _upscale_if_small(self, image: Image.Image) -> Image.Image:
        short_side = min(image.size)
        if short_side >= self.options.min_short_side:
            return image
        scale = min(self.options.min_short_side / short_side, 2.0)
        new_w = int(image.width * scale)
        new_h = int(image.height * scale)
        return image.resize((new_w, new_h), Image.LANCZOS)

    def _quality_aware_enhance(
        self, image: Image.Image, quality_score: float, reasons: list[str],
    ) -> Image.Image:
        """품질 점수에 따라 최소 개입 원칙으로 보정한다.

        일반(≥0.35): autocontrast + contrast (기존 파이프라인 동일)
        저품질(<0.35): denoise + 로컬 정규화로 조명 불균일 보정 + 강한 대비
        """
        contrast_factor = max(1.0, float(self.options.contrast_factor))

        if quality_score >= 0.35:
            result = ImageOps.autocontrast(image)
            return ImageEnhance.Contrast(result).enhance(contrast_factor)

        denoised = image.filter(ImageFilter.MedianFilter(size=3))

        if "low_contrast" in reasons:
            arr = np.array(denoised, dtype=np.float32)
            blurred = denoised.filter(ImageFilter.GaussianBlur(radius=15))
            local_mean = np.clip(np.array(blurred, dtype=np.float32), 1.0, 255.0)
            normalized = np.clip((arr / local_mean) * 128.0, 0, 255)
            blended = np.clip(arr * 0.7 + normalized * 0.3, 0, 255).astype(np.uint8)
            denoised = Image.fromarray(blended)

        result = ImageOps.autocontrast(denoised, cutoff=1)
        return ImageEnhance.Contrast(result).enhance(contrast_factor + 0.3)

    def _boost_contrast(self, image: Image.Image) -> Image.Image:
        contrast_factor = max(1.0, float(self.options.contrast_factor))
        image = ImageOps.autocontrast(image)
        return ImageEnhance.Contrast(image).enhance(contrast_factor)

    def _encode_image(self, image: Image.Image, output_format: str) -> bytes:
        buffer = BytesIO()
        image.save(buffer, format=output_format)
        return buffer.getvalue()

    def _persist_image(self, image_bytes: bytes, output_dir: Path | None, output_format: str) -> str:
        directory = output_dir or Path(tempfile.gettempdir())
        directory.mkdir(parents=True, exist_ok=True)
        suffix = f".{output_format.lower()}"
        with tempfile.NamedTemporaryFile(delete=False, dir=directory, suffix=suffix) as handle:
            handle.write(image_bytes)
            return handle.name

    def _score_image(self, image: Image.Image) -> tuple[float, list[str]]:
        grayscale = ImageOps.grayscale(image)
        contrast_stat = ImageStat.Stat(grayscale)
        contrast_std = contrast_stat.stddev[0] if contrast_stat.stddev else 0.0

        edge_image = grayscale.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edge_image)
        edge_mean = edge_stat.mean[0] if edge_stat.mean else 0.0
        edge_std = edge_stat.stddev[0] if edge_stat.stddev else 0.0

        detail_score = self._clamp((edge_mean + edge_std) / 140.0)
        contrast_score = self._clamp(contrast_std / 64.0)
        quality_score = round((detail_score * 0.65) + (contrast_score * 0.35), 4)

        low_quality_reasons: list[str] = []
        if min(grayscale.size) < self.options.min_short_side:
            low_quality_reasons.append("small_image")
        if contrast_std < self.options.low_contrast_threshold:
            low_quality_reasons.append("low_contrast")
        if detail_score < self.options.blur_threshold:
            low_quality_reasons.append("blurry")
        if quality_score < 0.25:
            low_quality_reasons.append("low_quality")

        return quality_score, low_quality_reasons

    def _clamp(self, value: float) -> float:
        if math.isnan(value) or math.isinf(value):
            return 0.0
        return max(0.0, min(1.0, value))


def preprocess_receipt(
    source: Image.Image | bytes | bytearray | str | Path,
    *,
    rotation_hint: int = 0,
    persist: bool = False,
    output_dir: Path | str | None = None,
    output_format: str = DEFAULT_OUTPUT_FORMAT,
) -> PreprocessResult:
    return ReceiptPreprocessor(
        PreprocessOptions(
            rotation_hint=rotation_hint,
            persist=persist,
            output_dir=Path(output_dir) if output_dir is not None else None,
            output_format=output_format,
        )
    ).preprocess(
        source,
        rotation_hint=rotation_hint,
        persist=persist,
        output_dir=output_dir,
        output_format=output_format,
    )
