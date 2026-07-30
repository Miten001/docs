"""Core data models for the Facebook Finance Auto-Poster."""

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    """Content categories for finance posts."""

    TIPS = "TIPS"
    NEWS_COMMENTARY = "NEWS_COMMENTARY"
    EDUCATIONAL = "EDUCATIONAL"
    MOTIVATIONAL = "MOTIVATIONAL"
    STATS_FACTS = "STATS_FACTS"
    COMPARISON = "COMPARISON"
    MYTH_BUSTING = "MYTH_BUSTING"


class PostStatus(str, Enum):
    """Status of a schedulable post."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class Duration(str, Enum):
    """Scheduling duration options."""

    ONE_WEEK = "ONE_WEEK"
    ONE_MONTH = "ONE_MONTH"


class RunConfig(BaseModel):
    """Configuration for a bulk generation and scheduling run."""

    duration: Duration = Duration.ONE_WEEK
    posts_per_day: int = Field(default=10, ge=1, le=15)
    page_id: str = ""
    access_token: str = ""
    gemini_api_key: str = ""
    groq_api_key: str = ""
    dry_run: bool = False
    output_dir: Path = Path("./output")
    content_categories: List[Category] = Field(
        default_factory=lambda: list(Category)
    )
    timezone: str = "America/New_York"

    @field_validator("posts_per_day")
    @classmethod
    def validate_posts_per_day(cls, v: int) -> int:
        if v < 1 or v > 15:
            raise ValueError("posts_per_day must be between 1 and 15")
        return v


class PostContent(BaseModel):
    """Structured content for a single finance post."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    hook_text: str = Field(..., min_length=10, max_length=60)
    body_text: str = Field(..., min_length=50, max_length=500)
    category: Category
    topic: str
    hashtags: List[str] = Field(default_factory=list, max_length=5)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("hashtags")
    @classmethod
    def validate_hashtags(cls, v: List[str]) -> List[str]:
        if len(v) > 5:
            return v[:5]
        return v


class SchedulablePost(BaseModel):
    """A post ready to be scheduled on Facebook."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: PostContent
    image_path: str = ""
    scheduled_time: Optional[datetime] = None
    status: PostStatus = PostStatus.PENDING
    facebook_post_id: Optional[str] = None
    retry_count: int = 0

    @field_validator("scheduled_time")
    @classmethod
    def validate_scheduled_time(cls, v: Optional[datetime]) -> Optional[datetime]:
        if v is None:
            return v
        now = datetime.now(timezone.utc)
        min_time = now + timedelta(minutes=10)
        max_time = now + timedelta(days=75)
        if v < min_time:
            raise ValueError("scheduled_time must be at least 10 minutes in the future")
        if v > max_time:
            raise ValueError("scheduled_time must be no more than 75 days in the future")
        return v


class ScheduleConfig(BaseModel):
    """Configuration for the scheduling algorithm."""

    start_date: datetime
    end_date: datetime
    posts_per_day: int = Field(default=10, ge=1, le=15)
    timezone: str = "America/New_York"


class ScheduleResult(BaseModel):
    """Result of a scheduling operation."""

    total: int = 0
    scheduled: int = 0
    failed: int = 0
    failures: List[Dict] = Field(default_factory=list)


class RunResult(BaseModel):
    """Result of a full orchestration run."""

    total_generated: int = 0
    total_scheduled: int = 0
    total_failed: int = 0
    posts: List[SchedulablePost] = Field(default_factory=list)
    dry_run: bool = False
    manifest_path: Optional[str] = None
