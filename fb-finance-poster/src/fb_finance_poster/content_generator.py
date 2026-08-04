"""Content generation: topic selection, Gemini/Groq text generation, validation.

- ``TopicSelector`` picks unique, category-diverse topics (7-day dedup window).
- ``ContentGenerator`` calls Google Gemini (free tier, ``gemini-flash-latest``),
  falling back to Groq (``llama-3.1-70b-versatile``) on rate limits.
- ``ContentValidator`` rejects specific stock picks, return guarantees, and
  other misleading financial claims, triggering regeneration.
"""

from __future__ import annotations

import json
import logging
import random
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

from .models import (
    BODY_MAX_LEN,
    BODY_MIN_LEN,
    HOOK_MAX_LEN,
    HOOK_MIN_LEN,
    MAX_HASHTAGS,
    Category,
    PostContent,
)
from .rate_limiter import FreeTierRateLimiter, TextService

logger = logging.getLogger("fb_finance_poster")


# ---------------------------------------------------------------------------
# Topic catalog
# ---------------------------------------------------------------------------

TOPIC_CATALOG: Dict[Category, List[str]] = {
    Category.TIPS: [
        "automating your savings",
        "cutting recurring subscriptions",
        "building a 3-month emergency fund",
        "using cashback wisely",
        "negotiating your bills",
        "the 50/30/20 budget rule",
        "avoiding lifestyle creep",
        "maximizing employer 401k match",
    ],
    Category.NEWS_COMMENTARY: [
        "what rising interest rates mean for savers",
        "inflation and your grocery budget",
        "why the Fed watches the jobs report",
        "how market volatility affects retirement accounts",
        "the impact of student loan changes",
        "understanding recent CPI numbers",
    ],
    Category.EDUCATIONAL: [
        "how compound interest actually works",
        "index funds vs individual stocks",
        "understanding your credit score",
        "the basics of a Roth IRA",
        "what an expense ratio really costs you",
        "how dollar-cost averaging works",
        "diversification explained simply",
    ],
    Category.MOTIVATIONAL: [
        "why starting small still matters",
        "the mindset of consistent investors",
        "paying yourself first",
        "turning setbacks into a savings plan",
        "the power of long-term thinking",
        "building wealth is a marathon",
    ],
    Category.STATS_FACTS: [
        "the average American savings rate",
        "how many people have no emergency fund",
        "the historical return of the S&P 500",
        "how fees erode long-term returns",
        "the median retirement account balance",
        "how early investing changes outcomes",
    ],
    Category.COMPARISON: [
        "high-yield savings vs checking accounts",
        "renting vs buying a home",
        "traditional vs Roth retirement accounts",
        "ETFs vs mutual funds",
        "paying off debt vs investing",
        "credit cards vs debit cards for building credit",
    ],
    Category.MYTH_BUSTING: [
        "you need to be rich to start investing",
        "carrying a credit card balance helps your score",
        "renting is always throwing money away",
        "you should time the market",
        "budgeting means you can never have fun",
        "checking your credit score hurts it",
    ],
}


@dataclass
class Topic:
    """A concrete topic within a category."""

    name: str
    category: Category

    @property
    def key(self) -> str:
        return f"{self.category.value}:{self.name}"


# ---------------------------------------------------------------------------
# Topic selection
# ---------------------------------------------------------------------------


class TopicSelector:
    """Selects unique topics, weighting toward under-represented categories."""

    def __init__(
        self,
        categories: Sequence[Category],
        *,
        used_topics: Optional[Sequence[str]] = None,
        rng: Optional[random.Random] = None,
        dedup_window: int = 7 * 15,  # ~7 days at max posts/day
    ) -> None:
        if not categories:
            raise ValueError("at least one category is required")
        self.categories = list(categories)
        # `used_topics` is an ordered history; most recent last.
        self._used: List[str] = list(used_topics or [])
        self._rng = rng or random.Random()
        self.dedup_window = dedup_window
        # Category usage counter for diversity weighting.
        self._category_counts: Counter = Counter()

    @property
    def used_topics(self) -> List[str]:
        return list(self._used)

    def _recent_used(self) -> set:
        return set(self._used[-self.dedup_window :])

    def _available_topics(self, category: Category) -> List[str]:
        recent = self._recent_used()
        return [
            name
            for name in TOPIC_CATALOG.get(category, [])
            if f"{category.value}:{name}" not in recent
        ]

    def select(self) -> Topic:
        """Return a topic not used within the dedup window.

        Categories with fewer recent posts are boosted so that content stays
        diverse. Only configured categories are ever selected.
        """
        # Determine which configured categories still have unused topics.
        candidates = [
            c for c in self.categories if self._available_topics(c)
        ]
        if not candidates:
            # All topics exhausted in the window; reset the window to allow
            # reuse of the oldest topics rather than failing.
            self._used = self._used[-1:]
            candidates = [
                c for c in self.categories if self._available_topics(c)
            ]
        if not candidates:  # pragma: no cover - only if catalog empty
            raise RuntimeError("no topics available for configured categories")

        # Weight toward under-represented categories: weight = 1 / (1 + count).
        weights = [
            1.0 / (1.0 + self._category_counts[c]) for c in candidates
        ]
        category = self._rng.choices(candidates, weights=weights, k=1)[0]

        available = self._available_topics(category)
        name = self._rng.choice(available)

        topic = Topic(name=name, category=category)
        self._used.append(topic.key)
        self._category_counts[category] += 1
        return topic

    def select_day(self, count: int) -> List[Topic]:
        """Select topics for a single day ensuring category diversity.

        Guarantees at least ``min(3, count)`` distinct categories when the
        configured category set allows it.
        """
        target_distinct = min(3, count, len(self.categories))
        topics: List[Topic] = []
        used_categories: set = set()

        for i in range(count):
            remaining = count - i
            needed = target_distinct - len(used_categories)
            if needed >= remaining:
                # Force selection from a not-yet-used category to hit diversity.
                forced = [
                    c
                    for c in self.categories
                    if c not in used_categories and self._available_topics(c)
                ]
                if forced:
                    topic = self._select_from(forced)
                else:
                    topic = self.select()
            else:
                topic = self.select()
            topics.append(topic)
            used_categories.add(topic.category)
        return topics

    def _select_from(self, categories: Sequence[Category]) -> Topic:
        weights = [
            1.0 / (1.0 + self._category_counts[c]) for c in categories
        ]
        category = self._rng.choices(list(categories), weights=weights, k=1)[0]
        name = self._rng.choice(self._available_topics(category))
        topic = Topic(name=name, category=category)
        self._used.append(topic.key)
        self._category_counts[category] += 1
        return topic


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

_CATEGORY_GUIDANCE: Dict[Category, str] = {
    Category.TIPS: "Give one actionable personal-finance tip.",
    Category.NEWS_COMMENTARY: "Offer balanced commentary on a finance news theme.",
    Category.EDUCATIONAL: "Explain a finance concept simply and clearly.",
    Category.MOTIVATIONAL: "Inspire disciplined, long-term money habits.",
    Category.STATS_FACTS: "Share an interesting, verifiable finance statistic.",
    Category.COMPARISON: "Compare two finance options fairly with tradeoffs.",
    Category.MYTH_BUSTING: "Debunk a common finance myth with facts.",
}


def build_system_prompt(category: Category) -> str:
    """Build the system prompt for a category (<= 2000 chars)."""
    guidance = _CATEGORY_GUIDANCE[category]
    prompt = (
        "You are a finance content writer creating engaging, compliant social "
        "media posts for a US audience on Facebook. "
        f"Category: {category.value}. {guidance} "
        "Rules: Do NOT recommend specific stocks/tickers to buy or sell. "
        "Do NOT guarantee returns or promise profits. Keep it educational and "
        "general, never personalized financial advice. "
        "Respond with STRICT JSON only, no markdown, using this schema: "
        '{"hook_text": string (10-60 chars, punchy attention-grabber), '
        '"body_text": string (50-500 chars, the post caption), '
        '"hashtags": array of up to 5 strings without the # symbol}.'
    )
    return prompt[:2000]


def build_user_prompt(topic: Topic) -> str:
    return (
        f"Write a {topic.category.value} finance post about: {topic.name}. "
        "Return only the JSON object."
    )


# ---------------------------------------------------------------------------
# Content validation
# ---------------------------------------------------------------------------

_FORBIDDEN_PATTERNS = [
    re.compile(r"\bguarantee(?:d|s)?\b.*\b(return|profit|gain|money)", re.I),
    re.compile(r"\b(return|profit|gain)s?\b.*\bguarantee", re.I),
    re.compile(r"\bbuy\b\s+\$?[A-Z]{2,5}\b"),  # buy TSLA / buy $AAPL
    re.compile(r"\bsell\b\s+\$?[A-Z]{2,5}\b"),
    re.compile(r"\$[A-Z]{1,5}\b"),  # cashtags like $AAPL
    re.compile(r"\bget rich quick\b", re.I),
    re.compile(r"\bcan'?t lose\b", re.I),
    re.compile(r"\brisk[\- ]?free\b.*\b(return|profit|invest)", re.I),
    re.compile(r"\b\d{2,}%\s*(guaranteed|return|profit)", re.I),
    re.compile(r"\bdouble your money\b", re.I),
]


@dataclass
class ValidationResult:
    is_valid: bool
    issues: List[str] = field(default_factory=list)


class ContentValidator:
    """Rejects non-compliant financial content."""

    def validate(self, content: PostContent) -> ValidationResult:
        text = f"{content.hook_text} {content.body_text}"
        issues: List[str] = []
        for pattern in _FORBIDDEN_PATTERNS:
            if pattern.search(text):
                issues.append(
                    f"content matched forbidden pattern: {pattern.pattern}"
                )
        return ValidationResult(is_valid=not issues, issues=issues)

    def validate_text(self, text: str) -> ValidationResult:
        issues = [
            f"text matched forbidden pattern: {p.pattern}"
            for p in _FORBIDDEN_PATTERNS
            if p.search(text)
        ]
        return ValidationResult(is_valid=not issues, issues=issues)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------


def truncate_at_word_boundary(text: str, max_len: int) -> str:
    """Truncate ``text`` to at most ``max_len`` chars at a word boundary."""
    text = text.strip()
    if len(text) <= max_len:
        return text
    truncated = text[:max_len]
    if " " in truncated:
        truncated = truncated[: truncated.rfind(" ")]
    return truncated.strip()


def _pad_to_min(text: str, min_len: int, topic: Topic) -> str:
    """Ensure text meets a minimum length by appending neutral filler."""
    if len(text) >= min_len:
        return text
    filler = (
        f" Learning about {topic.name} is a smart step toward your financial "
        "goals. Save this post for later."
    )
    while len(text) < min_len:
        text = (text + filler).strip()
    return text


class ContentParseError(ValueError):
    """Raised when an AI response cannot be parsed into PostContent."""


def parse_ai_response(raw: str, topic: Topic) -> PostContent:
    """Parse a raw AI JSON response into a validated PostContent."""
    if not raw or not raw.strip():
        raise ContentParseError("empty AI response")

    # Extract the first JSON object from the response.
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ContentParseError("no JSON object found in AI response")
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise ContentParseError(f"invalid JSON: {exc}") from exc

    hook = str(data.get("hook_text", "")).strip()
    body = str(data.get("body_text", "")).strip()
    raw_tags = data.get("hashtags", []) or []

    if not hook or not body:
        raise ContentParseError("missing hook_text or body_text")

    # Normalize lengths to satisfy model constraints.
    if len(hook) > HOOK_MAX_LEN:
        hook = truncate_at_word_boundary(hook, HOOK_MAX_LEN)
    if len(hook) < HOOK_MIN_LEN:
        hook = (hook + f": {topic.name}")[:HOOK_MAX_LEN]
        hook = hook.ljust(HOOK_MIN_LEN, ".")

    if len(body) > BODY_MAX_LEN:
        body = truncate_at_word_boundary(body, BODY_MAX_LEN)
    body = _pad_to_min(body, BODY_MIN_LEN, topic)
    if len(body) > BODY_MAX_LEN:
        body = truncate_at_word_boundary(body, BODY_MAX_LEN)

    hashtags = [str(t) for t in raw_tags][:MAX_HASHTAGS]

    return PostContent(
        hook_text=hook,
        body_text=body,
        category=topic.category,
        topic=topic.name,
        hashtags=hashtags,
    )


# ---------------------------------------------------------------------------
# Content generator
# ---------------------------------------------------------------------------

MAX_CONTENT_RETRIES = 3


class ContentGenerationError(RuntimeError):
    """Raised when content generation fails after all retries/fallbacks."""


class ContentGenerator:
    """Generates PostContent via Gemini with Groq fallback.

    The ``gemini_client`` and ``groq_client`` are dependency-injected so the
    class is fully testable without network access. Each client must expose a
    ``generate(system_prompt, user_prompt) -> (text, token_count)`` method.
    Passing ``None`` disables that backend.
    """

    def __init__(
        self,
        *,
        rate_limiter: FreeTierRateLimiter,
        gemini_client=None,
        groq_client=None,
        validator: Optional[ContentValidator] = None,
        sleep_fn=time.sleep,
        max_retries: int = MAX_CONTENT_RETRIES,
    ) -> None:
        self.rate_limiter = rate_limiter
        self.gemini_client = gemini_client
        self.groq_client = groq_client
        self.validator = validator or ContentValidator()
        self._sleep = sleep_fn
        self.max_retries = max_retries

    def generate(self, topic: Topic) -> PostContent:
        """Generate validated content for a topic, retrying and falling back."""
        system_prompt = build_system_prompt(topic.category)
        user_prompt = build_user_prompt(topic)
        last_error: Optional[Exception] = None

        for attempt in range(1, self.max_retries + 1):
            service = self.rate_limiter.preferred_service()
            try:
                raw, tokens = self._call_service(
                    service, system_prompt, user_prompt
                )
                if service == TextService.GEMINI:
                    self.rate_limiter.record_tokens(tokens)

                content = parse_ai_response(raw, topic)
                result = self.validator.validate(content)
                if result.is_valid:
                    return content

                logger.info(
                    "Content failed compliance validation (attempt %d): %s",
                    attempt,
                    "; ".join(result.issues),
                )
                # Add explicit feedback to steer regeneration.
                user_prompt = build_user_prompt(topic) + (
                    " Avoid specific stock tickers, buy/sell calls, and any "
                    "guarantees of returns."
                )
                last_error = ContentGenerationError(
                    "compliance validation failed"
                )
            except RateLimitError:
                # Route to Groq (if available) and retry immediately.
                self.rate_limiter.note_gemini_rate_limited()
                if not self.rate_limiter.groq_available:
                    self.rate_limiter.wait_for_cooldown(60)
                last_error = ContentGenerationError("rate limited")
                continue
            except QuotaExhaustedError:
                self.rate_limiter.note_gemini_quota_exhausted()
                last_error = ContentGenerationError("quota exhausted")
                continue
            except (ContentParseError, Exception) as exc:  # noqa: BLE001
                last_error = exc
                logger.info(
                    "Content generation attempt %d failed: %s", attempt, exc
                )

            if attempt < self.max_retries:
                self._sleep(2 ** attempt)  # 2s, 4s, 8s exponential backoff

        raise ContentGenerationError(
            f"failed to generate content for topic '{topic.name}': {last_error}"
        )

    def _call_service(self, service: TextService, system_prompt, user_prompt):
        if service == TextService.GROQ:
            if self.groq_client is None:
                raise ContentGenerationError("Groq client not configured")
            return self.groq_client.generate(system_prompt, user_prompt)
        if self.gemini_client is None:
            # No Gemini configured: try Groq if present.
            if self.groq_client is not None:
                return self.groq_client.generate(system_prompt, user_prompt)
            raise ContentGenerationError("no text generation client configured")
        self.rate_limiter.acquire_gemini_slot()
        return self.gemini_client.generate(system_prompt, user_prompt)


class RateLimitError(RuntimeError):
    """Raised by a text client when the provider returns HTTP 429."""


class QuotaExhaustedError(RuntimeError):
    """Raised by a text client when the daily quota is exhausted."""


# ---------------------------------------------------------------------------
# Concrete clients (thin wrappers over the SDKs)
# ---------------------------------------------------------------------------


class GeminiClient:  # pragma: no cover - exercised only with real network/keys
    """Thin wrapper around google-generativeai (``gemini-flash-latest``)."""

    def __init__(self, api_key: str, model: str = "gemini-flash-latest") -> None:
        import google.generativeai as genai

        genai.configure(api_key=api_key)
        self._genai = genai
        self._model = genai.GenerativeModel(model)

    def generate(self, system_prompt: str, user_prompt: str):
        try:
            response = self._model.generate_content(
                f"{system_prompt}\n\n{user_prompt}",
                generation_config={"temperature": 0.8, "max_output_tokens": 2048, "response_mime_type": "application/json"},
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "429" in message or "rate" in message:
                raise RateLimitError(str(exc)) from exc
            if "quota" in message or "exhaust" in message:
                raise QuotaExhaustedError(str(exc)) from exc
            raise
        text = getattr(response, "text", "") or ""
        tokens = 0
        usage = getattr(response, "usage_metadata", None)
        if usage is not None:
            tokens = getattr(usage, "total_token_count", 0) or 0
        return text, tokens


class GroqClient:  # pragma: no cover - exercised only with real network/keys
    """Thin wrapper around the Groq SDK (``llama-3.1-70b-versatile``)."""

    def __init__(
        self, api_key: str, model: str = "llama-3.1-70b-versatile"
    ) -> None:
        from groq import Groq

        self._client = Groq(api_key=api_key)
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str):
        try:
            completion = self._client.chat.completions.create(
                model=self._model,
                temperature=0.8,
                max_tokens=400,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            )
        except Exception as exc:  # noqa: BLE001
            message = str(exc).lower()
            if "429" in message or "rate" in message:
                raise RateLimitError(str(exc)) from exc
            raise
        text = completion.choices[0].message.content or ""
        tokens = 0
        usage = getattr(completion, "usage", None)
        if usage is not None:
            tokens = getattr(usage, "total_tokens", 0) or 0
        return text, tokens
