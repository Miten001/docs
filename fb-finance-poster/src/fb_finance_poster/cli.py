"""Click-based command-line interface for the Facebook Finance Auto-Poster.

Commands:
    run      Generate and schedule a week/month of finance posts.
    preview  Generate a few sample posts locally (no scheduling).
    status   Show the state of a previous run's scheduled posts.
    cancel   Cancel scheduled Facebook posts by id.
    resume   Continue an interrupted run from locally saved content.

Secrets are only ever read from the environment / .env — never printed.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import List, Optional

import click

from . import __version__
from .config import build_run_config, configure_logging
from .content_generator import (
    ContentGenerator,
    GeminiClient,
    GroqClient,
)
from .image_generator import ImageGenerator
from .models import Category, Duration, RunConfig, days_in_duration
from .orchestrator import MANIFEST_FILE, Orchestrator
from .rate_limiter import FreeTierRateLimiter
from .scheduler import (
    FacebookGraphClient,
    OptimalTimeCalculator,
    PostScheduler,
)
from .text_overlay import TextOverlayEngine

REQUIRED_FB_PERMISSIONS = ("pages_manage_posts", "pages_read_engagement")


def _echo(msg: str) -> None:
    click.echo(msg)


def _estimate_time(total_posts: int) -> str:
    """Human-readable estimate based on the Gemini 15 RPM free-tier limit."""
    low = max(1, round(total_posts * 0.7))
    high = max(2, round(total_posts * 1.3))
    return f"~{low}-{high} minutes (limited by free-tier rate limits)"


def _build_text_client(config: RunConfig):
    """Choose a text-generation client based on available free keys."""
    if config.gemini_api_key:
        return GeminiClient(config.gemini_api_key), (
            GroqClient(config.groq_api_key) if config.groq_api_key else None
        )
    if config.groq_api_key:
        # Gemini key absent: use Groq as the primary client.
        return GroqClient(config.groq_api_key), None
    return None, None


def _build_orchestrator(
    config: RunConfig, *, with_scheduler: bool
) -> Orchestrator:
    groq_available = bool(config.groq_api_key)
    rate_limiter = FreeTierRateLimiter(groq_available=groq_available)

    gemini_client, groq_client = _build_text_client(config)
    if gemini_client is None and groq_client is None:
        raise click.ClickException(
            "No text-generation API key found. Set GEMINI_API_KEY "
            "(free from https://aistudio.google.com) or GROQ_API_KEY in your "
            ".env file."
        )

    # If Gemini is primary, groq_client is the fallback; if Groq is primary
    # (no Gemini key), route it through the gemini_client slot.
    from .content_generator import GeminiClient as _GC

    if isinstance(gemini_client, _GC):
        content_generator = ContentGenerator(
            rate_limiter=rate_limiter,
            gemini_client=gemini_client,
            groq_client=groq_client,
        )
    else:
        content_generator = ContentGenerator(
            rate_limiter=rate_limiter,
            gemini_client=None,
            groq_client=gemini_client,  # Groq acting as sole provider
        )

    image_generator = ImageGenerator(config.output_path())
    overlay_engine = TextOverlayEngine()

    scheduler = None
    if with_scheduler and not config.dry_run:
        scheduler = PostScheduler(
            client=FacebookGraphClient(),
            page_id=config.page_id,
            access_token=config.access_token,
        )

    return Orchestrator(
        config,
        rate_limiter=rate_limiter,
        content_generator=content_generator,
        image_generator=image_generator,
        overlay_engine=overlay_engine,
        scheduler=scheduler,
        time_calculator=OptimalTimeCalculator(timezone=config.timezone),
        progress_fn=_echo,
    )


def validate_fb_permissions(client, token: str) -> None:
    """Raise a ClickException if the token lacks required FB permissions."""
    try:
        data = client.debug_token(token)
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(
            f"Could not validate Facebook token permissions: {exc}"
        ) from exc
    scopes = set(data.get("scopes", []))
    missing = [p for p in REQUIRED_FB_PERMISSIONS if p not in scopes]
    if missing:
        raise click.ClickException(
            "Facebook token is missing required permissions: "
            + ", ".join(missing)
            + ". Grant pages_manage_posts and pages_read_engagement."
        )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="fb-finance-poster")
@click.option("--verbose", is_flag=True, help="Enable verbose logging.")
def cli(verbose: bool) -> None:
    """Facebook Finance Auto-Poster — generate & schedule posts for $0."""
    configure_logging(logging.DEBUG if verbose else logging.INFO)


@cli.command()
@click.option(
    "--duration",
    type=click.Choice([d.value for d in Duration]),
    default=Duration.ONE_WEEK.value,
    help="How much content to generate.",
)
@click.option(
    "--posts-per-day", type=int, default=None, help="Posts per day (1-15)."
)
@click.option("--page-id", default=None, help="Facebook Page ID.")
@click.option(
    "--dry-run", is_flag=True, help="Generate content/images without scheduling."
)
@click.option("--output-dir", default=None, help="Output directory.")
@click.option(
    "--categories",
    default=None,
    help="Comma-separated categories (default: all).",
)
def run(
    duration: str,
    posts_per_day: Optional[int],
    page_id: Optional[str],
    dry_run: bool,
    output_dir: Optional[str],
    categories: Optional[str],
) -> None:
    """Generate and schedule a full week or month of finance posts."""
    try:
        config = build_run_config(
            duration=duration,
            posts_per_day=posts_per_day,
            page_id=page_id,
            dry_run=dry_run,
            output_dir=output_dir,
            categories=categories,
        )
    except (ValueError, Exception) as exc:  # noqa: BLE001
        raise click.ClickException(str(exc))

    total = days_in_duration(config.duration) * config.posts_per_day
    _echo(f"Planning {total} posts ({config.duration.value}, "
          f"{config.posts_per_day}/day).")
    _echo(f"Estimated generation time: {_estimate_time(total)}")
    _echo("Total cost: $0 (all services are free).")

    orchestrator = _build_orchestrator(config, with_scheduler=not dry_run)

    # Validate Facebook permissions before scheduling (live runs only).
    if not dry_run and orchestrator.scheduler is not None:
        validate_fb_permissions(
            orchestrator.scheduler.client, config.access_token
        )

    result = orchestrator.run()
    if result.failed and not result.dry_run:
        sys.exit(1)


@cli.command()
@click.option("--count", type=int, default=3, help="Number of sample posts.")
@click.option("--output-dir", default=None, help="Output directory.")
@click.option("--categories", default=None, help="Comma-separated categories.")
def preview(count: int, output_dir: Optional[str], categories: Optional[str]) -> None:
    """Generate a few sample posts locally without scheduling."""
    if count < 1:
        raise click.ClickException("--count must be at least 1")

    # Preview always runs as a dry run.
    config = build_run_config(
        duration=Duration.ONE_WEEK.value,
        posts_per_day=min(count, 15),
        dry_run=True,
        output_dir=output_dir,
        categories=categories,
    )
    orchestrator = _build_orchestrator(config, with_scheduler=False)

    _echo(f"Generating {count} preview post(s)...")
    # Generate exactly `count` posts by iterating the pipeline directly.
    from .content_generator import ContentGenerationError

    shown = 0
    while shown < count:
        topic = orchestrator.topic_selector.select()
        try:
            content = orchestrator.content_generator.generate(topic)
        except ContentGenerationError as exc:
            _echo(f"  (skipped a post: {exc})")
            continue
        shown += 1
        _echo("-" * 40)
        _echo(f"  [{content.category.value}] {content.topic}")
        _echo(f"  HOOK : {content.hook_text}")
        _echo(f"  BODY : {content.body_text}")
        _echo(f"  TAGS : {' '.join(content.hashtags)}")
    _echo("-" * 40)
    _echo("Total cost: $0")


@cli.command()
@click.option("--output-dir", default="./output", help="Output directory.")
def status(output_dir: str) -> None:
    """Display the state of scheduled posts from a previous run."""
    manifest_path = Path(output_dir) / MANIFEST_FILE
    if not manifest_path.exists():
        raise click.ClickException(
            f"No manifest found at {manifest_path}. Run a generation first."
        )
    manifest = json.loads(manifest_path.read_text())
    _echo(f"Run: {manifest.get('duration')} "
          f"({manifest.get('posts_per_day')}/day)")
    _echo(f"  Generated : {manifest.get('generated')}")
    _echo(f"  Scheduled : {manifest.get('scheduled')}")
    _echo(f"  Failed    : {manifest.get('failed')}")
    _echo(f"  Cost      : {manifest.get('total_cost', '$0')}")
    _echo("")
    counts: dict = {}
    for post in manifest.get("posts", []):
        counts[post["status"]] = counts.get(post["status"], 0) + 1
    for stat, n in sorted(counts.items()):
        _echo(f"  {stat:<10}: {n}")


@cli.command()
@click.option(
    "--post-ids",
    required=True,
    help="Comma-separated Facebook post IDs to cancel.",
)
@click.option("--page-id", default=None, help="Facebook Page ID.")
def cancel(post_ids: str, page_id: Optional[str]) -> None:
    """Cancel scheduled Facebook posts by id."""
    ids: List[str] = [p.strip() for p in post_ids.split(",") if p.strip()]
    if not ids:
        raise click.ClickException("No post IDs provided.")
    config = build_run_config(page_id=page_id)
    if not config.access_token:
        raise click.ClickException("FB_ACCESS_TOKEN is required to cancel posts.")
    scheduler = PostScheduler(
        client=FacebookGraphClient(),
        page_id=config.page_id,
        access_token=config.access_token,
    )
    results = scheduler.cancel(ids)
    for pid, outcome in results.items():
        _echo(f"  {pid}: {outcome}")


@cli.command()
@click.option("--output-dir", default="./output", help="Output directory.")
@click.option("--page-id", default=None, help="Facebook Page ID.")
@click.option("--dry-run", is_flag=True, help="Resume in dry-run mode.")
def resume(output_dir: str, page_id: Optional[str], dry_run: bool) -> None:
    """Resume an interrupted run using locally saved content."""
    config = build_run_config(
        page_id=page_id, output_dir=output_dir, dry_run=dry_run
    )
    orchestrator = _build_orchestrator(config, with_scheduler=not dry_run)
    if not dry_run and orchestrator.scheduler is not None:
        validate_fb_permissions(
            orchestrator.scheduler.client, config.access_token
        )
    _echo("Resuming previous run...")
    result = orchestrator.run(resume=True)
    if result.failed and not result.dry_run:
        sys.exit(1)


def main() -> None:  # pragma: no cover
    cli()


if __name__ == "__main__":  # pragma: no cover
    cli()
