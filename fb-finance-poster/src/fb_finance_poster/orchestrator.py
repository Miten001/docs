"""Bulk orchestration engine: content -> image -> overlay -> schedule."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .content_generator import (
    ContentGenerationError,
    ContentGenerator,
    TopicSelector,
)
from .image_generator import DiskSpaceError, ImageGenerator
from .models import (
    Duration,
    PostContent,
    PostStatus,
    RunConfig,
    RunResult,
    SchedulablePost,
    days_in_duration,
)
from .rate_limiter import FreeTierRateLimiter
from .scheduler import (
    FacebookTokenError,
    OptimalTimeCalculator,
    PostScheduler,
)
from .text_overlay import TextOverlayEngine

logger = logging.getLogger("fb_finance_poster")

CONTENT_STORE_FILE = "content_store.json"
MANIFEST_FILE = "manifest.json"


class Orchestrator:
    """Coordinates the full generation and scheduling pipeline."""

    def __init__(
        self,
        config: RunConfig,
        *,
        rate_limiter: FreeTierRateLimiter,
        content_generator: ContentGenerator,
        image_generator: ImageGenerator,
        overlay_engine: TextOverlayEngine,
        scheduler: Optional[PostScheduler] = None,
        time_calculator: Optional[OptimalTimeCalculator] = None,
        topic_selector: Optional[TopicSelector] = None,
        progress_fn: Optional[Callable[[str], None]] = None,
    ) -> None:
        self.config = config
        self.rate_limiter = rate_limiter
        self.content_generator = content_generator
        self.image_generator = image_generator
        self.overlay_engine = overlay_engine
        self.scheduler = scheduler
        self.time_calculator = time_calculator or OptimalTimeCalculator(
            timezone=config.timezone
        )
        self.topic_selector = topic_selector or TopicSelector(
            config.content_categories
        )
        self._progress = progress_fn or (lambda msg: logger.info(msg))
        self.output_dir = config.output_path()

    # -- public API --------------------------------------------------------

    def total_posts(self) -> int:
        return days_in_duration(self.config.duration) * self.config.posts_per_day

    def run(self, resume: bool = False) -> RunResult:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        total_days = days_in_duration(self.config.duration)
        total = total_days * self.config.posts_per_day

        posts, generated = self._generate_posts(total, total_days, resume=resume)

        # Assign optimal scheduled times.
        self._assign_times(posts, total_days)

        result = RunResult(
            total=total,
            generated=generated,
            dry_run=self.config.dry_run,
        )

        if self.config.dry_run or self.scheduler is None:
            self._progress("Dry run: skipping Facebook scheduling.")
            result.scheduled = 0
            result.failed = 0
        else:
            try:
                sched = self.scheduler.schedule_all(
                    [p for p in posts if p.status != PostStatus.FAILED]
                )
                result.scheduled = sched.scheduled
                result.failed = sched.failed + sum(
                    1 for p in posts if p.status == PostStatus.FAILED
                )
                result.failures.extend(sched.failures)
            except FacebookTokenError as exc:
                logger.error("Halting: %s", exc)
                self._progress(
                    "Facebook token expired/invalid. Progress saved. "
                    "Refresh your token and run `resume`."
                )
                self._save_content_store(posts)
                result.failed = total - result.scheduled
                self._write_manifest(posts, result)
                return result

        result.manifest_path = self._write_manifest(posts, result)
        self._save_content_store(posts)
        self._print_summary(result)
        return result

    # -- generation --------------------------------------------------------

    def _generate_posts(
        self, total: int, total_days: int, *, resume: bool
    ) -> tuple[List[SchedulablePost], int]:
        posts: List[SchedulablePost] = []

        if resume:
            posts = self._load_content_store()
            if posts:
                self._progress(
                    f"Resuming: {len(posts)} posts loaded from local store."
                )
                # Rebuild topic selector history to avoid repeats.
                used = [f"{p.content.category.value}:{p.content.topic}" for p in posts]
                self.topic_selector = TopicSelector(
                    self.config.content_categories, used_topics=used
                )

        start_index = len(posts)
        generated = start_index

        for i in range(start_index, total):
            self._progress(
                f"Generating post {i + 1} of {total} "
                f"(service: {self.rate_limiter.preferred_service().value})"
            )
            topic = self.topic_selector.select()
            try:
                content = self.content_generator.generate(topic)
            except ContentGenerationError as exc:
                # Property 20: skip individual failures, keep going.
                logger.warning("Skipping post %d (content failed): %s", i + 1, exc)
                continue

            post = SchedulablePost(content=content, status=PostStatus.PENDING)

            try:
                image_result = self.image_generator.generate(
                    content.category, post.id
                )
                overlay = self.overlay_engine.apply_overlay(
                    image_result.path, content.hook_text
                )
                post.image_path = overlay.output_path
            except DiskSpaceError:
                logger.error(
                    "Disk space exhausted after generating %d posts. "
                    "Free space and run `resume`.",
                    len(posts),
                )
                self._save_content_store(posts)
                break
            except Exception as exc:  # noqa: BLE001
                logger.warning("Image/overlay failed for post %d: %s", i + 1, exc)
                # Still keep the content; scheduling without image will fail
                # gracefully later, but we don't halt the whole run.

            posts.append(post)
            generated += 1
            # Persist incrementally so a crash can be resumed.
            self._save_content_store(posts)

        return posts, generated

    def _assign_times(
        self, posts: List[SchedulablePost], total_days: int
    ) -> None:
        if not posts:
            return
        start = self._start_date()
        times = self.time_calculator.calculate(
            start, total_days, self.config.posts_per_day
        )
        for post, when in zip(posts, times):
            try:
                post.scheduled_time = when
            except Exception as exc:  # noqa: BLE001 - pydantic validation
                logger.warning("Invalid scheduled time for %s: %s", post.id, exc)

    def _start_date(self):
        # Start tomorrow so all times are safely >10 minutes in the future.
        if ZoneInfo is not None:
            now = datetime.now(ZoneInfo(self.config.timezone))
        else:  # pragma: no cover
            now = datetime.now(timezone.utc)
        return (now + timedelta(days=1)).date()

    # -- persistence -------------------------------------------------------

    def _content_store_path(self) -> Path:
        return self.output_dir / CONTENT_STORE_FILE

    def _save_content_store(self, posts: List[SchedulablePost]) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        data = [p.model_dump(mode="json") for p in posts]
        self._content_store_path().write_text(
            json.dumps(data, indent=2, default=str)
        )

    def _load_content_store(self) -> List[SchedulablePost]:
        path = self._content_store_path()
        if not path.exists():
            return []
        try:
            data = json.loads(path.read_text())
            return [SchedulablePost.model_validate(item) for item in data]
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not load content store: %s", exc)
            return []

    def _write_manifest(
        self, posts: List[SchedulablePost], result: RunResult
    ) -> str:
        manifest = {
            "duration": self.config.duration.value,
            "posts_per_day": self.config.posts_per_day,
            "total": result.total,
            "generated": result.generated,
            "scheduled": result.scheduled,
            "failed": result.failed,
            "dry_run": result.dry_run,
            "total_cost": "$0",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "posts": [self._manifest_entry(p) for p in posts],
        }
        path = self.output_dir / MANIFEST_FILE
        path.write_text(json.dumps(manifest, indent=2, default=str))
        return str(path)

    @staticmethod
    def _manifest_entry(post: SchedulablePost) -> dict:
        return {
            "id": post.id,
            "hook_text": post.content.hook_text,
            "body_text": post.content.body_text,
            "category": post.content.category.value,
            "topic": post.content.topic,
            "hashtags": post.content.hashtags,
            "image_path": post.image_path,
            "scheduled_time": (
                post.scheduled_time.isoformat() if post.scheduled_time else None
            ),
            "status": post.status.value,
            "facebook_post_id": post.facebook_post_id,
        }

    # -- reporting ---------------------------------------------------------

    def _print_summary(self, result: RunResult) -> None:
        lines = [
            "",
            "=" * 48,
            "  Facebook Finance Auto-Poster — Run Summary",
            "=" * 48,
            f"  Total posts planned : {result.total}",
            f"  Generated           : {result.generated}",
            f"  Scheduled           : {result.scheduled}",
            f"  Failed              : {result.failed}",
            f"  Dry run             : {result.dry_run}",
            f"  Manifest            : {result.manifest_path}",
            "  Total cost          : $0",
            "=" * 48,
        ]
        self._progress("\n".join(lines))
