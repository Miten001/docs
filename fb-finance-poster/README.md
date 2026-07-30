# Facebook Finance Auto-Poster

## Yeh Tool Kya Hai? (What is this tool?)

Yeh ek **fully automated** content pipeline hai jo aapke Facebook page pe finance-related posts generate, design, aur schedule karta hai — **bilkul FREE mein** ($0/month).

This is a **fully automated** content pipeline that generates, designs, and schedules finance-related posts to your Facebook page — **completely FREE** ($0/month total cost).

### Key Features:
- **AI Content Generation**: Google Gemini free tier se engaging hooks aur educational finance content
- **AI Image Generation**: Pollinations.ai (bilkul free, koi API key nahi chahiye) se professional images
- **Text Overlay**: Pillow (open-source) se attractive text overlay
- **Auto Scheduling**: Facebook Graph API se optimal times pe scheduling
- **Bulk Scheduling**: Ek command se poora week ya month schedule karo (8-10 posts daily)
- **US Audience Optimized**: Best engagement times pe posts (Morning, Lunch, Evening)
- **$0 Total Cost**: Sab kuch free hai!

---

## Cost Summary / Kharcha Kitna?

| Service | Purpose | Cost |
|---------|---------|------|
| Google Gemini API | Text content generation | **FREE** (15 RPM, 1M tokens/day) |
| Pollinations.ai | Image generation | **FREE** (no API key, unlimited) |
| Facebook Graph API | Post scheduling | **FREE** (200 calls/hour) |
| Pillow (PIL) | Image processing | **FREE** (open-source) |
| Groq (optional fallback) | Backup text generation | **FREE** (30 RPM) |
| **Total** | | **$0/month** |

---

## Setup / Installation

### Step 1: Python Install Karo

Python 3.10+ required hai. Check karo:

```bash
python --version
```

### Step 2: Project Clone/Download Karo

```bash
cd fb-finance-poster
```

### Step 3: Dependencies Install Karo

```bash
pip install -e .
```

Ya development ke liye:

```bash
pip install -e ".[dev]"
```

### Step 4: FREE API Keys Lo

#### Google Gemini API Key (FREE):
1. https://aistudio.google.com pe jao
2. Google account se sign in karo
3. "Get API Key" click karo
4. New API key create karo
5. Copy karo — yeh **FREE** hai (15 requests/minute, 1M tokens/day)

#### Facebook Page Access Token (FREE):
1. https://developers.facebook.com pe jao
2. App create karo (ya existing use karo)
3. Graph API Explorer use karo: https://developers.facebook.com/tools/explorer/
4. Permissions select karo: `pages_manage_posts`, `pages_read_engagement`
5. Page Access Token generate karo
6. Long-lived token ke liye: Settings > Advanced > extend token

#### Groq API Key (Optional, FREE):
1. https://console.groq.com pe jao
2. Sign up karo
3. API Keys section mein new key create karo
4. Yeh backup hai jab Gemini rate-limited ho

### Step 5: Environment Variables Set Karo

`.env` file create karo project folder mein:

```bash
cp .env.example .env
```

Phir `.env` file edit karo:

```env
# Required (ALL FREE)
FB_PAGE_ID=your_facebook_page_id
FB_ACCESS_TOKEN=your_long_lived_page_access_token
GEMINI_API_KEY=your_gemini_api_key

# Optional (FREE)
GROQ_API_KEY=your_groq_api_key
POSTS_PER_DAY=10
OUTPUT_DIR=./output
TIMEZONE=America/New_York
```

---

## How to Use / Kaise Use Kare

### 1. Preview Posts (Bina Schedule Kiye)

Pehle dekho kaise posts generate hote hain:

```bash
fb-poster preview --count 5
```

### 2. Dry Run (Generate but Don't Schedule)

Full week ke posts generate karo, schedule mat karo:

```bash
fb-poster run --duration week --posts-per-day 10 --dry-run
```

### 3. Schedule One Week

Ek hafte ke posts generate aur schedule karo:

```bash
fb-poster run --duration week --posts-per-day 10
```

### 4. Schedule One Month

Ek mahine ke posts generate aur schedule karo:

```bash
fb-poster run --duration month --posts-per-day 9
```

### 5. Specific Categories

Sirf specific categories ke posts generate karo:

```bash
fb-poster run --duration week --posts-per-day 8 --categories TIPS,EDUCATIONAL,MOTIVATIONAL
```

### 6. Check Status

Scheduled posts ka status dekho:

```bash
fb-poster status
```

### 7. Cancel Posts

Kisi post ko cancel karo:

```bash
fb-poster cancel POST_ID_1 POST_ID_2
```

### 8. Resume Interrupted Run

Agar beech mein band ho gaya, wahi se continue karo:

```bash
fb-poster resume
```

---

## Examples / Udaharan

### Example 1: Quick Start (5 minutes mein shuru)

```bash
# 1. Install
pip install -e .

# 2. API keys set karo (.env file mein)
# 3. Preview dekho
fb-poster preview --count 3

# 4. Week schedule karo
fb-poster run --duration week --dry-run  # pehle dry-run
fb-poster run --duration week             # phir actual schedule
```

### Example 2: Full Month Automation

```bash
# 30 days * 10 posts/day = 300 posts, $0 cost
fb-poster run --duration month --posts-per-day 10

# Estimated time: 3-5 hours (rate limits ke wajah se)
# Cost: $0
```

### Example 3: Custom Output Directory

```bash
fb-poster run --duration week --output-dir ./january_content
fb-poster status --output-dir ./january_content
```

---

## Content Categories / Content ke Prakar

| Category | Description (Hindi) | Description (English) |
|----------|--------------------|-----------------------|
| TIPS | Financial tips aur tricks | Practical money-saving tips |
| NEWS_COMMENTARY | Market news pe commentary | Financial news commentary |
| EDUCATIONAL | Investing/saving sikho | Educational finance content |
| MOTIVATIONAL | Wealth-building motivation | Inspiring finance posts |
| STATS_FACTS | Interesting finance statistics | Financial facts and numbers |
| COMPARISON | Options ki tulna | Financial product comparisons |
| MYTH_BUSTING | Finance myths todna | Debunking money myths |

---

## Posting Schedule / Kab Post Hota Hai

US audience ke liye optimal times (EST):

| Time Window | Engagement Level | Posts |
|------------|-----------------|-------|
| 7:00-9:00 AM | High (Morning commute) | 2-3 |
| 11:30 AM-1:30 PM | Highest (Lunch break) | 3-4 |
| 5:00-7:00 PM | High (After work) | 2-3 |
| 8:00-10:00 PM | Medium (Evening) | 1-2 |

---

## Rate Limits / Speed Limits

Free tier ke limits automatically manage hote hain:

- **Gemini**: 15 requests/minute → Tool automatically 4 seconds gap rakhta hai
- **Groq** (fallback): 30 requests/minute → Jab Gemini rate-limited ho
- **Pollinations.ai**: Unlimited! (bas 60 second timeout per image)
- **Facebook**: 200 calls/hour → 1 second gap between calls

### Estimated Generation Times:

| Duration | Posts | Time | Cost |
|----------|-------|------|------|
| 1 week (10/day) | 70 | ~45-90 min | $0 |
| 1 week (8/day) | 56 | ~35-70 min | $0 |
| 1 month (10/day) | 300 | ~3-5 hours | $0 |
| 1 month (8/day) | 240 | ~2-4 hours | $0 |

---

## File Structure / Files Ka Structure

```
fb-finance-poster/
├── pyproject.toml          # Project config
├── .env.example            # Template for API keys
├── README.md               # This file
├── templates/              # Fallback template images
├── output/                 # Generated content (auto-created)
│   ├── images/             # Raw generated images
│   ├── final/              # Images with text overlay
│   ├── manifest.json       # All post details
│   ├── progress.json       # Resume support
│   └── topic_history.json  # Topic deduplication
└── src/
    └── fb_finance_poster/
        ├── __init__.py
        ├── cli.py              # CLI commands
        ├── config.py           # Configuration loading
        ├── models.py           # Data models
        ├── content_gen.py      # AI content generation
        ├── image_gen.py        # Pollinations.ai images
        ├── overlay.py          # Text overlay (Pillow)
        ├── scheduler.py        # Facebook scheduling
        ├── rate_limiter.py     # Rate limit management
        ├── orchestrator.py     # Pipeline coordination
        └── topic_selector.py   # Topic diversity
```

---

## Troubleshooting / Samasya Samadhan

### "GEMINI_API_KEY is required"
- `.env` file mein `GEMINI_API_KEY` set karo
- Free key lo: https://aistudio.google.com

### "FB_ACCESS_TOKEN is required"
- Yeh sirf scheduling ke liye chahiye
- `--dry-run` use karo bina token ke test karne ke liye
- Free token: https://developers.facebook.com/tools/explorer/

### Rate limit errors
- Automatically handle hota hai — tool Groq pe switch karta hai
- Agar dono rate-limited: tool wait karta hai aur resume karta hai

### Image generation slow
- Pollinations.ai free hai but thoda slow ho sakta hai (10-30 seconds per image)
- Timeout pe automatically simpler prompt try karta hai
- Last mein fallback gradient image use karta hai

### Interrupted run
- `fb-poster resume` use karo — wahi se start hoga jaha ruka tha
- Progress automatically save hoti hai har 10 posts pe

---

## Security / Suraksha

- API keys **KABHI** code mein hardcode mat karo
- `.env` file ko `.gitignore` mein add karo
- Keys console output mein masked dikhti hain (xxxx...xxxx)
- Generated content mein koi stock picks ya guaranteed returns nahi hote

---

## License

MIT License — Free to use, modify, and distribute.

---

## Summary

**Ek command. Ek week ka content. Zero cost.**

```bash
fb-poster run --duration week --posts-per-day 10
```

Bas itna hi karna hai. Baaki sab automatic hai! 🚀
