"""Image generation using Pollinations.ai (FREE, no API key required)."""

from __future__ import annotations

import hashlib
import random
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import click
import requests

from .models import Category
from .rate_limiter import FreeTierRateLimiter

# Category-specific style keywords for image prompts
CATEGORY_STYLES: dict[Category, str] = {
    Category.TIPS: (
        "modern minimalist finance infographic style, money growth concept, "
        "green and blue tones, professional clean design, lightbulb or savings icon"
    ),
    Category.NEWS_COMMENTARY: (
        "professional news broadcast style, financial charts and graphs, "
        "dark blue corporate background, data visualization, modern business aesthetic"
    ),
    Category.EDUCATIONAL: (
        "clean educational diagram style, simple illustrations, "
        "whiteboard-like background, friendly approachable design, pastel colors"
    ),
    Category.MOTIVATIONAL: (
        "inspiring sunrise landscape, golden hour lighting, "
        "success and growth symbolism, warm uplifting colors, mountain peak or path"
    ),
    Category.STATS_FACTS: (
        "data visualization infographic style, bold numbers and charts, "
        "modern geometric design, contrasting colors, statistical graphics"
    ),
    Category.COMPARISON: (
        "split comparison layout, two-sided design, versus concept, "
        "balanced visual with contrasting sections, professional comparison chart"
    ),
    Category.MYTH_BUSTING: (
        "dramatic reveal style, broken misconception visual, "
        "truth vs myth contrast, bold red X on myth side, enlightenment concept"
    ),
}

# Fallback template descriptions for when Pollinations.ai fails
FALLBACK_TEMPLATES: list[str] = [
    "finance_blue_gradient",
    "money_growth_green",
    "professional_dark",
    "educational_light",
    "motivational_sunrise",
]


class ImageGenerator:
    """Generates finance-themed images using Pollinations.ai.

    Pollinations.ai is completely FREE:
    - No API key required
    - No rate limits
    - Simple URL-based API
    - URL format: https://image.pollinations.ai/prompt/{encoded_prompt}?width=W&height=H&nologo=true
    """

    def __init__(
        self,
        output_dir: Path,
        rate_limiter: Optional[FreeTierRateLimiter] = None,
        templates_dir: Optional[Path] = None,
    ) -> None:
        self._output_dir = output_dir
        self._rate_limiter = rate_limiter or FreeTierRateLimiter()
        self._templates_dir = templates_dir or Path("templates")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def generate_image(
        self,
        category: Category,
        topic: str = "",
        width: int = 1200,
        height: int = 630,
    ) -> Optional[str]:
        """Generate a finance-themed image for the given category.

        Args:
            category: Content category for style selection.
            topic: Optional topic for prompt customization.
            width: Image width (default 1200 for Facebook).
            height: Image height (default 630 for Facebook).

        Returns:
            Path to the downloaded image file, or None on failure.
        """
        prompt = self._build_prompt(category, topic)

        # Try up to 3 times with progressively simpler prompts
        for attempt in range(3):
            try:
                current_prompt = prompt if attempt == 0 else self._simplify_prompt(prompt, attempt)
                image_path = self._download_image(current_prompt, width, height)
                if image_path:
                    return image_path
            except requests.Timeout:
                click.echo(f"  Image generation timeout (attempt {attempt + 1}/3). Simplifying prompt...")
                time.sleep(2)
            except requests.RequestException as e:
                click.echo(f"  Image generation error (attempt {attempt + 1}/3): {e}")
                time.sleep(2)
            except Exception as e:
                click.echo(f"  Unexpected image error (attempt {attempt + 1}/3): {e}")
                time.sleep(2)

        # All retries failed - use fallback template
        click.echo("  Using fallback template image.")
        return self._get_fallback_image(category, width, height)

    def _build_prompt(self, category: Category, topic: str = "") -> str:
        """Build an image generation prompt with category-specific styling.

        Uses positive prompt engineering to ensure appropriate finance-themed imagery.
        Pollinations.ai does not support negative prompts, so we guide through positives.
        """
        style = CATEGORY_STYLES.get(category, CATEGORY_STYLES[Category.TIPS])

        prompt_parts = [
            "Professional high quality finance themed image",
            style,
            "modern design, clean composition",
            "space for text overlay in center",
            "corporate professional aesthetic",
            "suitable for social media, US audience appeal",
            "safe for work, appropriate business content",
        ]

        if topic:
            # Add topic context but keep it visual
            topic_short = topic[:50] if len(topic) > 50 else topic
            prompt_parts.insert(1, f"concept: {topic_short}")

        return ", ".join(prompt_parts)

    def _simplify_prompt(self, original_prompt: str, attempt: int) -> str:
        """Create a simpler prompt for retry attempts."""
        if attempt == 1:
            # Remove topic-specific parts, keep style
            return "Professional finance themed image, modern clean design, blue and green tones, space for text overlay, corporate business"
        else:
            # Extremely simple fallback prompt
            return "Professional blue gradient background with subtle financial chart elements, clean modern design, space for text"

    def _download_image(self, prompt: str, width: int, height: int) -> Optional[str]:
        """Download an image from Pollinations.ai.

        URL format: https://image.pollinations.ai/prompt/{encoded_prompt}?width=W&height=H&nologo=true
        """
        encoded_prompt = quote(prompt, safe="")

        # Ensure URL is not too long (browsers limit ~2000 chars)
        max_prompt_length = 1500
        if len(encoded_prompt) > max_prompt_length:
            # Truncate the encoded prompt
            prompt = prompt[:500]
            encoded_prompt = quote(prompt, safe="")

        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&nologo=true"

        timeout = self._rate_limiter.get_pollinations_timeout()

        # Add a random seed for variety
        seed = random.randint(1, 999999)
        url += f"&seed={seed}"

        response = requests.get(url, timeout=timeout, stream=True)
        response.raise_for_status()

        # Validate content type
        content_type = response.headers.get("content-type", "")
        if "image" not in content_type and len(response.content) < 1000:
            click.echo(f"  Invalid response from Pollinations.ai (content-type: {content_type})")
            return None

        # Generate unique filename
        prompt_hash = hashlib.md5(prompt.encode()).hexdigest()[:8]
        timestamp = int(time.time())
        filename = f"img_{timestamp}_{prompt_hash}.jpg"
        filepath = self._output_dir / filename

        # Save image
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        # Validate file size (<10MB)
        file_size = filepath.stat().st_size
        if file_size > 10 * 1024 * 1024:
            click.echo(f"  Generated image too large: {file_size / 1024 / 1024:.1f}MB (max 10MB)")
            filepath.unlink()
            return None

        if file_size < 1000:
            click.echo("  Generated image too small, likely invalid.")
            filepath.unlink()
            return None

        return str(filepath)

    def _get_fallback_image(self, category: Category, width: int, height: int) -> Optional[str]:
        """Create or retrieve a fallback template image.

        If no pre-made templates exist, generates a simple gradient image using Pillow.
        """
        try:
            from PIL import Image, ImageDraw

            # Create a professional gradient background based on category
            colors = {
                Category.TIPS: ((34, 139, 34), (0, 100, 0)),           # Green gradient
                Category.NEWS_COMMENTARY: ((25, 25, 112), (0, 0, 80)),  # Dark blue
                Category.EDUCATIONAL: ((70, 130, 180), (100, 149, 237)),  # Light blue
                Category.MOTIVATIONAL: ((255, 165, 0), (255, 69, 0)),    # Orange/red
                Category.STATS_FACTS: ((75, 0, 130), (48, 25, 52)),      # Purple
                Category.COMPARISON: ((0, 128, 128), (0, 80, 80)),       # Teal
                Category.MYTH_BUSTING: ((178, 34, 34), (139, 0, 0)),     # Red
            }

            color_start, color_end = colors.get(category, ((0, 70, 140), (0, 40, 80)))

            img = Image.new("RGB", (width, height))
            draw = ImageDraw.Draw(img)

            # Create vertical gradient
            for y in range(height):
                ratio = y / height
                r = int(color_start[0] + (color_end[0] - color_start[0]) * ratio)
                g = int(color_start[1] + (color_end[1] - color_start[1]) * ratio)
                b = int(color_start[2] + (color_end[2] - color_start[2]) * ratio)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            # Add subtle decorative elements
            for i in range(5):
                x = random.randint(0, width)
                y_pos = random.randint(0, height)
                size = random.randint(20, 60)
                opacity_color = (255, 255, 255)
                draw.ellipse(
                    [x - size, y_pos - size, x + size, y_pos + size],
                    outline=opacity_color,
                    width=1,
                )

            # Save fallback image
            timestamp = int(time.time())
            filename = f"fallback_{category.value.lower()}_{timestamp}.jpg"
            filepath = self._output_dir / filename
            img.save(filepath, "JPEG", quality=90)

            return str(filepath)

        except Exception as e:
            click.echo(f"  Failed to create fallback image: {e}")
            return None
