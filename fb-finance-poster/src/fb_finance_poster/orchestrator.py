"""Main pipeline orchestration - coordinates all components."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click

from .content_gen import ContentGenerator
from .image_gen import ImageGenerator
from .models import (
    Category,
    Duration,
    PostStatus,
    RunConfig,
    RunResult,
    SchedulablePost,
)
from .overlay import TextOverlayEngine
from .rate_limiter import FreeTierRateLimiter
from .scheduler import PostScheduler
from .topic_selector import TopicSelector


def get_total_days(duration: Duration) -> int:
    """Get total days for a duration."""
    if duration == Duration.ONE_WEEK:
        return 7
    elif duration == Duration.ONE_MONTH:
        return 30
    return 7


class Orchestrator:
    """Coordinates the full content generation and scheduling pipeline.

    Pipeline flow:
    1. Calculate total posts needed (days * posts_per_day)
    2. For each post: topic selection -> content gen -> image gen -> text overlay
    3. Calculate optimal posting times
    4. Schedule all posts (or save for dry_run)
    5. Save manifest and display summary

    All at $0 cost using free-tier services.
    """

    def __init__(self, config: RunConfig) -> None:
        self._config = config
        self._rate_limiter = FreeTierRateLimiter()

        # Initialize components
        self._topic_selector = TopicSelector(
            history_path=config.output_dir / "topic_history.json"
        )
        self._content_gen = ContentGenerator(
            gemini_api_key=config.gemini_api_key,
            groq_api_key=config.groq_api_key,
            rate_limiter=self._rate_limiter,
        )
        self._image_gen = ImageGenerator(
            output_dir=config.output_dir / "images",
            rate_limiter=self._rate_limiter,
        )
        self._overlay_engine = TextOverlayEngine(
            output_dir=config.output_dir / "final"
        )

        if not config.dry_run and config.page_id and config.access_token:
            self._scheduler = PostScheduler(
                page_id=config.page_id,
                access_token=config.access_token,
            )
        else:
            self._scheduler = None

        # Ensure output directory exists
        config.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> RunResult:
        """Execute the full pipeline.

        Returns:
            RunResult with generation and scheduling stats.
        """
        total_days = get_total_days(self._config.duration)
        total_posts = total_days * self._config.posts_per_day

        click.echo(f"\n{'='*60}")
        click.echo(f"  Facebook Finance Auto-Poster")
        click.echo(f"  Duration: {self._config.duration.value} ({total_days} days)")
        click.echo(f"  Posts per day: {self._config.posts_per_day}")
        click.echo(f"  Total posts: {total_posts}")
        click.echo(f"  Dry run: {'Yes' if self._config.dry_run else 'No'}")
        click.echo(f"  Total cost: $0 (all services are free!)")
        click.echo(f"{'='*60}\n")

        # Estimate time
        est_minutes = (total_posts * 5) // 60 + 1  # ~5 seconds per post average
        click.echo(f"  Estimated time: ~{est_minutes} minutes")
        click.echo(f"  Using: Google Gemini (free) + Pollinations.ai (free) + Pillow (free)")
        click.echo("")

        # Step 1: Generate all content
        posts = self._generate_all_posts(total_posts, total_days)

        # Step 2: Assign optimal times
        if posts:
            self._assign_schedule_times(posts, total_days)

        # Step 3: Schedule or save
        result = RunResult(
            total_generated=len(posts),
            posts=posts,
            dry_run=self._config.dry_run,
        )

        if not self._config.dry_run and self._scheduler and posts:
            click.echo("\n  Scheduling posts to Facebook...")
            schedule_result = self._scheduler.schedule_all(posts)
            result.total_scheduled = schedule_result.scheduled
            result.total_failed = schedule_result.failed
        else:
            result.total_scheduled = 0
            result.total_failed = 0

        # Step 4: Save manifest
        manifest_path = self._save_manifest(posts)
        result.manifest_path = str(manifest_path)

        # Step 5: Display summary
        self._display_summary(result)

        return result

    def _generate_all_posts(self, total_posts: int, total_days: int) -> list[SchedulablePost]:
        """Generate content, images, and overlays for all posts."""
        posts: list[SchedulablePost] = []
        failed_count = 0

        for i in range(total_posts):
            day_index = i // self._config.posts_per_day
            post_in_day = (i % self._config.posts_per_day) + 1

            click.echo(
                f"  [{i + 1}/{total_posts}] Day {day_index + 1}, "
                f"Post {post_in_day}/{self._config.posts_per_day}"
            )

            try:
                post = self._generate_single_post(day_index)
                if post:
                    posts.append(post)
                    click.echo(f"    OK: \"{post.content.hook_text}\" [{post.content.category.value}]")
                else:
                    failed_count += 1
                    click.echo(f"    SKIPPED: Failed to generate content")
            except Exception as e:
                failed_count += 1
                click.echo(f"    ERROR: {e}")
                # Continue with remaining posts (resilience)
                continue

            # Save progress periodically
            if (i + 1) % 10 == 0:
                self._save_progress(posts)

        if failed_count > 0:
            click.echo(f"\n  {failed_count} posts failed generation (skipped).")

        return posts

    def _generate_single_post(self, day_index: int) -> Optional[SchedulablePost]:
        """Generate a single post: topic -> content -> image -> overlay."""
        # Step 1: Select topic
        topic, category = self._topic_selector.select_topic(
            categories=self._config.content_categories,
            day_index=day_index,
        )

        # Step 2: Generate content via AI (Gemini or Groq - both free)
        content = self._content_gen.generate_post(topic, category)
        if not content:
            return None

        # Step 3: Generate image via Pollinations.ai (free)
        image_path = self._image_gen.generate_image(category, topic)
        if not image_path:
            return None

        # Step 4: Apply text overlay via Pillow (free)
        final_image_path = self._overlay_engine.apply_overlay(
            image_path=image_path,
            hook_text=content.hook_text,
            position="center",
        )

        # Use raw image if overlay fails
        if not final_image_path:
            final_image_path = image_path

        # Create schedulable post
        post = SchedulablePost(
            content=content,
            image_path=final_image_path,
            status=PostStatus.PENDING,
        )

        return post

    def _assign_schedule_times(self, posts: list[SchedulablePost], total_days: int) -> None:
        """Assign optimal posting times to all generated posts."""
        if not self._scheduler:
            # Create a temporary scheduler just for time calculation
            from .scheduler import OptimalTimeCalculator
            calculator = OptimalTimeCalculator()
        else:
            calculator = self._scheduler._time_calculator

        # Start scheduling from tomorrow
        start_date = datetime.now(timezone.utc) + timedelta(days=1)
        start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)

        times = calculator.calculate_times(
            start_date=start_date,
            total_days=total_days,
            posts_per_day=self._config.posts_per_day,
        )

        # Assign times to posts (some posts may have failed, so we have fewer)
        for i, post in enumerate(posts):
            if i < len(times):
                post.scheduled_time = times[i]

    def _save_manifest(self, posts: list[SchedulablePost]) -> Path:
        """Save manifest.json with all post details."""
        manifest_path = self._config.output_dir / "manifest.json"

        manifest_data = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "config": {
                "duration": self._config.duration.value,
                "posts_per_day": self._config.posts_per_day,
                "dry_run": self._config.dry_run,
                "total_cost": "$0",
            },
            "posts": [],
        }

        for post in posts:
            post_data = {
                "id": post.id,
                "hook_text": post.content.hook_text,
                "body_text": post.content.body_text,
                "category": post.content.category.value,
                "topic": post.content.topic,
                "hashtags": post.content.hashtags,
                "image_path": post.image_path,
                "scheduled_time": post.scheduled_time.isoformat() if post.scheduled_time else None,
                "status": post.status.value,
                "facebook_post_id": post.facebook_post_id,
            }
            manifest_data["posts"].append(post_data)

        manifest_path.write_text(json.dumps(manifest_data, indent=2, default=str))
        click.echo(f"\n  Manifest saved: {manifest_path}")

        return manifest_path

    def _save_progress(self, posts: list[SchedulablePost]) -> None:
        """Save intermediate progress for resume capability."""
        progress_path = self._config.output_dir / "progress.json"
        progress_data = {
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "posts_generated": len(posts),
            "config": {
                "duration": self._config.duration.value,
                "posts_per_day": self._config.posts_per_day,
            },
            "post_ids": [p.id for p in posts],
        }
        progress_path.write_text(json.dumps(progress_data, indent=2))

    def _display_summary(self, result: RunResult) -> None:
        """Display execution summary."""
        click.echo(f"\n{'='*60}")
        click.echo(f"  SUMMARY")
        click.echo(f"{'='*60}")
        click.echo(f"  Total generated: {result.total_generated}")
        click.echo(f"  Total scheduled: {result.total_scheduled}")
        click.echo(f"  Total failed:    {result.total_failed}")
        click.echo(f"  Dry run:         {'Yes' if result.dry_run else 'No'}")
        click.echo(f"  Manifest:        {result.manifest_path}")
        click.echo(f"  Total cost:      $0 (all services are free!)")
        click.echo(f"{'='*60}\n")


def resume_from_progress(config: RunConfig) -> Optional[RunResult]:
    """Resume a previously interrupted run from saved progress.

    Reads progress.json and continues from where it left off.
    """
    progress_path = config.output_dir / "progress.json"
    manifest_path = config.output_dir / "manifest.json"

    if not progress_path.exists():
        click.echo("  No progress file found. Starting fresh.")
        return None

    try:
        progress_data = json.loads(progress_path.read_text())
        posts_generated = progress_data.get("posts_generated", 0)
        click.echo(f"  Found progress: {posts_generated} posts already generated.")

        # Load existing manifest if available
        existing_posts: list[SchedulablePost] = []
        if manifest_path.exists():
            manifest_data = json.loads(manifest_path.read_text())
            for post_data in manifest_data.get("posts", []):
                from .models import PostContent
                content = PostContent(
                    id=post_data["id"],
                    hook_text=post_data["hook_text"],
                    body_text=post_data["body_text"],
                    category=Category(post_data["category"]),
                    topic=post_data["topic"],
                    hashtags=post_data.get("hashtags", []),
                )
                post = SchedulablePost(
                    id=post_data["id"],
                    content=content,
                    image_path=post_data.get("image_path", ""),
                    status=PostStatus(post_data.get("status", "PENDING")),
                    facebook_post_id=post_data.get("facebook_post_id"),
                )
                if post_data.get("scheduled_time"):
                    post.scheduled_time = datetime.fromisoformat(post_data["scheduled_time"])
                existing_posts.append(post)

        # Calculate remaining posts
        total_days = get_total_days(config.duration)
        total_needed = total_days * config.posts_per_day
        remaining = total_needed - len(existing_posts)

        if remaining <= 0:
            click.echo("  All posts already generated. Proceeding to scheduling...")
            # Re-create orchestrator just for scheduling
            orchestrator = Orchestrator(config)
            orchestrator._assign_schedule_times(existing_posts, total_days)

            result = RunResult(
                total_generated=len(existing_posts),
                posts=existing_posts,
                dry_run=config.dry_run,
            )

            if not config.dry_run and orchestrator._scheduler:
                # Schedule only unscheduled posts
                to_schedule = [p for p in existing_posts if p.status == PostStatus.PENDING]
                if to_schedule:
                    schedule_result = orchestrator._scheduler.schedule_all(to_schedule)
                    result.total_scheduled = schedule_result.scheduled
                    result.total_failed = schedule_result.failed

            orchestrator._save_manifest(existing_posts)
            result.manifest_path = str(manifest_path)
            orchestrator._display_summary(result)
            return result

        click.echo(f"  Need to generate {remaining} more posts...")

        # Run orchestrator for remaining posts
        orchestrator = Orchestrator(config)
        # Generate only remaining
        new_posts = orchestrator._generate_all_posts(remaining, total_days)
        all_posts = existing_posts + new_posts

        # Schedule
        orchestrator._assign_schedule_times(all_posts, total_days)

        result = RunResult(
            total_generated=len(all_posts),
            posts=all_posts,
            dry_run=config.dry_run,
        )

        if not config.dry_run and orchestrator._scheduler:
            to_schedule = [p for p in all_posts if p.status == PostStatus.PENDING]
            if to_schedule:
                schedule_result = orchestrator._scheduler.schedule_all(to_schedule)
                result.total_scheduled = schedule_result.scheduled
                result.total_failed = schedule_result.failed

        orchestrator._save_manifest(all_posts)
        result.manifest_path = str(manifest_path)
        orchestrator._display_summary(result)
        return result

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        click.echo(f"  Error reading progress file: {e}")
        click.echo("  Starting fresh...")
        return None
