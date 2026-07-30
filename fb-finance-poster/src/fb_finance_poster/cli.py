"""Click CLI for the Facebook Finance Auto-Poster."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional, Tuple

import click

from .config import load_config, mask_secret, validate_config
from .models import Duration, RunConfig


@click.group()
@click.version_option(version="1.0.0", prog_name="fb-poster")
def cli() -> None:
    """Facebook Finance Auto-Poster - FREE automated content pipeline ($0/month).

    Generate, design, and schedule finance posts to your Facebook page
    using Google Gemini (free), Pollinations.ai (free), Pillow (free),
    and the Facebook Graph API (free).
    """
    pass


@cli.command()
@click.option(
    "--duration",
    type=click.Choice(["week", "month"]),
    default="week",
    help="Scheduling duration (week=7 days, month=30 days).",
)
@click.option(
    "--posts-per-day",
    type=int,
    default=None,
    help="Posts per day (1-15, default from env or 10).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Generate content without scheduling to Facebook.",
)
@click.option(
    "--output-dir",
    type=str,
    default=None,
    help="Output directory for generated content.",
)
@click.option(
    "--env-file",
    type=str,
    default=None,
    help="Path to .env file with API keys.",
)
@click.option(
    "--categories",
    type=str,
    default=None,
    help="Comma-separated categories (e.g., TIPS,EDUCATIONAL,MOTIVATIONAL).",
)
def run(
    duration: str,
    posts_per_day: Optional[int],
    dry_run: bool,
    output_dir: Optional[str],
    env_file: Optional[str],
    categories: Optional[str],
) -> None:
    """Generate and schedule finance posts in bulk.

    Examples:
        fb-poster run --duration week --posts-per-day 10
        fb-poster run --duration month --dry-run
        fb-poster run --duration week --posts-per-day 8 --categories TIPS,EDUCATIONAL
    """
    # Parse categories
    cat_list = None
    if categories:
        cat_list = [c.strip() for c in categories.split(",")]

    # Load config
    config = load_config(
        env_file=env_file,
        duration=duration,
        posts_per_day=posts_per_day,
        dry_run=dry_run,
        output_dir=output_dir,
        categories=cat_list,
    )

    # Validate
    errors = validate_config(config)
    if errors:
        click.echo("\nConfiguration errors:")
        for error in errors:
            click.echo(f"  - {error}")
        click.echo("\nPlease fix the above issues and try again.")
        click.echo("All API keys are FREE:")
        click.echo("  - Gemini: https://aistudio.google.com")
        click.echo("  - Groq (optional): https://console.groq.com")
        click.echo("  - Facebook: https://developers.facebook.com")
        sys.exit(1)

    # Display config (masked secrets)
    click.echo("\nConfiguration:")
    click.echo(f"  Duration:      {config.duration.value}")
    click.echo(f"  Posts/day:     {config.posts_per_day}")
    click.echo(f"  Dry run:       {config.dry_run}")
    click.echo(f"  Output:        {config.output_dir}")
    click.echo(f"  Gemini key:    {mask_secret(config.gemini_api_key)}")
    click.echo(f"  Groq key:      {mask_secret(config.groq_api_key)}")
    click.echo(f"  FB Page ID:    {mask_secret(config.page_id)}")
    click.echo(f"  Categories:    {len(config.content_categories)}")
    click.echo(f"  Total cost:    $0")

    # Estimate time
    from .orchestrator import get_total_days
    total_days = get_total_days(config.duration)
    total_posts = total_days * config.posts_per_day
    est_minutes = max(1, (total_posts * 5) // 60)
    click.echo(f"\n  Estimated: {total_posts} posts in ~{est_minutes} minutes at $0 cost")

    if not dry_run:
        click.confirm("\n  Proceed with generation and scheduling?", abort=True)

    # Run pipeline
    from .orchestrator import Orchestrator
    orchestrator = Orchestrator(config)
    result = orchestrator.run()

    if result.total_failed > 0:
        sys.exit(1)


@cli.command()
@click.option("--count", type=int, default=3, help="Number of sample posts to generate.")
@click.option("--env-file", type=str, default=None, help="Path to .env file.")
def preview(count: int, env_file: Optional[str]) -> None:
    """Generate sample posts without scheduling (preview mode).

    Examples:
        fb-poster preview --count 5
        fb-poster preview
    """
    config = load_config(env_file=env_file, dry_run=True, posts_per_day=count)
    config.duration = Duration.ONE_WEEK  # Minimal duration
    config.posts_per_day = max(1, min(count, 15))

    errors = validate_config(config)
    if errors:
        click.echo("Configuration errors:")
        for error in errors:
            click.echo(f"  - {error}")
        sys.exit(1)

    click.echo(f"\nGenerating {count} preview posts (not scheduling)...\n")

    from .orchestrator import Orchestrator
    # Override to just generate 'count' posts
    config.dry_run = True
    orchestrator = Orchestrator(config)

    posts = orchestrator._generate_all_posts(count, 1)

    click.echo(f"\n{'='*60}")
    click.echo(f"  PREVIEW: {len(posts)} posts generated")
    click.echo(f"{'='*60}\n")

    for i, post in enumerate(posts, 1):
        click.echo(f"  Post {i}:")
        click.echo(f"    Category: {post.content.category.value}")
        click.echo(f"    Topic:    {post.content.topic}")
        click.echo(f"    Hook:     \"{post.content.hook_text}\"")
        click.echo(f"    Body:     {post.content.body_text[:100]}...")
        click.echo(f"    Hashtags: {', '.join('#' + h for h in post.content.hashtags)}")
        click.echo(f"    Image:    {post.image_path}")
        click.echo("")

    click.echo(f"  Total cost: $0")


@cli.command()
@click.option("--output-dir", type=str, default="./output", help="Output directory to check.")
def status(output_dir: str) -> None:
    """Display the current state of scheduled posts from manifest.

    Examples:
        fb-poster status
        fb-poster status --output-dir ./my_output
    """
    manifest_path = Path(output_dir) / "manifest.json"

    if not manifest_path.exists():
        click.echo(f"  No manifest found at {manifest_path}")
        click.echo("  Run 'fb-poster run' first to generate content.")
        return

    try:
        data = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        click.echo(f"  Error reading manifest: {e}")
        return

    posts = data.get("posts", [])
    config_info = data.get("config", {})

    click.echo(f"\n{'='*60}")
    click.echo(f"  SCHEDULE STATUS")
    click.echo(f"{'='*60}")
    click.echo(f"  Generated at:  {data.get('generated_at', 'unknown')}")
    click.echo(f"  Duration:      {config_info.get('duration', 'unknown')}")
    click.echo(f"  Posts/day:     {config_info.get('posts_per_day', 'unknown')}")
    click.echo(f"  Total cost:    {config_info.get('total_cost', '$0')}")
    click.echo(f"  Total posts:   {len(posts)}")

    # Count by status
    from collections import Counter
    status_counts = Counter(p.get("status", "UNKNOWN") for p in posts)
    click.echo(f"\n  Status breakdown:")
    for s, count in sorted(status_counts.items()):
        click.echo(f"    {s}: {count}")

    # Show next few scheduled posts
    scheduled = [p for p in posts if p.get("status") == "SCHEDULED"]
    if scheduled:
        click.echo(f"\n  Next scheduled posts:")
        for p in sorted(scheduled, key=lambda x: x.get("scheduled_time", ""))[:5]:
            click.echo(f"    {p.get('scheduled_time', '?')} - \"{p.get('hook_text', '?')}\"")

    click.echo(f"\n{'='*60}\n")


@cli.command()
@click.argument("post_ids", nargs=-1, required=True)
@click.option("--env-file", type=str, default=None, help="Path to .env file.")
def cancel(post_ids: tuple, env_file: Optional[str]) -> None:
    """Cancel scheduled posts on Facebook by their IDs.

    Examples:
        fb-poster cancel POST_ID_1 POST_ID_2
    """
    config = load_config(env_file=env_file)

    if not config.page_id or not config.access_token:
        click.echo("  Error: FB_PAGE_ID and FB_ACCESS_TOKEN required for cancellation.")
        sys.exit(1)

    from .scheduler import PostScheduler
    scheduler = PostScheduler(page_id=config.page_id, access_token=config.access_token)

    click.echo(f"\n  Cancelling {len(post_ids)} post(s)...\n")

    cancelled = 0
    for pid in post_ids:
        success = scheduler.cancel_post(pid)
        if success:
            click.echo(f"    Cancelled: {pid}")
            cancelled += 1
        else:
            click.echo(f"    Failed:    {pid}")

    click.echo(f"\n  Result: {cancelled}/{len(post_ids)} cancelled successfully.\n")


@cli.command()
@click.option("--output-dir", type=str, default="./output", help="Output directory with progress.")
@click.option("--env-file", type=str, default=None, help="Path to .env file.")
def resume(output_dir: str, env_file: Optional[str]) -> None:
    """Resume a previously interrupted generation/scheduling run.

    Reads progress from the output directory and continues where it left off.

    Examples:
        fb-poster resume
        fb-poster resume --output-dir ./my_output
    """
    config = load_config(env_file=env_file, output_dir=output_dir)

    errors = validate_config(config)
    if errors:
        click.echo("Configuration errors:")
        for error in errors:
            click.echo(f"  - {error}")
        sys.exit(1)

    click.echo(f"\n  Resuming from {output_dir}...")

    from .orchestrator import resume_from_progress
    result = resume_from_progress(config)

    if result is None:
        click.echo("  No progress to resume. Use 'fb-poster run' to start fresh.")
        sys.exit(1)


if __name__ == "__main__":
    cli()
