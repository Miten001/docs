"""Configuration loading from environment variables and .env files."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from .models import Category, Duration, RunConfig


def load_config(
    env_file: Optional[str] = None,
    duration: Optional[str] = None,
    posts_per_day: Optional[int] = None,
    dry_run: bool = False,
    output_dir: Optional[str] = None,
    categories: Optional[list[str]] = None,
) -> RunConfig:
    """Load configuration from environment variables and optional overrides.

    Args:
        env_file: Path to a .env file. Defaults to .env in current directory.
        duration: Override duration (week/month).
        posts_per_day: Override posts per day.
        dry_run: Whether to skip actual scheduling.
        output_dir: Override output directory.
        categories: Override content categories.

    Returns:
        RunConfig with all settings resolved.
    """
    # Load .env file
    if env_file:
        load_dotenv(env_file)
    else:
        load_dotenv()

    # Resolve duration
    dur = Duration.ONE_WEEK
    if duration:
        dur_map = {
            "week": Duration.ONE_WEEK,
            "one_week": Duration.ONE_WEEK,
            "month": Duration.ONE_MONTH,
            "one_month": Duration.ONE_MONTH,
        }
        dur = dur_map.get(duration.lower(), Duration.ONE_WEEK)

    # Resolve posts per day
    ppd = posts_per_day or int(os.getenv("POSTS_PER_DAY", "10"))

    # Resolve output directory
    out_dir = output_dir or os.getenv("OUTPUT_DIR", "./output")

    # Resolve categories
    content_categories: list[Category] = list(Category)
    if categories:
        content_categories = [Category(c.upper()) for c in categories if c.upper() in Category.__members__]
        if not content_categories:
            content_categories = list(Category)

    # Resolve timezone
    tz = os.getenv("TIMEZONE", "America/New_York")

    return RunConfig(
        duration=dur,
        posts_per_day=ppd,
        page_id=os.getenv("FB_PAGE_ID", ""),
        access_token=os.getenv("FB_ACCESS_TOKEN", ""),
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        groq_api_key=os.getenv("GROQ_API_KEY", ""),
        dry_run=dry_run,
        output_dir=Path(out_dir),
        content_categories=content_categories,
        timezone=tz,
    )


def mask_secret(value: str) -> str:
    """Mask a secret string for safe display. Never log full keys."""
    if not value:
        return "(not set)"
    if len(value) <= 8:
        return "***"
    return value[:4] + "***" + value[-4:]


def validate_config(config: RunConfig) -> list[str]:
    """Validate configuration and return list of error messages.

    Returns:
        Empty list if config is valid, otherwise list of error strings.
    """
    errors: list[str] = []

    if not config.gemini_api_key:
        errors.append("GEMINI_API_KEY is required (free from https://aistudio.google.com)")

    if not config.dry_run:
        if not config.page_id:
            errors.append("FB_PAGE_ID is required for scheduling (set in .env or environment)")
        if not config.access_token:
            errors.append("FB_ACCESS_TOKEN is required for scheduling (set in .env or environment)")

    if config.posts_per_day < 1 or config.posts_per_day > 15:
        errors.append("posts_per_day must be between 1 and 15")

    return errors
