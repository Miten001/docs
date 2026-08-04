# Facebook Finance Auto-Poster

Generate, design, and schedule an entire week or month of finance-themed
Facebook posts with a single command — **entirely for free ($0/month)**.

The tool orchestrates only free-tier services:

| Service | Purpose | Cost |
|---------|---------|------|
| Google Gemini (`gemini-1.5-flash`) | Text content generation (primary) | **FREE** — 15 RPM, 1M tokens/day |
| Groq (`llama-3.1-70b-versatile`) | Text content generation (fallback) | **FREE** — optional |
| Pollinations.ai | Image generation (no API key!) | **FREE** — unlimited |
| Pillow (PIL) | Text-overlay composition | **FREE** — open source |
| Facebook Graph API | Post scheduling | **FREE** — 200 calls/hour |
| | **Total** | **$0/month** |

## How it works

```
CLI → Orchestrator → ContentGenerator (Gemini/Groq)
                   → ImageGenerator   (Pollinations.ai)
                   → TextOverlayEngine (Pillow)
                   → PostScheduler    (Facebook Graph API)
```

For each post the pipeline picks a unique topic, writes an engaging hook +
body caption, generates a finance-themed background image, overlays the hook
text, assigns an optimal US-audience posting time, and (unless `--dry-run`)
schedules it on your Facebook page.

## Where to get the free API keys

| Service | Where | Cost | Limits |
|---------|-------|------|--------|
| Google Gemini | https://aistudio.google.com | FREE | 15 RPM, 1M tokens/day |
| Groq (optional fallback) | https://console.groq.com | FREE | ~30 RPM |
| Pollinations.ai | *no key needed* | FREE | unlimited |
| Facebook Graph API | https://developers.facebook.com | FREE | 200 calls/hour |

## Installation

```bash
cd fb-finance-poster
python -m venv .venv
source .venv/bin/activate

# install the package (add [dev] for the test dependencies)
pip install -e ".[dev]"
```

## Configuration

```bash
cp .env.example .env
# then edit .env and fill in FB_PAGE_ID, FB_ACCESS_TOKEN, GEMINI_API_KEY
```

The tool loads all secrets from environment variables / `.env`. Tokens and API
keys are **never** printed to the console or written to logs.

## Usage

```bash
# Verify the CLI is installed
fb-finance-poster --help
# or, without installing the console script:
python -m fb_finance_poster.cli --help

# Preview 5 sample posts locally (no scheduling, no Facebook needed)
fb-finance-poster preview --count 5

# Dry run: generate a full week of content & images but DON'T schedule
fb-finance-poster run --duration ONE_WEEK --posts-per-day 10 --dry-run

# The real thing: generate + schedule a week of posts to your page
fb-finance-poster run --duration ONE_WEEK --posts-per-day 10 --page-id 123456789

# Schedule a whole month
fb-finance-poster run --duration ONE_MONTH --posts-per-day 9

# Check the status of a previous run
fb-finance-poster status --output-dir ./output

# Resume an interrupted run (re-uses locally saved content)
fb-finance-poster resume --output-dir ./output

# Cancel scheduled posts
fb-finance-poster cancel --post-ids 123_456,123_789
```

### `run` options

| Option | Description | Default |
|--------|-------------|---------|
| `--duration` | `ONE_WEEK` or `ONE_MONTH` | `ONE_WEEK` |
| `--posts-per-day` | Posts per day (1–15) | `10` (or `POSTS_PER_DAY`) |
| `--page-id` | Facebook Page ID | `FB_PAGE_ID` |
| `--dry-run` | Generate content/images without scheduling | off |
| `--output-dir` | Where images + manifest are written | `./output` |
| `--categories` | Comma-separated categories to enable | all |

Available categories: `TIPS, NEWS_COMMENTARY, EDUCATIONAL, MOTIVATIONAL,
STATS_FACTS, COMPARISON, MYTH_BUSTING`.

## Estimated generation time (free-tier limited)

| Duration | Posts | Approx. time | Cost |
|----------|-------|--------------|------|
| 1 week   | ~70   | 45–90 min    | $0 |
| 1 month  | ~270  | 3–5 hours    | $0 |

Times are limited by the Gemini free-tier rate limit (15 RPM). Everything runs
at **$0 cost**.

## Testing

```bash
pip install -e ".[dev]"
pytest -q          # runs the dry-run smoke test (no network / no keys needed)
```

## License

MIT
