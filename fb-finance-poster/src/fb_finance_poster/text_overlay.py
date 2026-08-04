"""Text overlay composition using Pillow.

Renders hook text onto a generated image with a semi-transparent dark banner
(guaranteeing a >= 4.5:1 contrast ratio), keeps the text inside a safe zone
(<= 1000px wide on a 1200px image), reduces the font progressively down to a
16pt minimum, and truncates at a word boundary with an ellipsis when needed.
The original image file is preserved; a new output file is produced with the
same dimensions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("fb_finance_poster")

MIN_FONT_SIZE = 16
DEFAULT_MAX_FONT_SIZE = 72
SAFE_WIDTH_RATIO = 1000 / 1200  # <= 1000px on a 1200px-wide image
MIN_CONTRAST_RATIO = 4.5
BANNER_ALPHA = 180  # out of 255 — semi-transparent dark banner


@dataclass
class OverlayResult:
    output_path: str
    font_size: int
    truncated: bool
    text_rendered: str
    text_box: Tuple[int, int, int, int]  # left, top, right, bottom


def _relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """WCAG relative luminance for an sRGB color."""

    def channel(c: int) -> float:
        s = c / 255.0
        return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4

    r, g, b = rgb
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast_ratio(
    fg: Tuple[int, int, int], bg: Tuple[int, int, int]
) -> float:
    """WCAG contrast ratio between two colors (>= 1.0)."""
    l1 = _relative_luminance(fg)
    l2 = _relative_luminance(bg)
    lighter, darker = max(l1, l2), min(l1, l2)
    return (lighter + 0.05) / (darker + 0.05)


def _blend_over(
    top: Tuple[int, int, int], alpha: int, bottom: Tuple[int, int, int]
) -> Tuple[int, int, int]:
    """Alpha-composite ``top`` (with ``alpha``) over ``bottom``."""
    a = alpha / 255.0
    return tuple(int(top[i] * a + bottom[i] * (1 - a)) for i in range(3))


def _load_font(size: int) -> ImageFont.FreeTypeFont:
    """Load a TrueType font at ``size``; fall back gracefully."""
    candidates = [
        "DejaVuSans-Bold.ttf",
        "DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "Arial.ttf",
    ]
    for name in candidates:
        try:
            return ImageFont.truetype(name, size)
        except (OSError, IOError):
            continue
    # Last resort: the bitmap default font (fixed size, but keeps us running).
    return ImageFont.load_default()


def _measure(
    draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont
) -> Tuple[int, int]:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def _wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> List[str]:
    words = text.split()
    lines: List[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        width, _ = _measure(draw, candidate, font)
        if width <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _truncate_to_fit(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_height: int,
    line_spacing: int,
) -> Tuple[List[str], bool]:
    """Truncate at a word boundary + ellipsis so wrapped text fits the box."""
    words = text.split()
    truncated = False
    while words:
        candidate = " ".join(words) + ("…" if truncated else "")
        lines = _wrap_text(draw, candidate, font, max_width)
        total_h = _block_height(draw, lines, font, line_spacing)
        if total_h <= max_height:
            return lines, truncated
        words.pop()
        truncated = True
    # Nothing fits; return a single ellipsis.
    return ["…"], True


def _block_height(
    draw: ImageDraw.ImageDraw,
    lines: List[str],
    font: ImageFont.FreeTypeFont,
    line_spacing: int,
) -> int:
    total = 0
    for line in lines:
        _, h = _measure(draw, line, font)
        total += h + line_spacing
    return max(0, total - line_spacing)


class TextOverlayEngine:
    """Composites hook text onto images with Pillow."""

    def __init__(
        self,
        *,
        min_font_size: int = MIN_FONT_SIZE,
        max_font_size: int = DEFAULT_MAX_FONT_SIZE,
        text_color: Tuple[int, int, int] = (255, 255, 255),
        banner_color: Tuple[int, int, int] = (0, 0, 0),
        banner_alpha: int = BANNER_ALPHA,
    ) -> None:
        self.min_font_size = min_font_size
        self.max_font_size = max_font_size
        self.text_color = text_color
        self.banner_color = banner_color
        self.banner_alpha = banner_alpha

    def apply_overlay(
        self, image_path: str, hook_text: str, output_path: Optional[str] = None
    ) -> OverlayResult:
        src = Path(image_path)
        if output_path is None:
            output_path = str(src.with_name(src.stem + "_final.png"))

        with Image.open(src) as base_img:
            base = base_img.convert("RGBA")
            width, height = base.size

            max_text_width = int(width * SAFE_WIDTH_RATIO)
            side_margin = (width - max_text_width) // 2
            # Text block is constrained vertically to the middle band.
            max_text_height = int(height * 0.5)

            overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            font_size = self.max_font_size
            lines: List[str] = []
            truncated = False
            font = _load_font(font_size)
            line_spacing = max(6, font_size // 5)

            # Progressive font reduction down to the 16pt minimum.
            while font_size >= self.min_font_size:
                font = _load_font(font_size)
                line_spacing = max(6, font_size // 5)
                wrapped = _wrap_text(draw, hook_text, font, max_text_width)
                block_h = _block_height(draw, wrapped, font, line_spacing)
                widest = max(
                    (_measure(draw, ln, font)[0] for ln in wrapped), default=0
                )
                if block_h <= max_text_height and widest <= max_text_width:
                    lines = wrapped
                    break
                font_size -= 2
            else:
                font_size = self.min_font_size
                font = _load_font(font_size)
                line_spacing = max(6, font_size // 5)

            if not lines:
                # Still doesn't fit at min size -> truncate at word boundary.
                lines, truncated = _truncate_to_fit(
                    draw,
                    hook_text,
                    font,
                    max_text_width,
                    max_text_height,
                    line_spacing,
                )

            block_h = _block_height(draw, lines, font, line_spacing)
            block_w = max(
                (_measure(draw, ln, font)[0] for ln in lines), default=0
            )

            # Center the text block within the safe margins.
            pad = 20
            block_left = (width - block_w) // 2
            block_top = (height - block_h) // 2

            # Draw the semi-transparent dark banner behind the text for contrast.
            banner_box = (
                max(side_margin - pad, block_left - pad),
                block_top - pad,
                min(width - side_margin + pad, block_left + block_w + pad),
                block_top + block_h + pad,
            )
            draw.rectangle(
                banner_box,
                fill=(*self.banner_color, self.banner_alpha),
            )

            # Draw each line centered.
            y = block_top
            for line in lines:
                w, h = _measure(draw, line, font)
                x = (width - w) // 2
                draw.text((x, y), line, font=font, fill=(*self.text_color, 255))
                y += h + line_spacing

            composed = Image.alpha_composite(base, overlay)

            # Preserve original: write a NEW file, same dimensions.
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            if out.suffix.lower() in (".jpg", ".jpeg"):
                composed.convert("RGB").save(out, format="JPEG", quality=90)
            else:
                composed.save(out, format="PNG")

            # Verify contrast of white text over the banner-over-background.
            effective_bg = _blend_over(
                self.banner_color, self.banner_alpha, (128, 128, 128)
            )
            ratio = contrast_ratio(self.text_color, effective_bg)
            if ratio < MIN_CONTRAST_RATIO:  # pragma: no cover - defensive
                logger.warning(
                    "Overlay contrast ratio %.2f below %.1f", ratio, MIN_CONTRAST_RATIO
                )

            return OverlayResult(
                output_path=str(out),
                font_size=font_size,
                truncated=truncated,
                text_rendered=" ".join(lines),
                text_box=(
                    block_left,
                    block_top,
                    block_left + block_w,
                    block_top + block_h,
                ),
            )
