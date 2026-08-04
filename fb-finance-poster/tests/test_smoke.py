"""Dry-run smoke test for the full pipeline with all external APIs mocked.

No network access and no API keys are required to run this test.
"""

from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from PIL import Image

from fb_finance_poster.content_generator import ContentGenerator, TopicSelector
from fb_finance_poster.image_generator import ImageGenerator
from fb_finance_poster.models import Category, Duration, RunConfig, days_in_duration
from fb_finance_poster.orchestrator import MANIFEST_FILE, Orchestrator
from fb_finance_poster.rate_limiter import FreeTierRateLimiter
from fb_finance_poster.scheduler import OptimalTimeCalculator
from fb_finance_poster.text_overlay import TextOverlayEngine


class FakeTextClient:
    """Returns deterministic, valid JSON content — no network."""

    def __init__(self) -> None:
        self.calls = 0

    def generate(self, system_prompt: str, user_prompt: str):
        self.calls += 1
        payload = {
            "hook_text": "Grow your savings the smart way",
            "body_text": (
                "Small, consistent habits build real wealth over time. "
                "Automate your savings, review your budget monthly, and stay "
                "the course. Education beats hype every single time."
            ),
            "hashtags": ["finance", "money", "savings", "budgeting"],
        }
        return json.dumps(payload), 120


def _png_bytes(width: int = 1200, height: int = 630) -> bytes:
    img = Image.new("RGB", (width, height), (20, 60, 110))
    buf = BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def fake_downloader(url: str, timeout: int) -> bytes:
    assert "image.pollinations.ai" in url
    assert "width=1200" in url and "height=630" in url
    return _png_bytes()


def _build_orchestrator(config: RunConfig, tmp_path: Path) -> Orchestrator:
    no_sleep = lambda *_a, **_k: None
    rate_limiter = FreeTierRateLimiter(sleep_fn=no_sleep, time_fn=lambda: 0.0)
    content_generator = ContentGenerator(
        rate_limiter=rate_limiter,
        gemini_client=FakeTextClient(),
        groq_client=None,
        sleep_fn=no_sleep,
    )
    image_generator = ImageGenerator(
        config.output_path(), downloader=fake_downloader, sleep_fn=no_sleep
    )
    return Orchestrator(
        config,
        rate_limiter=rate_limiter,
        content_generator=content_generator,
        image_generator=image_generator,
        overlay_engine=TextOverlayEngine(),
        scheduler=None,  # dry run
        time_calculator=OptimalTimeCalculator(timezone=config.timezone),
        topic_selector=TopicSelector(config.content_categories),
        progress_fn=lambda _m: None,
    )


def test_dry_run_pipeline_produces_expected_posts(tmp_path):
    posts_per_day = 2
    config = RunConfig(
        duration=Duration.ONE_WEEK,
        posts_per_day=posts_per_day,
        dry_run=True,
        output_dir=str(tmp_path / "output"),
        content_categories=[
            Category.TIPS,
            Category.EDUCATIONAL,
            Category.MOTIVATIONAL,
            Category.STATS_FACTS,
        ],
    )
    orchestrator = _build_orchestrator(config, tmp_path)
    expected = days_in_duration(Duration.ONE_WEEK) * posts_per_day  # 14

    result = orchestrator.run()

    # Correct number of posts generated.
    assert result.total == expected
    assert result.generated == expected
    assert result.dry_run is True
    assert result.scheduled == 0

    # Manifest written with all posts.
    manifest_path = Path(config.output_dir) / MANIFEST_FILE
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert manifest["total"] == expected
    assert len(manifest["posts"]) == expected
    assert manifest["total_cost"] == "$0"

    # Every post has a valid hook, body, image, and scheduled time.
    for post in manifest["posts"]:
        assert 10 <= len(post["hook_text"]) <= 60
        assert 50 <= len(post["body_text"]) <= 500
        assert len(post["hashtags"]) <= 5
        assert post["image_path"] is not None
        assert Path(post["image_path"]).exists()
        assert post["scheduled_time"] is not None


def test_generated_images_have_correct_dimensions(tmp_path):
    config = RunConfig(
        duration=Duration.ONE_WEEK,
        posts_per_day=1,
        dry_run=True,
        output_dir=str(tmp_path / "output"),
        content_categories=[Category.TIPS],
    )
    orchestrator = _build_orchestrator(config, tmp_path)
    result = orchestrator.run()

    manifest = json.loads(
        (Path(config.output_dir) / MANIFEST_FILE).read_text()
    )
    assert result.generated == 7
    with Image.open(manifest["posts"][0]["image_path"]) as img:
        assert img.size == (1200, 630)


def test_optimal_times_respect_min_gap(tmp_path):
    from datetime import date

    calc = OptimalTimeCalculator(timezone="America/New_York")
    times = calc.calculate(date(2030, 1, 1), total_days=3, posts_per_day=6)
    assert len(times) == 18
    # Group by day and verify 30-minute minimum gap.
    from itertools import groupby

    for _day, day_times in groupby(times, key=lambda t: t.date()):
        day_times = list(day_times)
        for earlier, later in zip(day_times, day_times[1:]):
            assert (later - earlier).total_seconds() >= 30 * 60
