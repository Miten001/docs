"""Topic selection with diversity enforcement and deduplication."""

from __future__ import annotations

import json
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from .models import Category


# Topic pools per category
TOPIC_POOLS: dict[Category, list[str]] = {
    Category.TIPS: [
        "Emergency fund building strategies",
        "Automating your savings",
        "The 50/30/20 budget rule",
        "Credit score improvement tips",
        "Reducing unnecessary subscriptions",
        "Cash back rewards maximization",
        "Negotiating lower bills",
        "Side income ideas for beginners",
        "Tax-advantaged accounts overview",
        "Dollar cost averaging explained",
        "The power of compound interest",
        "Smart grocery shopping on a budget",
        "Free financial tools everyone should use",
        "Setting up automatic bill payments",
        "How to track your net worth",
        "The envelope budgeting method",
        "When to use a credit card vs debit",
        "Building multiple income streams",
        "High-yield savings accounts",
        "Reducing food delivery spending",
        "How to negotiate a raise",
        "Starting a no-spend challenge",
        "Understanding your paycheck deductions",
        "Free ways to learn about finance",
        "Setting realistic financial goals",
    ],
    Category.NEWS_COMMENTARY: [
        "Federal Reserve interest rate impact",
        "Stock market volatility explained",
        "Housing market trends",
        "Inflation effects on savings",
        "Tech sector investment landscape",
        "Cryptocurrency regulation updates",
        "Global economic shifts",
        "Banking industry changes",
        "Consumer spending patterns",
        "Job market and wage growth",
        "Energy prices and your wallet",
        "Small business economic outlook",
        "Student loan policy changes",
        "Healthcare costs and planning",
        "Retail investor trends",
        "Bond market signals",
        "International trade impacts",
        "Insurance industry shifts",
        "Fintech innovation trends",
        "Recession indicators to watch",
    ],
    Category.EDUCATIONAL: [
        "What is an index fund",
        "Understanding ETFs vs mutual funds",
        "How the stock market works",
        "Basics of bonds and fixed income",
        "What is diversification",
        "Understanding market capitalization",
        "How dividends work",
        "Introduction to REITs",
        "What is a 401k match",
        "Roth IRA vs Traditional IRA",
        "Understanding expense ratios",
        "How inflation erodes purchasing power",
        "What is asset allocation",
        "Understanding P/E ratios",
        "How treasury bonds work",
        "What is a brokerage account",
        "Understanding risk tolerance",
        "How compound growth works over decades",
        "What is a target date fund",
        "Understanding capital gains tax",
        "How HSA accounts work",
        "What is dollar cost averaging",
        "Understanding market cycles",
        "How to read a stock chart basics",
        "What is the S&P 500",
    ],
    Category.MOTIVATIONAL: [
        "Start investing with just $10",
        "Your future self will thank you",
        "Small steps lead to big wealth",
        "Time in market beats timing the market",
        "Financial freedom is achievable",
        "Consistency beats perfection in saving",
        "Every millionaire started somewhere",
        "Your income is your greatest wealth tool",
        "Delayed gratification pays dividends",
        "Build wealth while you sleep",
        "Financial discipline is a superpower",
        "The best time to start was yesterday",
        "Progress over perfection in budgeting",
        "Wealth is built in decades not days",
        "Invest in yourself first",
        "The snowball effect of saving",
        "Believe in your financial journey",
        "Small sacrifices create big futures",
        "Your money mindset matters",
        "Financial literacy changes everything",
    ],
    Category.STATS_FACTS: [
        "Average American savings statistics",
        "Retirement savings by age benchmarks",
        "Historical stock market returns",
        "The rule of 72 explained",
        "How much compound interest grows $100",
        "Average credit card debt in America",
        "Percentage of Americans living paycheck to paycheck",
        "Historical inflation rates",
        "Average 401k balance by age",
        "How much you need to retire",
        "Cost of waiting to invest one year",
        "Average student loan debt statistics",
        "Millionaire statistics in America",
        "Average household spending breakdown",
        "Time to double money at different rates",
        "Social Security statistics",
        "Average net worth by age group",
        "Emergency fund statistics in US",
        "How much Americans spend on subscriptions",
        "Investment returns vs savings account returns",
    ],
    Category.COMPARISON: [
        "Renting vs buying a home",
        "Index funds vs actively managed funds",
        "High yield savings vs CDs",
        "401k vs IRA comparison",
        "Stocks vs bonds for beginners",
        "Credit union vs bank",
        "Term life vs whole life insurance",
        "Paying off debt vs investing",
        "New car vs used car financially",
        "Cash vs credit card spending",
        "Public vs private college costs",
        "Freelance vs full-time financially",
        "Urban vs suburban cost of living",
        "Traditional vs Roth retirement accounts",
        "Leasing vs buying a car",
    ],
    Category.MYTH_BUSTING: [
        "Myth: You need lots of money to invest",
        "Myth: Credit cards are always bad",
        "Myth: Renting is throwing money away",
        "Myth: You should always buy the cheapest option",
        "Myth: Rich people dont budget",
        "Myth: Investing is gambling",
        "Myth: You need a financial advisor to start",
        "Myth: Carrying a balance helps your credit",
        "Myth: More income equals more wealth",
        "Myth: Cash is always king",
        "Myth: Young people dont need to save for retirement",
        "Myth: All debt is bad debt",
        "Myth: You cant invest during a recession",
        "Myth: Budgeting means you cant enjoy life",
        "Myth: Gold is the safest investment",
    ],
}


class TopicSelector:
    """Selects unique, diverse topics for finance posts.

    Features:
    - 7-day deduplication window (no repeat topics within a week)
    - Weighted category selection (favors under-represented categories)
    - Ensures minimum 3 distinct categories per day
    - Persists history to local JSON file
    """

    def __init__(self, history_path: Optional[Path] = None) -> None:
        self._history_path = history_path
        self._history: list[dict] = []
        self._daily_categories: Counter[str] = Counter()
        self._current_day: Optional[str] = None

        if history_path and history_path.exists():
            self._load_history()

    def _load_history(self) -> None:
        """Load topic history from local JSON file."""
        try:
            if self._history_path and self._history_path.exists():
                data = json.loads(self._history_path.read_text())
                self._history = data.get("history", [])
        except (json.JSONDecodeError, OSError):
            self._history = []

    def _save_history(self) -> None:
        """Save topic history to local JSON file."""
        if self._history_path:
            self._history_path.parent.mkdir(parents=True, exist_ok=True)
            data = {"history": self._history}
            self._history_path.write_text(json.dumps(data, indent=2, default=str))

    def _get_recent_topics(self, days: int = 7) -> set[str]:
        """Get topics used within the last N days."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        recent: set[str] = set()
        for entry in self._history:
            entry_time = datetime.fromisoformat(entry["timestamp"])
            if entry_time >= cutoff:
                recent.add(entry["topic"])
        return recent

    def _get_category_usage(self) -> Counter[str]:
        """Get category usage counts from recent history."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        usage: Counter[str] = Counter()
        for entry in self._history:
            entry_time = datetime.fromisoformat(entry["timestamp"])
            if entry_time >= cutoff:
                usage[entry["category"]] += 1
        return usage

    def select_topic(
        self,
        categories: list[Category],
        day_index: Optional[int] = None,
    ) -> tuple[str, Category]:
        """Select a unique topic from the configured categories.

        Args:
            categories: List of enabled content categories.
            day_index: Optional day index for tracking daily diversity.

        Returns:
            Tuple of (topic_name, category).
        """
        # Track daily category usage for diversity
        day_key = str(day_index) if day_index is not None else datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._current_day != day_key:
            self._current_day = day_key
            self._daily_categories = Counter()

        recent_topics = self._get_recent_topics(days=7)
        category_usage = self._get_category_usage()

        # Weight categories: favor under-represented ones
        category_weights: list[tuple[Category, float]] = []
        for cat in categories:
            usage = category_usage.get(cat.value, 0)
            daily_usage = self._daily_categories.get(cat.value, 0)
            # Base weight + penalty for over-use
            weight = max(0.1, 10.0 - usage - daily_usage * 3)
            category_weights.append((cat, weight))

        # Ensure daily diversity: boost categories not yet used today
        if len(self._daily_categories) < 3:
            for i, (cat, weight) in enumerate(category_weights):
                if cat.value not in self._daily_categories:
                    category_weights[i] = (cat, weight * 3.0)

        # Select category using weighted random
        cats = [cw[0] for cw in category_weights]
        weights = [cw[1] for cw in category_weights]
        total_weight = sum(weights)
        if total_weight == 0:
            weights = [1.0] * len(weights)
            total_weight = len(weights)

        normalized_weights = [w / total_weight for w in weights]
        selected_category = random.choices(cats, weights=normalized_weights, k=1)[0]

        # Select topic from pool, avoiding recent ones
        pool = TOPIC_POOLS.get(selected_category, [])
        available_topics = [t for t in pool if t not in recent_topics]

        if not available_topics:
            # All topics in this category were recently used; try another category
            for cat in cats:
                if cat == selected_category:
                    continue
                pool = TOPIC_POOLS.get(cat, [])
                available_topics = [t for t in pool if t not in recent_topics]
                if available_topics:
                    selected_category = cat
                    break

        if not available_topics:
            # Extremely unlikely: all topics recently used. Reset and pick any.
            available_topics = TOPIC_POOLS.get(selected_category, ["General finance tip"])

        topic = random.choice(available_topics)

        # Record selection
        self._history.append({
            "topic": topic,
            "category": selected_category.value,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        self._daily_categories[selected_category.value] += 1
        self._save_history()

        return topic, selected_category

    def reset_daily(self) -> None:
        """Reset daily category counter (call at start of new day)."""
        self._daily_categories = Counter()
        self._current_day = None
