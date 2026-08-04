"""Optimal posting-time calculation and Facebook Graph API scheduling."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Callable, List, Optional

try:  # Python 3.9+ stdlib
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from .models import (
    MAX_SCHEDULE_LEAD,
    MIN_SCHEDULE_LEAD,
    PostStatus,
    SchedulablePost,
)

logger = logging.getLogger("fb_finance_poster")

MIN_GAP_MINUTES = 30
FB_API_CALL_PAUSE_SECONDS = 1.0
MAX_SCHEDULE_RETRIES = 3
GRAPH_API_BASE = "https://graph.facebook.com/v18.0"


@dataclass(frozen=True)
class EngagementWindow:
    name: str
    start_minute: int  # minutes from midnight (EST)
    end_minute: int
    weight: float

    @property
    def duration(self) -> int:
        return self.end_minute - self.start_minute


# Four US engagement windows (EST). Times expressed as minutes from midnight.
PRIME_WINDOWS: List[EngagementWindow] = [
    EngagementWindow("Morning", 7 * 60, 9 * 60, 0.8),        # 7:00-9:00
    EngagementWindow("Lunch", 11 * 60 + 30, 13 * 60 + 30, 1.0),  # 11:30-13:30
    EngagementWindow("After-work", 17 * 60, 19 * 60, 0.9),  # 17:00-19:00
    EngagementWindow("Evening", 20 * 60, 22 * 60, 0.7),     # 20:00-22:00
]


def _largest_remainder_allocation(
    total: int, weights: List[float]
) -> List[int]:
    """Allocate ``total`` items proportional to ``weights`` (sum == total)."""
    weight_sum = sum(weights)
    exact = [total * w / weight_sum for w in weights]
    floors = [int(x) for x in exact]
    remainder = total - sum(floors)
    # Distribute the remaining items to the largest fractional parts.
    fractional = sorted(
        range(len(weights)), key=lambda i: exact[i] - floors[i], reverse=True
    )
    for i in range(remainder):
        floors[fractional[i % len(floors)]] += 1
    return floors


def _capacity(window: EngagementWindow) -> int:
    """Max posts that fit in a window with the minimum gap."""
    return window.duration // MIN_GAP_MINUTES + 1


def _rebalance_capacity(
    allocation: List[int], windows: List[EngagementWindow]
) -> List[int]:
    """Move overflow from over-capacity windows to windows with room."""
    allocation = list(allocation)
    caps = [_capacity(w) for w in windows]
    for i in range(len(allocation)):
        while allocation[i] > caps[i]:
            # Find another window with spare capacity (prefer adjacent).
            candidates = sorted(
                (j for j in range(len(allocation)) if allocation[j] < caps[j]),
                key=lambda j: (abs(j - i), -windows[j].weight),
            )
            if not candidates:
                # No room anywhere; leave as-is (extremely high posts/day).
                break
            allocation[i] -= 1
            allocation[candidates[0]] += 1
    return allocation


class OptimalTimeCalculator:
    """Distributes posts across US engagement windows with randomized times."""

    def __init__(
        self,
        *,
        timezone: str = "America/New_York",
        rng: Optional[random.Random] = None,
        windows: Optional[List[EngagementWindow]] = None,
    ) -> None:
        self.timezone = timezone
        self._rng = rng or random.Random()
        self.windows = windows or PRIME_WINDOWS
        self._tz = ZoneInfo(timezone) if ZoneInfo is not None else None

    def _day_times(self, day: date, posts_per_day: int) -> List[datetime]:
        allocation = _largest_remainder_allocation(
            posts_per_day, [w.weight for w in self.windows]
        )
        allocation = _rebalance_capacity(allocation, self.windows)

        day_times: List[datetime] = []
        for window, count in zip(self.windows, allocation):
            if count <= 0:
                continue
            # Space posts by at least MIN_GAP; randomize the block start.
            slack = window.duration - (count - 1) * MIN_GAP_MINUTES
            offset = self._rng.randint(0, max(0, slack))
            for i in range(count):
                minute = window.start_minute + offset + i * MIN_GAP_MINUTES
                minute = min(minute, window.end_minute)  # clamp to window
                day_times.append(self._make_datetime(day, minute))

        day_times.sort()
        return self._enforce_min_gap(day_times)

    def _make_datetime(self, day: date, minute_of_day: int) -> datetime:
        hours, minutes = divmod(minute_of_day, 60)
        naive = datetime(day.year, day.month, day.day, hours, minutes)
        if self._tz is not None:
            return naive.replace(tzinfo=self._tz)
        return naive

    @staticmethod
    def _enforce_min_gap(times: List[datetime]) -> List[datetime]:
        if not times:
            return times
        result = [times[0]]
        for t in times[1:]:
            prev = result[-1]
            if (t - prev) < timedelta(minutes=MIN_GAP_MINUTES):
                t = prev + timedelta(minutes=MIN_GAP_MINUTES)
            result.append(t)
        return result

    def calculate(
        self, start_date: date, total_days: int, posts_per_day: int
    ) -> List[datetime]:
        """Return ``total_days * posts_per_day`` scheduled datetimes."""
        times: List[datetime] = []
        for day_offset in range(total_days):
            day = start_date + timedelta(days=day_offset)
            times.extend(self._day_times(day, posts_per_day))
        return times


# ---------------------------------------------------------------------------
# Facebook scheduling
# ---------------------------------------------------------------------------


@dataclass
class ScheduleResult:
    total: int = 0
    scheduled: int = 0
    failed: int = 0
    failures: List[dict] = field(default_factory=list)


class FacebookTokenError(RuntimeError):
    """Raised when the Facebook token is expired/invalid (HTTP 401)."""


class FacebookRateLimitError(RuntimeError):
    """Raised when Facebook returns HTTP 429."""


class PostScheduler:
    """Schedules posts to Facebook via the Graph API with retries + backoff.

    ``client`` is an injectable object exposing
    ``schedule_photo(page_id, image_path, message, scheduled_time, token) -> str``
    (returning the Facebook post id) and ``cancel(post_id, token) -> bool``.
    """

    def __init__(
        self,
        *,
        client=None,
        page_id: str = "",
        access_token: str = "",
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], datetime] = lambda: datetime.now().astimezone(),
        max_retries: int = MAX_SCHEDULE_RETRIES,
    ) -> None:
        self.client = client
        self.page_id = page_id
        self.access_token = access_token
        self._sleep = sleep_fn
        self._now = time_fn
        self.max_retries = max_retries

    def _validate_bounds(self, post: SchedulablePost) -> None:
        if post.scheduled_time is None:
            raise ValueError("post has no scheduled_time")
        lead = post.scheduled_time - self._now()
        if lead < MIN_SCHEDULE_LEAD:
            raise ValueError("scheduled_time must be >= 10 minutes in the future")
        if lead > MAX_SCHEDULE_LEAD:
            raise ValueError("scheduled_time must be <= 75 days in the future")

    def schedule_all(self, posts: List[SchedulablePost]) -> ScheduleResult:
        result = ScheduleResult(total=len(posts))
        for post in posts:
            if self._schedule_one(post):
                result.scheduled += 1
            else:
                result.failed += 1
                result.failures.append(
                    {"post_id": post.id, "error": post.error or "unknown"}
                )
            self._sleep(FB_API_CALL_PAUSE_SECONDS)  # 1s pause between calls

        # Report accuracy invariant: scheduled + failed == total.
        assert result.scheduled + result.failed == result.total
        logger.info(
            "Scheduling complete: %d scheduled, %d failed of %d total",
            result.scheduled,
            result.failed,
            result.total,
        )
        return result

    def _schedule_one(self, post: SchedulablePost) -> bool:
        try:
            self._validate_bounds(post)
        except ValueError as exc:
            post.status = PostStatus.FAILED
            post.error = str(exc)
            return False

        attempt = 0
        while attempt < self.max_retries:
            try:
                fb_id = self.client.schedule_photo(
                    page_id=self.page_id,
                    image_path=post.image_path,
                    message=post.content.caption(),
                    scheduled_time=post.scheduled_time,
                    token=self.access_token,
                )
                post.facebook_post_id = fb_id
                post.status = PostStatus.SCHEDULED
                return True
            except FacebookTokenError:
                # Non-recoverable: propagate so the orchestrator can halt.
                post.status = PostStatus.FAILED
                post.error = "Facebook token expired or invalid (401)"
                raise
            except FacebookRateLimitError:
                logger.warning("Facebook rate limit hit; pausing 60s before retry")
                self._sleep(60)
                # A rate-limit pause does not consume a retry.
                continue
            except Exception as exc:  # noqa: BLE001
                attempt += 1
                post.retry_count = attempt
                post.error = str(exc)
                if attempt < self.max_retries:
                    self._sleep(2 ** attempt)  # 2s, 4s, 8s
                else:
                    post.status = PostStatus.FAILED
        return False

    def cancel(self, post_ids: List[str]) -> dict:
        results = {}
        for pid in post_ids:
            try:
                ok = self.client.cancel(pid, self.access_token)
                results[pid] = "cancelled" if ok else "failed"
            except Exception as exc:  # noqa: BLE001
                results[pid] = f"error: {exc}"
            self._sleep(FB_API_CALL_PAUSE_SECONDS)
        return results


class FacebookGraphClient:  # pragma: no cover - requires real network/token
    """Concrete Facebook Graph API client using requests."""

    def __init__(self, base_url: str = GRAPH_API_BASE) -> None:
        self.base_url = base_url

    def schedule_photo(
        self, *, page_id, image_path, message, scheduled_time, token
    ) -> str:
        import requests

        url = f"{self.base_url}/{page_id}/photos"
        unix_time = int(scheduled_time.timestamp())
        with open(image_path, "rb") as fh:
            response = requests.post(
                url,
                data={
                    "message": message,
                    "published": "false",
                    "scheduled_publish_time": unix_time,
                    "access_token": token,
                },
                files={"source": fh},
                timeout=120,
            )
        _raise_for_graph_status(response)
        return response.json().get("id", "")

    def cancel(self, post_id: str, token: str) -> bool:
        import requests

        url = f"{self.base_url}/{post_id}"
        response = requests.delete(url, data={"access_token": token}, timeout=60)
        _raise_for_graph_status(response)
        return bool(response.json().get("success", True))

    def debug_token(self, token: str) -> dict:
        import requests

        url = f"{self.base_url}/debug_token"
        response = requests.get(
            url,
            params={"input_token": token, "access_token": token},
            timeout=60,
        )
        _raise_for_graph_status(response)
        return response.json().get("data", {})


def _raise_for_graph_status(response) -> None:  # pragma: no cover
    if response.status_code == 401:
        raise FacebookTokenError("Facebook token expired or invalid")
    if response.status_code == 429:
        raise FacebookRateLimitError("Facebook rate limit exceeded")
    response.raise_for_status()
