"""Free Tier Rate Limit Manager for Google Gemini, Groq, and Pollinations.ai."""

from __future__ import annotations

import time
from collections import deque
from enum import Enum
from typing import Optional

import click


class AIService(str, Enum):
    """Available AI text generation services."""

    GEMINI = "gemini"
    GROQ = "groq"


class FreeTierRateLimiter:
    """Manages API rate limits across free-tier services.

    - Google Gemini free tier: 15 RPM, 1M tokens/day
    - Groq free tier: 30 RPM
    - Pollinations.ai: No rate limit (60s timeout per request)
    """

    GEMINI_RPM = 15
    GEMINI_MIN_INTERVAL = 4.0  # seconds between Gemini calls
    GEMINI_DAILY_TOKEN_LIMIT = 1_000_000
    GROQ_RPM = 30
    POLLINATIONS_TIMEOUT = 60  # seconds

    def __init__(self) -> None:
        # Sliding window of timestamps for RPM tracking
        self._gemini_calls: deque[float] = deque()
        self._groq_calls: deque[float] = deque()
        self._last_gemini_call: float = 0.0
        self._last_groq_call: float = 0.0

        # Daily token usage tracking
        self._gemini_daily_tokens: int = 0
        self._daily_reset_time: float = time.time()

        # Service availability flags
        self._gemini_available: bool = True
        self._groq_available: bool = True
        self._gemini_cooldown_until: float = 0.0
        self._groq_cooldown_until: float = 0.0

    @property
    def gemini_daily_tokens_used(self) -> int:
        """Get current daily token usage for Gemini."""
        self._check_daily_reset()
        return self._gemini_daily_tokens

    def _check_daily_reset(self) -> None:
        """Reset daily counters if 24 hours have passed."""
        now = time.time()
        if now - self._daily_reset_time >= 86400:
            self._gemini_daily_tokens = 0
            self._daily_reset_time = now

    def _clean_window(self, calls: deque[float], window: float = 60.0) -> None:
        """Remove entries older than the sliding window."""
        cutoff = time.time() - window
        while calls and calls[0] < cutoff:
            calls.popleft()

    def get_preferred_service(self) -> AIService:
        """Determine which AI service to use based on current rate limit state.

        Returns:
            The preferred service (GEMINI or GROQ).
        """
        now = time.time()

        # Check if Gemini is available
        if self._gemini_available and now >= self._gemini_cooldown_until:
            self._clean_window(self._gemini_calls)
            if len(self._gemini_calls) < self.GEMINI_RPM - 2:
                self._check_daily_reset()
                if self._gemini_daily_tokens < self.GEMINI_DAILY_TOKEN_LIMIT * 0.95:
                    return AIService.GEMINI

        # Fallback to Groq
        if self._groq_available and now >= self._groq_cooldown_until:
            self._clean_window(self._groq_calls)
            if len(self._groq_calls) < self.GROQ_RPM - 2:
                return AIService.GROQ

        # Both rate-limited: wait for shortest cooldown
        gemini_wait = max(0, self._gemini_cooldown_until - now)
        groq_wait = max(0, self._groq_cooldown_until - now)

        if not self._gemini_available and not self._groq_available:
            wait_time = min(gemini_wait, groq_wait) if gemini_wait and groq_wait else max(gemini_wait, groq_wait)
            if wait_time > 0:
                click.echo(f"  Both services rate-limited. Waiting {wait_time:.0f}s...")
                time.sleep(wait_time)
            # Reset after waiting
            self._gemini_available = True
            self._groq_available = True
            return AIService.GEMINI

        # Default to Gemini with a wait
        return AIService.GEMINI

    def wait_for_gemini(self) -> None:
        """Wait if necessary to respect Gemini rate limits (15 RPM, 4s interval)."""
        now = time.time()

        # Enforce minimum interval between calls
        elapsed = now - self._last_gemini_call
        if elapsed < self.GEMINI_MIN_INTERVAL:
            sleep_time = self.GEMINI_MIN_INTERVAL - elapsed
            time.sleep(sleep_time)

        # Enforce RPM limit
        self._clean_window(self._gemini_calls)
        if len(self._gemini_calls) >= self.GEMINI_RPM - 1:
            # Wait until oldest call exits the window
            oldest = self._gemini_calls[0]
            wait_until = oldest + 60.0
            sleep_time = wait_until - time.time()
            if sleep_time > 0:
                click.echo(f"  Gemini RPM limit approached. Waiting {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            self._clean_window(self._gemini_calls)

    def record_gemini_call(self, tokens_used: int = 0) -> None:
        """Record a successful Gemini API call."""
        now = time.time()
        self._gemini_calls.append(now)
        self._last_gemini_call = now
        self._gemini_daily_tokens += tokens_used

        # Alert at 80% daily usage
        self._check_daily_reset()
        if self._gemini_daily_tokens >= self.GEMINI_DAILY_TOKEN_LIMIT * 0.8:
            remaining = self.GEMINI_DAILY_TOKEN_LIMIT - self._gemini_daily_tokens
            click.echo(f"  WARNING: Gemini daily token usage at 80%+. ~{remaining:,} tokens remaining.")

    def mark_gemini_rate_limited(self, cooldown_seconds: float = 60.0) -> None:
        """Mark Gemini as rate-limited and set cooldown."""
        self._gemini_available = False
        self._gemini_cooldown_until = time.time() + cooldown_seconds
        click.echo(f"  Gemini rate-limited. Switching to Groq. Cooldown: {cooldown_seconds:.0f}s")

    def mark_gemini_quota_exhausted(self) -> None:
        """Mark Gemini daily quota as exhausted."""
        self._gemini_available = False
        self._gemini_cooldown_until = self._daily_reset_time + 86400
        click.echo("  Gemini daily quota exhausted. Using Groq for remaining content.")

    def wait_for_groq(self) -> None:
        """Wait if necessary to respect Groq rate limits (30 RPM)."""
        self._clean_window(self._groq_calls)
        if len(self._groq_calls) >= self.GROQ_RPM - 1:
            oldest = self._groq_calls[0]
            wait_until = oldest + 60.0
            sleep_time = wait_until - time.time()
            if sleep_time > 0:
                click.echo(f"  Groq RPM limit approached. Waiting {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            self._clean_window(self._groq_calls)

    def record_groq_call(self) -> None:
        """Record a successful Groq API call."""
        now = time.time()
        self._groq_calls.append(now)
        self._last_groq_call = now

    def mark_groq_rate_limited(self, cooldown_seconds: float = 60.0) -> None:
        """Mark Groq as rate-limited and set cooldown."""
        self._groq_available = False
        self._groq_cooldown_until = time.time() + cooldown_seconds
        click.echo(f"  Groq rate-limited. Cooldown: {cooldown_seconds:.0f}s")

    def get_pollinations_timeout(self) -> int:
        """Get the timeout value for Pollinations.ai requests."""
        return self.POLLINATIONS_TIMEOUT

    def reset(self) -> None:
        """Reset all rate limit state (useful for testing)."""
        self._gemini_calls.clear()
        self._groq_calls.clear()
        self._last_gemini_call = 0.0
        self._last_groq_call = 0.0
        self._gemini_daily_tokens = 0
        self._daily_reset_time = time.time()
        self._gemini_available = True
        self._groq_available = True
        self._gemini_cooldown_until = 0.0
        self._groq_cooldown_until = 0.0
