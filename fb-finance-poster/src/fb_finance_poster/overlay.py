"""Text overlay engine using Pillow (free, open-source)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

import click
from PIL import Image, ImageDraw, ImageFont


class TextOverlayEngine:
    """Renders hook text onto images with professional styling.

    Features:
    - Semi-transparent background for contrast (>= 4.5:1 ratio)
    - Safe zones: max 1000px text width on 1200px image
    - Progressive font size reduction (min 16pt)
    - Word-boundary truncation with ellipsis
    - Preserves original image (creates new output file)
    - Output maintains same dimensions as input
    """

    # Minimum font size in points
    MIN_FONT_SIZE = 16
    # Maximum text width ratio (relative to image width)
    MAX_TEXT_WIDTH_RATIO = 0.833  # 1000/1200
    # Padding around text
    PADDING = 20
    # Background opacity (0-255)
    BG_OPACITY = 180

    def __init__(self, output_dir: Optional[Path] = None) -> None:
        self._output_dir = output_dir or Path("./output")
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def apply_overlay(
        self,
        image_path: str,
        hook_text: str,
        position: str = "center",
    ) -> Optional[str]:
        """Apply text overlay to an image.

        Args:
            image_path: Path to the source image.
            hook_text: Text to render (10-60 characters).
            position: Overlay position ('center', 'top', 'bottom').

        Returns:
            Path to the new image with overlay, or None on failure.
        """
        try:
            # Open original image
            img = Image.open(image_path).convert("RGBA")
            original_size = img.size
            width, height = original_size

            # Calculate safe zone constraints
            max_text_width = int(width * self.MAX_TEXT_WIDTH_RATIO)

            # Find optimal font size and prepare text
            font, final_text = self._calculate_font_and_text(
                hook_text, max_text_width, width, height
            )

            # Create overlay layer
            overlay = Image.new("RGBA", original_size, (0, 0, 0, 0))
            draw = ImageDraw.Draw(overlay)

            # Calculate text bounding box
            bbox = draw.textbbox((0, 0), final_text, font=font)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]

            # Calculate position
            x, y = self._calculate_position(
                position, width, height, text_width, text_height
            )

            # Draw semi-transparent background rectangle
            bg_x1 = x - self.PADDING
            bg_y1 = y - self.PADDING
            bg_x2 = x + text_width + self.PADDING
            bg_y2 = y + text_height + self.PADDING

            # Ensure background stays within image bounds
            bg_x1 = max(0, bg_x1)
            bg_y1 = max(0, bg_y1)
            bg_x2 = min(width, bg_x2)
            bg_y2 = min(height, bg_y2)

            draw.rectangle(
                [bg_x1, bg_y1, bg_x2, bg_y2],
                fill=(0, 0, 0, self.BG_OPACITY),
            )

            # Draw text in white (high contrast against dark bg)
            draw.text((x, y), final_text, fill=(255, 255, 255, 255), font=font)

            # Composite overlay onto original
            result = Image.alpha_composite(img, overlay)

            # Convert back to RGB for JPEG output
            result_rgb = result.convert("RGB")

            # Verify dimensions match
            assert result_rgb.size == original_size, "Output dimensions must match input"

            # Save as new file (preserve original)
            base_name = Path(image_path).stem
            output_filename = f"{base_name}_overlay.jpg"
            output_path = self._output_dir / output_filename

            result_rgb.save(output_path, "JPEG", quality=92)

            return str(output_path)

        except Exception as e:
            click.echo(f"  Text overlay failed: {e}")
            return None

    def _calculate_font_and_text(
        self,
        text: str,
        max_width: int,
        img_width: int,
        img_height: int,
    ) -> "tuple":
        """Calculate optimal font size and prepare final text.

        Reduces font size progressively. If text still doesn't fit at min size,
        truncates at word boundary with ellipsis.

        Returns:
            Tuple of (font, final_text).
        """
        # Calculate starting font size based on image dimensions
        start_size = max(32, min(64, img_width // 20))

        font = self._get_font(start_size)
        current_size = start_size
        final_text = text

        # Progressive font size reduction
        while current_size >= self.MIN_FONT_SIZE:
            font = self._get_font(current_size)

            # Test if text fits
            test_img = Image.new("RGB", (img_width, img_height))
            test_draw = ImageDraw.Draw(test_img)
            bbox = test_draw.textbbox((0, 0), final_text, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width <= max_width:
                return font, final_text

            current_size -= 2

        # Text doesn't fit even at minimum font size - truncate
        font = self._get_font(self.MIN_FONT_SIZE)
        final_text = self._truncate_to_fit(text, font, max_width, img_width, img_height)

        return font, final_text

    def _truncate_to_fit(
        self,
        text: str,
        font: "ImageFont.FreeTypeFont",
        max_width: int,
        img_width: int,
        img_height: int,
    ) -> str:
        """Truncate text at word boundary and add ellipsis."""
        test_img = Image.new("RGB", (img_width, img_height))
        test_draw = ImageDraw.Draw(test_img)

        words = text.split()
        result = ""

        for i, word in enumerate(words):
            candidate = result + (" " if result else "") + word
            candidate_with_ellipsis = candidate + "..."

            bbox = test_draw.textbbox((0, 0), candidate_with_ellipsis, font=font)
            text_width = bbox[2] - bbox[0]

            if text_width > max_width:
                if result:
                    return result + "..."
                else:
                    # Even one word doesn't fit - hard truncate
                    for j in range(len(word), 0, -1):
                        candidate = word[:j] + "..."
                        bbox = test_draw.textbbox((0, 0), candidate, font=font)
                        if bbox[2] - bbox[0] <= max_width:
                            return candidate
                    return word[:5] + "..."

            result = candidate

        return result

    def _calculate_position(
        self,
        position: str,
        img_width: int,
        img_height: int,
        text_width: int,
        text_height: int,
    ) -> tuple[int, int]:
        """Calculate text position based on alignment setting."""
        # Always center horizontally
        x = (img_width - text_width) // 2

        if position == "top":
            y = int(img_height * 0.15)
        elif position == "bottom":
            y = int(img_height * 0.75) - text_height
        else:  # center
            y = (img_height - text_height) // 2

        return x, y

    def _get_font(self, size: int) -> "ImageFont.FreeTypeFont":
        """Get a font at the specified size.

        Tries system fonts, falls back to Pillow default.
        """
        # Common font paths on Linux/Mac/Windows
        font_paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu-sans-fonts/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSDisplay.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]

        for font_path in font_paths:
            if os.path.exists(font_path):
                try:
                    return ImageFont.truetype(font_path, size)
                except (OSError, IOError):
                    continue

        # Try to use any available truetype font
        try:
            return ImageFont.truetype("DejaVuSans-Bold", size)
        except (OSError, IOError):
            pass

        # Last resort: Pillow default (bitmap) font
        try:
            return ImageFont.load_default(size=size)
        except TypeError:
            # Older Pillow versions don't support size parameter
            return ImageFont.load_default()
