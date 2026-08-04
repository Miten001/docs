"""Free-tier rate limiting for Google Gemini, Groq, and Pollinations.ai.

Enforces the Gemini free-tier limit of 15 requests/minute by:
  * spacing calls at least 4 seconds apart, and
  * using a sliding one-minute window that pauses when fewer than 2 requests
    remain in the current minute.

Also tracks daily Gemini token usage (1M/day) with an 80% alert, provides
Groq fallback routing, and exposes the 60-second Pollinations.ai timeout.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Deque, Optional

logger = logging.getLogger("fb_finance_poster")

# Gemini free-tier limits.
GEMINI_RPM_LIMIT = 15
GEMINI_MIN_SPACING_SECONDS = 4.0
GEMINI_DAILY_TOKEN_LIMIT = 1_000_000
DAILY_TOKEN_ALERT_RATIO = 0.80
RPM_WINDOW_SECONDS = 60.0
RPM_REMAINING_THRESHOLD = 2  # pause when fewer than this many remain

# Pollinations.ai request timeout.
POLLINATIONS_TIMEOUT_SECONDS = 60


class TextService(str, Enum):
    GEMINI = "gemini"
    GROQ = "groq"


@dataclass
class RateLimiterState:
    """Mutable state tracked by the rate limiter (useful for inspection/tests)."""

    call_times: Deque[float] = field(default_factory=deque)
    last_call_time: Optional[float] = None
    daily_tokens_used: int = 0
    alerted_daily_quota: bool = False
    gemini_rate_limited: bool = False
    gemini_quota_exhausted: bool = False
    active_service: TextService = TextService.GEMINI


class FreeTierRateLimiter:
    """Coordinates free-tier API usage across text and image services.

    The ``sleep_fn`` and ``time_fn`` hooks make the limiter fully testable
    without real wall-clock delays.
    """

    def __init__(
        self,
        *,
        rpm_limit: int = GEMINI_RPM_LIMIT,
        min_spacing: float = GEMINI_MIN_SPACING_SECONDS,
        daily_token_limit: int = GEMINI_DAILY_TOKEN_LIMIT,
        groq_available: bool = False,
        sleep_fn: Callable[[float], None] = time.sleep,
        time_fn: Callable[[], float] = time.monotonic,
    ) -> None:
        self.rpm_limit = rpm_limit
        self.min_spacing = min_spacing
        self.daily_token_limit = daily_token_limit
        self.groq_available = groq_available
        self._sleep = sleep_fn
        self._time = time_fn
        self._lock = threading.Lock()
        self.state = RateLimiterState()

    # -- Gemini throttling -------------------------------------------------

    def _prune_window(self, now: float) -> None:
        window_start = now - RPM_WINDOW_SECONDS
        calls = self.state.call_times
        while calls and calls[0] < window_start:
            calls.popleft()

    def acquire_gemini_slot(self) -> None:
        """Block until it is safe to make another Gemini request.

        Guarantees at most ``rpm_limit`` calls in any rolling 60s window and at
        least ``min_spacing`` seconds between consecutive calls.
        """
        with self._lock:
            now = self._time()
            self._prune_window(now)

            # 1) Enforce minimum spacing between consecutive calls.
            if self.state.last_call_time is not None:
                elapsed = now - self.state.last_call_time
                if elapsed < self.min_spacing:
                    self._sleep(self.min_spacing - elapsed)
                    now = self._time()
                    self._prune_window(now)

            # 2) Enforce the rolling-window RPM cap. Pause when fewer than the
            #    threshold number of requests remain in the current minute.
            remaining = self.rpm_limit - len(self.state.call_times)
            if remaining < RPM_REMAINING_THRESHOLD and self.state.call_times:
                oldest = self.state.call_times[0]
                wait = (oldest + RPM_WINDOW_SECONDS) - now
                if wait > 0:
                    logger.info(
                        "Gemini rate limit approached (%d/%d in window); "
                        "pausing %.1fs",
                        len(self.state.call_times),
                        self.rpm_limit,
                        wait,
                    )
                    self._sleep(wait)
                    now = self._time()
                    self._prune_window(now)

            # Record this call.
            self.state.call_times.append(now)
            self.state.last_call_time = now

    def calls_in_current_window(self) -> int:
        """Number of recorded Gemini calls within the last 60 seconds."""
        with self._lock:
            self._prune_window(self._time())
            return len(self.state.call_times)

    # -- Token accounting --------------------------------------------------

    def record_tokens(self, tokens: int) -> None:
        """Record Gemini token usage and alert near the daily quota."""
        with self._lock:
            self.state.daily_tokens_used += max(0, tokens)
            used = self.state.daily_tokens_used
            if (
                not self.state.alerted_daily_quota
                and used >= self.daily_token_limit * DAILY_TOKEN_ALERT_RATIO
            ):
                self.state.alerted_daily_quota = True
                logger.warning(
                    "Approaching Gemini daily free-tier quota: %d/%d tokens "
                    "(%.0f%%). Will switch to Groq when exhausted.",
                    used,
                    self.daily_token_limit,
                    100.0 * used / self.daily_token_limit,
                )
            if used >= self.daily_token_limit:
                self.state.gemini_quota_exhausted = True

    # -- Fallback routing --------------------------------------------------

    def note_gemini_rate_limited(self) -> None:
        """Called when Gemini returns HTTP 429 — route to Groq if available."""
        self.state.gemini_rate_limited = True
        if self.groq_available:
            self.state.active_service = TextService.GROQ
            logger.info("Gemini rate-limited (429); routing to Groq fallback.")

    def note_gemini_quota_exhausted(self) -> None:
        """Called when Gemini daily quota is exhausted — switch to Groq."""
        self.state.gemini_quota_exhausted = True
        if self.groq_available:
            self.state.active_service = TextService.GROQ
            logger.info("Gemini daily quota exhausted; switching to Groq.")

    def preferred_service(self) -> TextService:
        """Return the text service that should currently be used."""
        if (
            self.state.gemini_rate_limited or self.state.gemini_quota_exhausted
        ) and self.groq_available:
            return TextService.GROQ
        return TextService.GEMINI

    def wait_for_cooldown(self, seconds: float) -> None:
        """Pause for the shortest cooldown when all services are limited."""
        logger.info("All text services limited; cooling down %.1fs", seconds)
        self._sleep(seconds)
        # Optimistically clear the transient rate-limit flag after cooldown.
        self.state.gemini_rate_limited = False
        self.state.active_service = TextService.GEMINI

    @property
    def pollinations_timeout(self) -> int:
        return POLLINATIONS_TIMEOUT_SECONDS
