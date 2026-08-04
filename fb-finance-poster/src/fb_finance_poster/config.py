"""Configuration loading and secret-safe logging.

Secrets (API keys, access tokens) are loaded exclusively from environment
variables / a `.env` file, and are NEVER written to logs or console output.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, List, Optional

from dotenv import load_dotenv

from .models import Category, Duration, RunConfig

# Environment variable names.
ENV_FB_PAGE_ID = "FB_PAGE_ID"
ENV_FB_ACCESS_TOKEN = "FB_ACCESS_TOKEN"
ENV_GEMINI_API_KEY = "GEMINI_API_KEY"
ENV_GROQ_API_KEY = "GROQ_API_KEY"
ENV_POSTS_PER_DAY = "POSTS_PER_DAY"
ENV_OUTPUT_DIR = "OUTPUT_DIR"
ENV_TIMEZONE = "TIMEZONE"

# The set of env vars whose values must never be printed.
_SECRET_ENV_VARS = frozenset(
    {ENV_FB_ACCESS_TOKEN, ENV_GEMINI_API_KEY, ENV_GROQ_API_KEY}
)


class SecretRedactingFilter(logging.Filter):
    """A logging filter that scrubs known secret values from log records."""

    def __init__(self, secrets: Iterable[str]):
        super().__init__()
        # Keep only non-trivial secret values.
        self._secrets = [s for s in secrets if s and len(s) >= 4]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        redacted = message
        for secret in self._secrets:
            if secret in redacted:
                redacted = redacted.replace(secret, "***REDACTED***")
        if redacted != message:
            record.msg = redacted
            record.args = ()
        return True


def load_environment(dotenv_path: Optional[str] = None) -> None:
    """Load variables from a .env file into the process environment."""
    load_dotenv(dotenv_path=dotenv_path, override=False)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the package logger with secret redaction enabled."""
    logger = logging.getLogger("fb_finance_poster")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        )
        logger.addHandler(handler)

    secrets = [os.environ.get(name, "") for name in _SECRET_ENV_VARS]
    redactor = SecretRedactingFilter(secrets)
    # Attach to the logger and its handlers.
    logger.addFilter(redactor)
    for handler in logger.handlers:
        handler.addFilter(redactor)
    return logger


def _parse_categories(raw: Optional[str]) -> Optional[List[Category]]:
    if not raw:
        return None
    result: List[Category] = []
    for token in raw.split(","):
        token = token.strip().upper()
        if not token:
            continue
        try:
            result.append(Category(token))
        except ValueError as exc:
            valid = ", ".join(c.value for c in Category)
            raise ValueError(
                f"unknown category '{token}'. Valid categories: {valid}"
            ) from exc
    return result or None


def build_run_config(
    *,
    duration: Optional[str] = None,
    posts_per_day: Optional[int] = None,
    page_id: Optional[str] = None,
    dry_run: bool = False,
    output_dir: Optional[str] = None,
    categories: Optional[str] = None,
    dotenv_path: Optional[str] = None,
) -> RunConfig:
    """Build a validated :class:`RunConfig` from CLI args + environment.

    CLI-supplied arguments take precedence over environment variables.
    Secrets are only ever read from the environment / .env file.
    """
    load_environment(dotenv_path)

    resolved_duration = Duration(duration) if duration else Duration.ONE_WEEK

    if posts_per_day is None:
        env_ppd = os.environ.get(ENV_POSTS_PER_DAY)
        posts_per_day = int(env_ppd) if env_ppd else 10

    resolved_page_id = page_id or os.environ.get(ENV_FB_PAGE_ID, "")
    resolved_output = output_dir or os.environ.get(ENV_OUTPUT_DIR, "./output")
    resolved_tz = os.environ.get(ENV_TIMEZONE, "America/New_York")

    parsed_categories = _parse_categories(categories)

    kwargs = dict(
        duration=resolved_duration,
        posts_per_day=posts_per_day,
        page_id=resolved_page_id,
        access_token=os.environ.get(ENV_FB_ACCESS_TOKEN, ""),
        gemini_api_key=os.environ.get(ENV_GEMINI_API_KEY, ""),
        groq_api_key=os.environ.get(ENV_GROQ_API_KEY) or None,
        dry_run=dry_run,
        output_dir=resolved_output,
        timezone=resolved_tz,
    )
    if parsed_categories is not None:
        kwargs["content_categories"] = parsed_categories

    return RunConfig(**kwargs)
