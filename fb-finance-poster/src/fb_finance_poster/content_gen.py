"""Content generation using Google Gemini free tier with Groq fallback."""

from __future__ import annotations

import json
import re
import time
from typing import Optional

import click

from .models import Category, PostContent
from .rate_limiter import AIService, FreeTierRateLimiter

# System prompts per category for US finance audience
SYSTEM_PROMPTS: dict[Category, str] = {
    Category.TIPS: (
        "You are a friendly US personal finance expert creating social media content. "
        "Generate practical, actionable financial tips for American audiences. "
        "Use simple language, be encouraging, and focus on everyday money-saving or wealth-building strategies. "
        "Do NOT give specific stock picks or guarantee returns."
    ),
    Category.NEWS_COMMENTARY: (
        "You are a US financial commentator creating engaging social media content. "
        "Provide brief, insightful commentary on financial news and market trends relevant to everyday Americans. "
        "Be informative but accessible. Do NOT make predictions or recommend specific investments."
    ),
    Category.EDUCATIONAL: (
        "You are a finance educator creating beginner-friendly social media content for US audiences. "
        "Explain financial concepts in simple terms that anyone can understand. "
        "Use analogies and examples. Do NOT give investment advice or recommend specific products."
    ),
    Category.MOTIVATIONAL: (
        "You are a motivational finance coach creating inspiring social media content. "
        "Encourage Americans to start or continue their financial journey. "
        "Be positive, empowering, and relatable. Focus on mindset and habits. "
        "Do NOT promise specific returns or make unrealistic claims."
    ),
    Category.STATS_FACTS: (
        "You are a data-driven finance content creator for US social media audiences. "
        "Share interesting, verified financial statistics and facts that surprise and educate. "
        "Cite general well-known sources. Make numbers relatable to everyday life."
    ),
    Category.COMPARISON: (
        "You are a balanced finance content creator helping Americans make informed decisions. "
        "Compare financial options fairly, presenting pros and cons of each. "
        "Do NOT recommend one option over another — let the audience decide."
    ),
    Category.MYTH_BUSTING: (
        "You are a myth-busting finance educator for US social media. "
        "Debunk common financial myths with facts and clear explanations. "
        "Be conversational and slightly surprising to grab attention. "
        "Do NOT give personalized financial advice."
    ),
}

# Forbidden content patterns for compliance
FORBIDDEN_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(buy|sell|short)\s+(shares?|stock|stocks)\s+of\s+\w+", re.IGNORECASE),
    re.compile(r"\$[A-Z]{1,5}\b"),  # Stock tickers like $AAPL
    re.compile(r"guaranteed?\s+(returns?|profit|income)", re.IGNORECASE),
    re.compile(r"\d+%\s+(return|profit|gain)\s+(guaranteed|assured|certain)", re.IGNORECASE),
    re.compile(r"(will|going to)\s+(make|earn|get)\s+\d+%", re.IGNORECASE),
    re.compile(r"(can.t|cannot|won.t)\s+lose", re.IGNORECASE),
    re.compile(r"risk[- ]free\s+(investment|return|profit)", re.IGNORECASE),
    re.compile(r"(get rich quick|double your money|triple your)", re.IGNORECASE),
]


class ContentValidator:
    """Validates generated content for compliance with finance content rules."""

    @staticmethod
    def validate(content: PostContent) -> tuple[bool, list[str]]:
        """Validate content for compliance.

        Returns:
            Tuple of (is_valid, list_of_issues).
        """
        issues: list[str] = []

        full_text = f"{content.hook_text} {content.body_text}"

        for pattern in FORBIDDEN_PATTERNS:
            match = pattern.search(full_text)
            if match:
                issues.append(f"Forbidden content detected: '{match.group()}' matches compliance rule")

        if len(content.hook_text) < 10:
            issues.append(f"Hook text too short: {len(content.hook_text)} chars (min 10)")
        if len(content.hook_text) > 60:
            issues.append(f"Hook text too long: {len(content.hook_text)} chars (max 60)")
        if len(content.body_text) < 50:
            issues.append(f"Body text too short: {len(content.body_text)} chars (min 50)")
        if len(content.body_text) > 500:
            issues.append(f"Body text too long: {len(content.body_text)} chars (max 500)")
        if len(content.hashtags) > 5:
            issues.append(f"Too many hashtags: {len(content.hashtags)} (max 5)")

        return (len(issues) == 0, issues)


class ContentGenerator:
    """Generates finance content using Google Gemini (primary) and Groq (fallback).

    Both services are free tier:
    - Google Gemini: 15 RPM, 1M tokens/day (free from https://aistudio.google.com)
    - Groq: 30 RPM (free from https://console.groq.com)
    """

    def __init__(
        self,
        gemini_api_key: str,
        groq_api_key: str = "",
        rate_limiter: Optional[FreeTierRateLimiter] = None,
    ) -> None:
        self._gemini_api_key = gemini_api_key
        self._groq_api_key = groq_api_key
        self._rate_limiter = rate_limiter or FreeTierRateLimiter()
        self._validator = ContentValidator()

        # Initialize Gemini client
        self._gemini_model = None
        if gemini_api_key:
            try:
                import google.generativeai as genai

                genai.configure(api_key=gemini_api_key)
                self._gemini_model = genai.GenerativeModel("gemini-1.5-flash")
            except Exception as e:
                click.echo(f"  Warning: Could not initialize Gemini: {e}")

        # Initialize Groq client
        self._groq_client = None
        if groq_api_key:
            try:
                from groq import Groq

                self._groq_client = Groq(api_key=groq_api_key)
            except Exception as e:
                click.echo(f"  Warning: Could not initialize Groq: {e}")

    def generate_post(self, topic: str, category: Category) -> Optional[PostContent]:
        """Generate a complete post for the given topic and category.

        Tries Gemini first, falls back to Groq on rate limit.
        Retries up to 3 times with exponential backoff.

        Args:
            topic: The specific finance topic.
            category: The content category.

        Returns:
            PostContent if successful, None if all attempts fail.
        """
        service = self._rate_limiter.get_preferred_service()

        for attempt in range(3):
            try:
                if service == AIService.GEMINI:
                    content = self._generate_via_gemini(topic, category)
                else:
                    content = self._generate_via_groq(topic, category)

                if content:
                    # Validate content
                    is_valid, issues = self._validator.validate(content)
                    if is_valid:
                        return content
                    else:
                        click.echo(f"  Content validation failed: {issues}. Regenerating...")
                        # Try regenerating with feedback
                        content = self._regenerate_with_feedback(topic, category, issues, service)
                        if content:
                            is_valid2, _ = self._validator.validate(content)
                            if is_valid2:
                                return content

            except Exception as e:
                error_msg = str(e).lower()
                if "429" in error_msg or "rate" in error_msg:
                    # Rate limited - switch service
                    if service == AIService.GEMINI:
                        self._rate_limiter.mark_gemini_rate_limited()
                        service = AIService.GROQ
                    else:
                        self._rate_limiter.mark_groq_rate_limited()
                        service = AIService.GEMINI
                elif "quota" in error_msg:
                    self._rate_limiter.mark_gemini_quota_exhausted()
                    service = AIService.GROQ
                else:
                    click.echo(f"  Generation error (attempt {attempt + 1}/3): {e}")

                # Exponential backoff
                if attempt < 2:
                    wait = 2 ** (attempt + 1)
                    time.sleep(wait)

        click.echo(f"  Failed to generate content for topic: {topic}")
        return None

    def _build_user_prompt(self, topic: str, category: Category) -> str:
        """Build the user prompt for content generation."""
        return (
            f"Create a Facebook post about: {topic}\n\n"
            f"Category: {category.value}\n\n"
            "Respond in JSON format with these exact keys:\n"
            '- "hook_text": A short attention-grabbing headline (10-60 characters, no quotes)\n'
            '- "body_text": The full post caption (50-500 characters, engaging and informative)\n'
            '- "hashtags": A list of 3-5 relevant hashtags (without the # symbol)\n\n'
            "Rules:\n"
            "- Target US audience\n"
            "- Be conversational and engaging\n"
            "- No specific stock picks or ticker symbols\n"
            "- No guaranteed returns or misleading claims\n"
            "- Include a call-to-action or thought-provoking question\n"
            "- Keep it educational and positive\n\n"
            "Respond ONLY with valid JSON, no markdown formatting."
        )

    def _parse_ai_response(self, raw_text: str, topic: str, category: Category) -> Optional[PostContent]:
        """Parse AI response text into a PostContent object."""
        try:
            # Clean up response - remove markdown code blocks if present
            cleaned = raw_text.strip()
            if cleaned.startswith("```"):
                lines = cleaned.split("\n")
                # Remove first and last lines (```json and ```)
                lines = [l for l in lines if not l.strip().startswith("```")]
                cleaned = "\n".join(lines)

            data = json.loads(cleaned)

            hook_text = data.get("hook_text", "").strip()
            body_text = data.get("body_text", "").strip()
            hashtags = data.get("hashtags", [])

            # Truncate if needed
            if len(hook_text) > 60:
                hook_text = self._truncate_at_word(hook_text, 60)
            if len(body_text) > 500:
                body_text = self._truncate_at_word(body_text, 500)
            if len(hashtags) > 5:
                hashtags = hashtags[:5]

            # Ensure minimum lengths
            if len(hook_text) < 10:
                hook_text = hook_text + " " * (10 - len(hook_text))
            if len(body_text) < 50:
                body_text = body_text + " Learn more about personal finance!" * 2

            # Clean hashtags
            hashtags = [h.replace("#", "").strip() for h in hashtags if h.strip()]

            return PostContent(
                hook_text=hook_text[:60],
                body_text=body_text[:500],
                category=category,
                topic=topic,
                hashtags=hashtags[:5],
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            click.echo(f"  Failed to parse AI response: {e}")
            return None

    def _truncate_at_word(self, text: str, max_len: int) -> str:
        """Truncate text at a word boundary."""
        if len(text) <= max_len:
            return text
        truncated = text[:max_len]
        last_space = truncated.rfind(" ")
        if last_space > max_len // 2:
            return truncated[:last_space]
        return truncated

    def _generate_via_gemini(self, topic: str, category: Category) -> Optional[PostContent]:
        """Generate content using Google Gemini free tier."""
        if not self._gemini_model:
            raise RuntimeError("Gemini not initialized")

        self._rate_limiter.wait_for_gemini()

        system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS[Category.TIPS])
        user_prompt = self._build_user_prompt(topic, category)

        full_prompt = f"{system_prompt}\n\n{user_prompt}"

        response = self._gemini_model.generate_content(
            full_prompt,
            generation_config={
                "max_output_tokens": 300,
                "temperature": 0.8,
            },
        )

        # Record the call
        tokens_used = 0
        if hasattr(response, "usage_metadata") and response.usage_metadata:
            tokens_used = getattr(response.usage_metadata, "total_token_count", 300)
        self._rate_limiter.record_gemini_call(tokens_used or 300)

        if response and response.text:
            return self._parse_ai_response(response.text, topic, category)
        return None

    def _generate_via_groq(self, topic: str, category: Category) -> Optional[PostContent]:
        """Generate content using Groq free tier (fallback)."""
        if not self._groq_client:
            raise RuntimeError("Groq not initialized (set GROQ_API_KEY for fallback)")

        self._rate_limiter.wait_for_groq()

        system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS[Category.TIPS])
        user_prompt = self._build_user_prompt(topic, category)

        response = self._groq_client.chat.completions.create(
            model="llama-3.1-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=300,
            temperature=0.8,
        )

        self._rate_limiter.record_groq_call()

        if response and response.choices:
            raw_text = response.choices[0].message.content or ""
            return self._parse_ai_response(raw_text, topic, category)
        return None

    def _regenerate_with_feedback(
        self,
        topic: str,
        category: Category,
        issues: list[str],
        service: AIService,
    ) -> Optional[PostContent]:
        """Regenerate content incorporating validation feedback."""
        feedback = "\n".join(f"- {issue}" for issue in issues)
        modified_prompt = (
            f"Create a Facebook post about: {topic}\n\n"
            f"Category: {category.value}\n\n"
            f"IMPORTANT: Your previous attempt had these issues:\n{feedback}\n\n"
            "Please fix these issues. Respond in JSON format with:\n"
            '- "hook_text": A short headline (10-60 characters)\n'
            '- "body_text": Full caption (50-500 characters)\n'
            '- "hashtags": 3-5 relevant hashtags (without #)\n\n'
            "No stock picks, no guaranteed returns, no misleading claims.\n"
            "Respond ONLY with valid JSON."
        )

        try:
            if service == AIService.GEMINI and self._gemini_model:
                self._rate_limiter.wait_for_gemini()
                system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS[Category.TIPS])
                response = self._gemini_model.generate_content(
                    f"{system_prompt}\n\n{modified_prompt}",
                    generation_config={"max_output_tokens": 300, "temperature": 0.7},
                )
                self._rate_limiter.record_gemini_call(300)
                if response and response.text:
                    return self._parse_ai_response(response.text, topic, category)
            elif service == AIService.GROQ and self._groq_client:
                self._rate_limiter.wait_for_groq()
                system_prompt = SYSTEM_PROMPTS.get(category, SYSTEM_PROMPTS[Category.TIPS])
                response = self._groq_client.chat.completions.create(
                    model="llama-3.1-70b-versatile",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": modified_prompt},
                    ],
                    max_tokens=300,
                    temperature=0.7,
                )
                self._rate_limiter.record_groq_call()
                if response and response.choices:
                    raw_text = response.choices[0].message.content or ""
                    return self._parse_ai_response(raw_text, topic, category)
        except Exception as e:
            click.echo(f"  Regeneration failed: {e}")

        return None
