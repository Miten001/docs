"""Core data models for the Facebook Finance Auto-Poster.

All models are implemented with Pydantic v2 and enforce the validation rules
described in the design document.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Category(str, Enum):
    """Content categories the generator can produce."""

    TIPS = "TIPS"
    NEWS_COMMENTARY = "NEWS_COMMENTARY"
    EDUCATIONAL = "EDUCATIONAL"
    MOTIVATIONAL = "MOTIVATIONAL"
    STATS_FACTS = "STATS_FACTS"
    COMPARISON = "COMPARISON"
    MYTH_BUSTING = "MYTH_BUSTING"


class PostStatus(str, Enum):
    """Lifecycle status of a schedulable post."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class Duration(str, Enum):
    """Supported bulk-run durations."""

    ONE_WEEK = "ONE_WEEK"
    ONE_MONTH = "ONE_MONTH"


# ---------------------------------------------------------------------------
# Validation constants (single source of truth)
# ---------------------------------------------------------------------------

HOOK_MIN_LEN = 10
HOOK_MAX_LEN = 60
BODY_MIN_LEN = 50
BODY_MAX_LEN = 500
MAX_HASHTAGS = 5
POSTS_PER_DAY_MIN = 1
POSTS_PER_DAY_MAX = 15
MIN_SCHEDULE_LEAD = timedelta(minutes=10)
MAX_SCHEDULE_LEAD = timedelta(days=75)
MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PostContent(BaseModel):
    """Structured text content produced by the Content Generator."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hook_text: str
    body_text: str
    category: Category
    topic: str
    hashtags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @field_validator("hook_text")
    @classmethod
    def _validate_hook(cls, value: str) -> str:
        stripped = value.strip()
        if not (HOOK_MIN_LEN <= len(stripped) <= HOOK_MAX_LEN):
            raise ValueError(
                f"hook_text must be {HOOK_MIN_LEN}-{HOOK_MAX_LEN} characters "
                f"(got {len(stripped)})"
            )
        return stripped

    @field_validator("body_text")
    @classmethod
    def _validate_body(cls, value: str) -> str:
        stripped = value.strip()
        if not (BODY_MIN_LEN <= len(stripped) <= BODY_MAX_LEN):
            raise ValueError(
                f"body_text must be {BODY_MIN_LEN}-{BODY_MAX_LEN} characters "
                f"(got {len(stripped)})"
            )
        return stripped

    @field_validator("hashtags")
    @classmethod
    def _validate_hashtags(cls, value: List[str]) -> List[str]:
        if len(value) > MAX_HASHTAGS:
            raise ValueError(
                f"at most {MAX_HASHTAGS} hashtags allowed (got {len(value)})"
            )
        normalized = []
        for tag in value:
            tag = tag.strip()
            if not tag:
                continue
            if not tag.startswith("#"):
                tag = "#" + tag.lstrip("#")
            normalized.append(tag)
        return normalized

    def caption(self) -> str:
        """Full Facebook caption = body text + hashtags on a new line."""
        if self.hashtags:
            return f"{self.body_text}\n\n{' '.join(self.hashtags)}"
        return self.body_text


class SchedulablePost(BaseModel):
    """A PostContent bound to a final image and a scheduled time."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: PostContent
    image_path: Optional[str] = None
    scheduled_time: Optional[datetime] = None
    status: PostStatus = PostStatus.PENDING
    facebook_post_id: Optional[str] = None
    retry_count: int = 0
    error: Optional[str] = None

    @field_validator("scheduled_time")
    @classmethod
    def _validate_scheduled_time(
        cls, value: Optional[datetime]
    ) -> Optional[datetime]:
        if value is None:
            return value
        # Normalize to timezone-aware UTC for consistent comparisons.
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        lead = value - now
        if lead < MIN_SCHEDULE_LEAD:
            raise ValueError(
                "scheduled_time must be at least 10 minutes in the future"
            )
        if lead > MAX_SCHEDULE_LEAD:
            raise ValueError(
                "scheduled_time must be no more than 75 days in the future"
            )
        return value


class ScheduleConfig(BaseModel):
    """Configuration describing how posts are distributed across days."""

    start_date: datetime
    end_date: datetime
    posts_per_day: int
    timezone: str = "America/New_York"

    @field_validator("posts_per_day")
    @classmethod
    def _validate_ppd(cls, value: int) -> int:
        if not (POSTS_PER_DAY_MIN <= value <= POSTS_PER_DAY_MAX):
            raise ValueError(
                f"posts_per_day must be between {POSTS_PER_DAY_MIN} and "
                f"{POSTS_PER_DAY_MAX}"
            )
        return value

    @model_validator(mode="after")
    def _validate_range(self) -> "ScheduleConfig":
        if self.end_date < self.start_date:
            raise ValueError("end_date must not precede start_date")
        return self


class RunConfig(BaseModel):
    """Top-level configuration for a bulk generation & scheduling run.

    Note: secrets (access_token, gemini_api_key, groq_api_key) are intentionally
    excluded from the default string/JSON representation to avoid accidental
    leakage in logs. See `__repr__`.
    """

    duration: Duration = Duration.ONE_WEEK
    posts_per_day: int = 10
    page_id: str = ""
    access_token: str = ""
    gemini_api_key: str = ""
    groq_api_key: Optional[str] = None
    dry_run: bool = False
    output_dir: str = "./output"
    timezone: str = "America/New_York"
    content_categories: List[Category] = Field(
        default_factory=lambda: list(Category)
    )

    @field_validator("posts_per_day")
    @classmethod
    def _validate_ppd(cls, value: int) -> int:
        if not (POSTS_PER_DAY_MIN <= value <= POSTS_PER_DAY_MAX):
            raise ValueError(
                f"posts_per_day must be between {POSTS_PER_DAY_MIN} and "
                f"{POSTS_PER_DAY_MAX} (got {value})"
            )
        return value

    @field_validator("content_categories")
    @classmethod
    def _validate_categories(cls, value: List[Category]) -> List[Category]:
        if not value:
            raise ValueError("content_categories must not be empty")
        return value

    @model_validator(mode="after")
    def _validate_credentials(self) -> "RunConfig":
        # A real (non-dry) run requires Facebook credentials + a Gemini key.
        if not self.dry_run:
            missing = []
            if not self.page_id:
                missing.append("page_id (FB_PAGE_ID)")
            if not self.access_token:
                missing.append("access_token (FB_ACCESS_TOKEN)")
            if not self.gemini_api_key and not self.groq_api_key:
                missing.append("gemini_api_key (GEMINI_API_KEY) or groq_api_key")
            if missing:
                raise ValueError(
                    "missing required credentials for a live run: "
                    + ", ".join(missing)
                )
        return self

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            f"RunConfig(duration={self.duration.value}, "
            f"posts_per_day={self.posts_per_day}, "
            f"page_id={_mask(self.page_id)}, "
            f"access_token={_mask(self.access_token)}, "
            f"gemini_api_key={_mask(self.gemini_api_key)}, "
            f"groq_api_key={_mask(self.groq_api_key or '')}, "
            f"dry_run={self.dry_run}, output_dir={self.output_dir!r})"
        )

    __str__ = __repr__

    def output_path(self) -> Path:
        return Path(self.output_dir)


def _mask(secret: str) -> str:
    """Return a redacted representation of a secret for safe display."""
    if not secret:
        return "<unset>"
    return "***REDACTED***"


def days_in_duration(duration: Duration, start: Optional[datetime] = None) -> int:
    """Return the number of days covered by a duration.

    ONE_WEEK -> 7 days. ONE_MONTH -> the number of days in the month that
    contains ``start`` (defaults to today).
    """
    if duration == Duration.ONE_WEEK:
        return 7
    # ONE_MONTH: number of days in the current calendar month.
    ref = start or datetime.now(timezone.utc)
    if ref.month == 12:
        next_month = ref.replace(year=ref.year + 1, month=1, day=1)
    else:
        next_month = ref.replace(month=ref.month + 1, day=1)
    this_month = ref.replace(day=1)
    return (next_month - this_month).days


class RunResult(BaseModel):
    """Result of a completed (or dry) run."""

    total: int = 0
    generated: int = 0
    scheduled: int = 0
    failed: int = 0
    dry_run: bool = False
    failures: List[dict] = Field(default_factory=list)
    manifest_path: Optional[str] = None

    @property
    def cost(self) -> str:
        return "$0"
