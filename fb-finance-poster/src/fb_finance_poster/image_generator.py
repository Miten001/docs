"""Image generation via Pollinations.ai (free, no API key required).

Builds a positive-only finance-themed prompt, requests a 1200x630 image from
the Pollinations.ai URL API, downloads and validates it, retries with a
simplified prompt on timeout/failure, and falls back to a locally generated
template image so the pipeline never stalls.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional
from urllib.parse import quote

from .models import MAX_IMAGE_BYTES, Category
from .rate_limiter import POLLINATIONS_TIMEOUT_SECONDS

logger = logging.getLogger("fb_finance_poster")

POLLINATIONS_BASE = "https://image.pollinations.ai/prompt/"
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 630
MAX_IMAGE_RETRIES = 3

# Category-specific positive style keywords. Positive prompt engineering only —
# Pollinations.ai does not support negative prompts.
_CATEGORY_STYLE: Dict[Category, str] = {
    Category.TIPS: "clean minimalist infographic style, piggy bank, calm blue tones",
    Category.NEWS_COMMENTARY: "modern newsroom style, subtle stock chart, professional",
    Category.EDUCATIONAL: "clean flat illustration, books and growth chart, friendly",
    Category.MOTIVATIONAL: "uplifting sunrise over city skyline, aspirational, warm tones",
    Category.STATS_FACTS: "sleek data visualization, bar charts, corporate blue",
    Category.COMPARISON: "balanced split composition, scales, neutral professional palette",
    Category.MYTH_BUSTING: "bold clear typography-friendly background, myth vs fact theme",
}


def get_style_keywords(category: Category) -> str:
    return _CATEGORY_STYLE.get(category, "professional finance theme, clean design")


def build_prompt(category: Category, *, simplified: bool = False) -> str:
    """Build a positive, finance-appropriate image prompt for a category."""
    style = get_style_keywords(category)
    if simplified:
        # Fewer adjectives for retry after a timeout.
        return f"professional finance background, {style.split(',')[0]}, space for text"
    return (
        "Professional finance themed image, "
        f"{style}, modern design, clean composition, "
        "space for text overlay at center, high quality, "
        "US audience appeal, safe for work, tasteful"
    )


def build_pollinations_url(
    prompt: str, *, width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT
) -> str:
    """Construct a valid Pollinations.ai URL from a prompt."""
    encoded = quote(prompt, safe="")
    return (
        f"{POLLINATIONS_BASE}{encoded}"
        f"?width={width}&height={height}&nologo=true"
    )


@dataclass
class ImageResult:
    path: str
    is_fallback: bool = False
    prompt: str = ""


class DiskSpaceError(RuntimeError):
    """Raised when the output directory runs out of space."""


class ImageGenerator:
    """Generates finance images via Pollinations.ai with retry + fallback.

    The ``downloader`` callable ``(url, timeout) -> bytes`` is injectable so the
    generator can be tested without network access.
    """

    def __init__(
        self,
        output_dir: Path,
        *,
        downloader: Optional[Callable[[str, int], bytes]] = None,
        template_dir: Optional[Path] = None,
        timeout: int = POLLINATIONS_TIMEOUT_SECONDS,
        max_retries: int = MAX_IMAGE_RETRIES,
        sleep_fn: Callable[[float], None] = time.sleep,
        width: int = DEFAULT_WIDTH,
        height: int = DEFAULT_HEIGHT,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.raw_dir = self.output_dir / "raw"
        self.template_dir = Path(template_dir) if template_dir else (
            self.output_dir / "templates"
        )
        self._downloader = downloader or _default_downloader
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep_fn
        self.width = width
        self.height = height

    def generate(self, category: Category, post_id: str) -> ImageResult:
        """Generate and store a raw image for a category.

        Returns an :class:`ImageResult`; falls back to a locally-rendered
        template when Pollinations.ai fails after all retries.
        """
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        dest = self.raw_dir / f"{post_id}_raw.png"

        for attempt in range(1, self.max_retries + 1):
            simplified = attempt > 1
            prompt = build_prompt(category, simplified=simplified)
            url = build_pollinations_url(
                prompt, width=self.width, height=self.height
            )
            try:
                data = self._downloader(url, self.timeout)
                self._validate_image_bytes(data)
                self._write_bytes(dest, data)
                logger.info(
                    "Generated image for %s (attempt %d)", post_id, attempt
                )
                return ImageResult(path=str(dest), is_fallback=False, prompt=prompt)
            except DiskSpaceError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    "Image generation attempt %d failed for %s: %s",
                    attempt,
                    post_id,
                    exc,
                )
                if attempt < self.max_retries:
                    self._sleep(2 ** attempt)

        # All retries exhausted -> fallback template image.
        logger.warning(
            "Falling back to template image for %s after %d attempts",
            post_id,
            self.max_retries,
        )
        fallback_path = self._fallback_image(category, post_id)
        return ImageResult(path=str(fallback_path), is_fallback=True, prompt="")

    # -- helpers -----------------------------------------------------------

    def _write_bytes(self, dest: Path, data: bytes) -> None:
        try:
            dest.write_bytes(data)
        except OSError as exc:
            if getattr(exc, "errno", None) == 28:  # ENOSPC
                raise DiskSpaceError("no space left on device") from exc
            raise

    @staticmethod
    def _validate_image_bytes(data: bytes) -> None:
        if not data or len(data) < 100:
            raise ValueError("downloaded image is empty or too small")
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError("downloaded image exceeds 10MB limit")
        # Verify it is a real, decodable JPEG/PNG.
        from io import BytesIO

        from PIL import Image

        with Image.open(BytesIO(data)) as img:
            img.verify()
            if img.format not in ("JPEG", "PNG"):
                raise ValueError(f"unsupported image format: {img.format}")

    def _fallback_image(self, category: Category, post_id: str) -> Path:
        """Return a pre-made template if available, else render one locally."""
        # 1) Use a pre-made template from the library, if present.
        if self.template_dir.exists():
            candidates: List[Path] = sorted(
                list(self.template_dir.glob("*.png"))
                + list(self.template_dir.glob("*.jpg"))
                + list(self.template_dir.glob("*.jpeg"))
            )
            if candidates:
                chosen = candidates[hash(category.value) % len(candidates)]
                return chosen

        # 2) Render a simple gradient template with Pillow.
        return self._render_template(category, post_id)

    def _render_template(self, category: Category, post_id: str) -> Path:
        from PIL import Image, ImageDraw

        self.raw_dir.mkdir(parents=True, exist_ok=True)
        dest = self.raw_dir / f"{post_id}_fallback.png"

        # Category-tinted vertical gradient background.
        palette = {
            Category.TIPS: (18, 74, 122),
            Category.NEWS_COMMENTARY: (40, 44, 60),
            Category.EDUCATIONAL: (24, 90, 78),
            Category.MOTIVATIONAL: (120, 66, 24),
            Category.STATS_FACTS: (30, 55, 110),
            Category.COMPARISON: (60, 60, 70),
            Category.MYTH_BUSTING: (90, 30, 50),
        }
        base = palette.get(category, (30, 40, 60))
        img = Image.new("RGB", (self.width, self.height), base)
        draw = ImageDraw.Draw(img)
        for y in range(self.height):
            factor = 1.0 - (y / self.height) * 0.5
            color = tuple(int(c * factor) for c in base)
            draw.line([(0, y), (self.width, y)], fill=color)
        img.save(dest, format="PNG")
        return dest


def _default_downloader(url: str, timeout: int) -> bytes:  # pragma: no cover
    """Download image bytes from a URL using requests."""
    import requests

    response = requests.get(url, timeout=timeout)
    response.raise_for_status()
    return response.content
