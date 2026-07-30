"""Facebook Graph API post scheduling (FREE - 200 calls/hour)."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import click
import requests

from .models import PostStatus, SchedulablePost, ScheduleConfig, ScheduleResult


class OptimalTimeCalculator:
    """Calculates optimal posting times for US audience engagement.

    Engagement Windows (EST):
    - Morning: 7:00-9:00 AM (weight 0.8)
    - Lunch: 11:30 AM-1:30 PM (weight 1.0 - highest)
    - After-work: 5:00-7:00 PM (weight 0.9)
    - Evening: 8:00-10:00 PM (weight 0.7)
    """

    # Engagement windows: (start_hour, start_min, end_hour, end_min, weight)
    WINDOWS = [
        (7, 0, 9, 0, 0.8),     # Morning commute
        (11, 30, 13, 30, 1.0),  # Lunch break (highest)
        (17, 0, 19, 0, 0.9),   # After work
        (20, 0, 22, 0, 0.7),   # Evening scroll
    ]

    MIN_GAP_MINUTES = 30

    def calculate_times(
        self,
        start_date: datetime,
        total_days: int,
        posts_per_day: int,
    ) -> list[datetime]:
        """Calculate optimal posting times across all days.

        Args:
            start_date: First day of scheduling.
            total_days: Number of days to schedule.
            posts_per_day: Posts per day (1-15).

        Returns:
            List of datetime objects for all scheduled posts.
        """
        all_times: list[datetime] = []

        for day_offset in range(total_days):
            current_date = start_date + timedelta(days=day_offset)
            day_times = self._calculate_day_times(current_date, posts_per_day)
            all_times.extend(day_times)

        return all_times

    def _calculate_day_times(self, date: datetime, posts_per_day: int) -> list[datetime]:
        """Calculate posting times for a single day."""
        # Distribute posts across windows proportionally by weight
        slots = self._distribute_across_windows(posts_per_day)

        day_times: list[datetime] = []

        for window_idx, count in slots.items():
            start_h, start_m, end_h, end_m, _ = self.WINDOWS[window_idx]

            # Calculate window duration in minutes
            window_start_min = start_h * 60 + start_m
            window_end_min = end_h * 60 + end_m
            window_duration = window_end_min - window_start_min

            for i in range(count):
                # Add random offset within window, spaced out
                segment = window_duration // max(count, 1)
                min_offset = i * segment
                max_offset = min((i + 1) * segment, window_duration - 1)

                random_offset = random.randint(min_offset, max_offset)
                total_minutes = window_start_min + random_offset

                hour = total_minutes // 60
                minute = total_minutes % 60

                post_time = date.replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )

                # Ensure time is in the future
                now = datetime.now(timezone.utc)
                if post_time.tzinfo is None:
                    # Assume UTC for scheduling
                    post_time = post_time.replace(tzinfo=timezone.utc)

                if post_time <= now:
                    post_time = now + timedelta(minutes=15)

                day_times.append(post_time)

        # Sort chronologically
        day_times.sort()

        # Enforce minimum 30-minute gap
        day_times = self._enforce_min_gap(day_times)

        return day_times

    def _distribute_across_windows(self, posts_per_day: int) -> dict[int, int]:
        """Distribute posts proportionally across engagement windows.

        Returns:
            Dict mapping window_index -> number_of_posts.
        """
        total_weight = sum(w[4] for w in self.WINDOWS)
        distribution: dict[int, int] = {}
        allocated = 0

        # Allocate proportionally
        for i, window in enumerate(self.WINDOWS):
            weight = window[4]
            share = (weight / total_weight) * posts_per_day
            count = int(share)
            distribution[i] = count
            allocated += count

        # Distribute remaining posts to highest-weight windows
        remaining = posts_per_day - allocated
        sorted_windows = sorted(
            range(len(self.WINDOWS)),
            key=lambda i: self.WINDOWS[i][4],
            reverse=True,
        )

        for i in range(remaining):
            idx = sorted_windows[i % len(sorted_windows)]
            distribution[idx] += 1

        return distribution

    def _enforce_min_gap(self, times: list[datetime]) -> list[datetime]:
        """Ensure minimum 30-minute gap between consecutive posts."""
        if len(times) <= 1:
            return times

        result = [times[0]]
        for i in range(1, len(times)):
            prev = result[-1]
            current = times[i]
            gap = (current - prev).total_seconds() / 60

            if gap < self.MIN_GAP_MINUTES:
                # Push forward
                current = prev + timedelta(minutes=self.MIN_GAP_MINUTES)

            result.append(current)

        return result


class PostScheduler:
    """Schedules posts via the Facebook Graph API (FREE).

    Features:
    - Upload image + message with scheduled_publish_time
    - Rate limit handling (pause on HTTP 429)
    - Retry with exponential backoff (2s, 4s, 8s)
    - 1-second pause between API calls
    - Validates: scheduled_time 10min-75days in future
    """

    FB_GRAPH_API_BASE = "https://graph.facebook.com/v18.0"
    MAX_RETRIES = 3
    INTER_CALL_PAUSE = 1.0  # seconds between API calls

    def __init__(self, page_id: str, access_token: str) -> None:
        self._page_id = page_id
        self._access_token = access_token
        self._time_calculator = OptimalTimeCalculator()

    def validate_token_permissions(self) -> tuple[bool, list[str]]:
        """Validate that the Facebook token has required permissions.

        Returns:
            Tuple of (is_valid, list_of_missing_permissions).
        """
        try:
            url = f"{self.FB_GRAPH_API_BASE}/debug_token"
            params = {
                "input_token": self._access_token,
                "access_token": self._access_token,
            }
            response = requests.get(url, params=params, timeout=30)
            data = response.json()

            if "error" in data:
                return False, [f"Token validation error: {data['error'].get('message', 'Unknown error')}"]

            token_data = data.get("data", {})
            scopes = token_data.get("scopes", [])

            required = ["pages_manage_posts", "pages_read_engagement"]
            missing = [p for p in required if p not in scopes]

            if missing:
                return False, missing

            # Check expiry
            expires_at = token_data.get("expires_at", 0)
            if expires_at > 0:
                expiry = datetime.fromtimestamp(expires_at, tz=timezone.utc)
                if expiry < datetime.now(timezone.utc) + timedelta(hours=1):
                    return False, ["Token expires within 1 hour. Please refresh."]

            return True, []

        except requests.RequestException as e:
            return False, [f"Could not validate token: {e}"]

    def calculate_schedule(
        self,
        start_date: datetime,
        total_days: int,
        posts_per_day: int,
    ) -> list[datetime]:
        """Calculate optimal posting times for the schedule.

        Args:
            start_date: First day of scheduling.
            total_days: Number of days to schedule.
            posts_per_day: Posts per day.

        Returns:
            List of scheduled datetime objects.
        """
        return self._time_calculator.calculate_times(start_date, total_days, posts_per_day)

    def schedule_all(self, posts: list[SchedulablePost]) -> ScheduleResult:
        """Schedule all posts to Facebook.

        Args:
            posts: List of posts with assigned scheduled_times.

        Returns:
            ScheduleResult with counts and failure details.
        """
        result = ScheduleResult(total=len(posts))

        for i, post in enumerate(posts):
            click.echo(f"  Scheduling post {i + 1}/{len(posts)}...")

            success = self._schedule_single_post(post)

            if success:
                result.scheduled += 1
            else:
                result.failed += 1
                result.failures.append({
                    "post_id": post.id,
                    "topic": post.content.topic,
                    "error": "Failed after max retries",
                })

            # Inter-call pause to respect rate limits
            if i < len(posts) - 1:
                time.sleep(self.INTER_CALL_PAUSE)

        return result

    def _schedule_single_post(self, post: SchedulablePost) -> bool:
        """Schedule a single post with retry logic.

        Returns:
            True if scheduled successfully, False otherwise.
        """
        if not post.scheduled_time:
            click.echo("    No scheduled_time set. Skipping.")
            post.status = PostStatus.FAILED
            return False

        # Validate time bounds
        now = datetime.now(timezone.utc)
        min_time = now + timedelta(minutes=10)
        max_time = now + timedelta(days=75)

        if post.scheduled_time < min_time:
            click.echo("    Scheduled time is less than 10 minutes in the future. Adjusting...")
            post.scheduled_time = now + timedelta(minutes=15)

        if post.scheduled_time > max_time:
            click.echo("    Scheduled time exceeds 75 days. Skipping.")
            post.status = PostStatus.FAILED
            return False

        for attempt in range(self.MAX_RETRIES):
            try:
                response = self._call_facebook_api(post)

                if response.status_code == 200:
                    data = response.json()
                    post.facebook_post_id = data.get("id", "")
                    post.status = PostStatus.SCHEDULED
                    return True
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    retry_after = int(response.headers.get("Retry-After", "60"))
                    click.echo(f"    Facebook rate limited. Waiting {retry_after}s...")
                    time.sleep(retry_after)
                elif response.status_code == 401:
                    # Token expired - fatal error
                    click.echo("    Facebook token expired or invalid!")
                    post.status = PostStatus.FAILED
                    raise RuntimeError("Facebook token expired")
                else:
                    error_data = response.json() if response.content else {}
                    error_msg = error_data.get("error", {}).get("message", f"HTTP {response.status_code}")
                    click.echo(f"    Facebook API error (attempt {attempt + 1}): {error_msg}")

            except requests.RequestException as e:
                click.echo(f"    Network error (attempt {attempt + 1}): {e}")
            except RuntimeError:
                raise

            # Exponential backoff
            if attempt < self.MAX_RETRIES - 1:
                wait = 2 ** (attempt + 1)
                time.sleep(wait)

            post.retry_count = attempt + 1

        # All retries failed
        post.status = PostStatus.FAILED
        return False

    def _call_facebook_api(self, post: SchedulablePost) -> requests.Response:
        """Make the actual Facebook Graph API call to schedule a post."""
        url = f"{self.FB_GRAPH_API_BASE}/{self._page_id}/photos"

        # Build message with hashtags
        message = post.content.body_text
        if post.content.hashtags:
            hashtag_str = " ".join(f"#{tag}" for tag in post.content.hashtags)
            message = f"{message}\n\n{hashtag_str}"

        # Convert scheduled_time to Unix timestamp
        scheduled_ts = int(post.scheduled_time.timestamp())  # type: ignore

        # Prepare multipart form data
        data = {
            "message": message,
            "scheduled_publish_time": str(scheduled_ts),
            "published": "false",
            "access_token": self._access_token,
        }

        files = {}
        if post.image_path and Path(post.image_path).exists():
            files["source"] = open(post.image_path, "rb")

        try:
            response = requests.post(url, data=data, files=files, timeout=60)
        finally:
            if files:
                files["source"].close()

        return response

    def cancel_post(self, facebook_post_id: str) -> bool:
        """Cancel a scheduled post on Facebook.

        Args:
            facebook_post_id: The Facebook post ID to cancel.

        Returns:
            True if cancelled successfully.
        """
        try:
            url = f"{self.FB_GRAPH_API_BASE}/{facebook_post_id}"
            params = {"access_token": self._access_token}
            response = requests.delete(url, params=params, timeout=30)
            return response.status_code == 200
        except requests.RequestException as e:
            click.echo(f"  Failed to cancel post {facebook_post_id}: {e}")
            return False
