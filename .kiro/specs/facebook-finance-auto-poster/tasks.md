# Implementation Plan: Facebook Finance Auto-Poster

## Overview

This plan implements the Facebook Finance Auto-Poster as a Python CLI application using Click for CLI framework, OpenAI for text generation, DALL-E/Stable Diffusion for image generation, Pillow for text overlay composition, and the Facebook Graph API for post scheduling. The implementation follows an incremental approach: project setup and data models first, then core components (content generation, image generation, text overlay, scheduling), then orchestration and error recovery, and finally integration wiring.

## Tasks

- [ ] 1. Set up project structure, dependencies, and core data models
  - [ ] 1.1 Initialize Python project with pyproject.toml, install dependencies (click, openai, pillow, requests, python-dotenv, pydantic), create package directory structure (`src/fb_finance_poster/`), and set up pytest for testing
    - Create `src/fb_finance_poster/__init__.py`, `src/fb_finance_poster/cli.py`, `src/fb_finance_poster/models.py`, `src/fb_finance_poster/config.py`
    - Create `tests/` directory with `conftest.py`
    - Define pyproject.toml with all dependencies including `hypothesis` for property tests
    - _Requirements: 1.1_

  - [ ] 1.2 Implement core data models using Pydantic: `RunConfig`, `PostContent`, `SchedulablePost`, `ScheduleConfig`, `Category` enum, and `PostStatus` enum with all validation rules from the design
    - `Category` enum: TIPS, NEWS_COMMENTARY, EDUCATIONAL, MOTIVATIONAL, STATS_FACTS, COMPARISON, MYTH_BUSTING
    - `PostStatus` enum: PENDING, SCHEDULED, PUBLISHED, FAILED
    - `RunConfig`: validate posts_per_day in [1, 15], duration in {ONE_WEEK, ONE_MONTH}
    - `PostContent`: validate hook_text 10-60 chars, body_text 50-500 chars, hashtags max 5
    - `SchedulablePost`: validate scheduled_time is 10min-75days in the future
    - _Requirements: 1.2, 1.3, 2.2, 2.3, 2.4, 7.2, 7.3_

  - [ ]* 1.3 Write property tests for data model validation using Hypothesis
    - **Property 1: Configuration Validation Correctness** — Generate arbitrary RunConfig values and verify acceptance/rejection matches the rules
    - **Property 2: Content Structural Invariants** — Generate arbitrary PostContent and verify hook_text (10-60), body_text (50-500), hashtags (<=5) constraints
    - **Validates: Requirements 1.2, 1.3, 2.2, 2.3, 2.4**

  - [ ] 1.4 Implement configuration loading from environment variables and .env file using python-dotenv, with validation for required API keys and page credentials
    - Load FB_PAGE_ID, FB_ACCESS_TOKEN, OPENAI_API_KEY, IMAGE_API, SD_API_KEY, POSTS_PER_DAY, OUTPUT_DIR, TIMEZONE
    - Never expose tokens in logs or console output
    - _Requirements: 10.1, 10.2_

- [ ] 2. Implement Content Generator and Topic Selector
  - [ ] 2.1 Implement the `TopicSelector` class with weighted category selection, 7-day deduplication window, and under-represented category boosting
    - Maintain a history of used topics (loaded from local store)
    - Weight selection toward categories with fewer recent posts
    - Only select from configured `content_categories` list
    - Ensure minimum 3 distinct categories per day (or total posts if fewer than 3)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

  - [ ]* 2.2 Write property tests for topic selection
    - **Property 3: Topic Uniqueness Within 7-Day Window** — For any sequence of topic selections, no two topics in a 7-day window are identical
    - **Property 4: Daily Category Diversity** — For any day's posts, distinct categories >= min(3, total_posts_that_day)
    - **Property 5: Topic Category Membership** — Every selected topic belongs to the configured categories list
    - **Validates: Requirements 3.1, 3.3, 3.4**

  - [ ] 2.3 Implement the `ContentGenerator` class that calls OpenAI API with structured prompts to produce `PostContent` objects (hook_text, body_text, category, hashtags)
    - Build system prompts tailored to each category for US finance audience
    - Parse AI response into structured PostContent
    - Truncate hook_text at word boundary if >60 chars, body_text if >500 chars
    - Generate up to 5 relevant hashtags
    - Implement retry logic: up to 3 retries with exponential backoff (2s, 4s, 8s) on API failure
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ] 2.4 Implement the `ContentValidator` class that checks generated content for compliance: reject specific stock picks, return guarantees, or misleading financial claims
    - Pattern-match for forbidden content (stock tickers with buy/sell, percentage guarantees, "guaranteed returns")
    - If validation fails, trigger regeneration with feedback
    - _Requirements: 10.4_

  - [ ]* 2.5 Write property tests for content generation validation
    - **Property 22: Content Compliance Rejection** — Any content containing stock picks, return guarantees, or misleading claims is rejected by the validator
    - **Validates: Requirement 10.4**

- [ ] 3. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 4. Implement Image Generator
  - [ ] 4.1 Implement the `ImageGenerator` class with prompt building, API calls to DALL-E 3 (or Stable Diffusion), image downloading, and local storage
    - Build prompts with category-specific style keywords and "space for text overlay" specification
    - Include negative prompts to prevent inappropriate/misleading imagery
    - Request images at Facebook-recommended dimensions (1200x630 or 1080x1080)
    - Download and store generated images as JPEG/PNG, validate file size <10MB
    - _Requirements: 4.1, 4.2, 4.3, 10.5_

  - [ ] 4.2 Implement retry and fallback logic for image generation: retry up to 3 times with modified prompts, fall back to pre-made template images from a local library on exhaustion
    - On content policy violation: sanitize prompt keywords and retry
    - On other errors: retry with exponential backoff
    - After 3 failures: select a fallback template image from `templates/` directory
    - _Requirements: 4.4, 4.5, 9.4_

  - [ ]* 4.3 Write property tests for image generation
    - **Property 6: Image Output Compliance** — Any image produced has dimensions 1200x630 or 1080x1080, format JPEG/PNG, size <10MB
    - **Property 7: Image Prompt Construction** — For any category, the built prompt contains category-specific style keywords and text overlay space specification
    - **Property 23: Negative Prompt Inclusion** — Every image generation request includes negative prompt keywords
    - **Validates: Requirements 4.1, 4.2, 4.3, 10.5**

- [ ] 5. Implement Text Overlay Engine
  - [ ] 5.1 Implement the `TextOverlayEngine` class using Pillow: render hook_text onto images with semi-transparent background, ensure contrast ratio >=4.5:1, respect safe zones (max 1000px text width on 1200px image)
    - Calculate optimal font size based on text length and image dimensions
    - Apply semi-transparent dark background behind text for contrast
    - Center text within safe margins
    - Preserve original image file, produce new output image
    - Maintain same dimensions in output as input
    - _Requirements: 5.1, 5.2, 5.5, 5.6_

  - [ ] 5.2 Implement progressive font size reduction (down to minimum 16pt) and word-boundary truncation with ellipsis when text doesn't fit
    - Start at calculated default font size
    - Reduce progressively until text fits within safe zone or hits 16pt minimum
    - If still doesn't fit at 16pt: truncate at word boundary and append ellipsis
    - _Requirements: 5.3, 5.4_

  - [ ]* 5.3 Write property tests for text overlay engine
    - **Property 8: Text Overlay Contrast** — For any image and hook_text, rendered text has contrast ratio >=4.5:1
    - **Property 9: Text Overlay Safe Zones** — For any 1200px-wide image, text bounding box width <=1000px
    - **Property 10: Font Size Minimum Bound** — Font size never drops below 16pt
    - **Property 11: Overlay Non-Destructiveness** — Original image is unmodified; output has same dimensions as input
    - **Validates: Requirements 5.1, 5.2, 5.3, 5.5, 5.6**

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 7. Implement Post Scheduler and Optimal Time Calculator
  - [ ] 7.1 Implement the `OptimalTimeCalculator` that distributes posts across four US engagement windows (Morning 7-9 AM, Lunch 11:30-1:30 PM, After-work 5-7 PM, Evening 8-10 PM EST) with proportional weighting and random offsets
    - Allocate posts proportionally: Lunch (weight 1.0) > After-work (0.9) > Morning (0.8) > Evening (0.7)
    - Add random offset within each window to vary daily posting times
    - Enforce minimum 30-minute gap between consecutive posts; redistribute to adjacent windows if gap cannot be met
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5_

  - [ ]* 7.2 Write property tests for optimal time calculation
    - **Property 12: Schedule Within Engagement Windows** — Every scheduled time falls within one of the four EST engagement windows
    - **Property 13: Proportional Window Distribution** — Posts per window are proportional to weights (±1 tolerance)
    - **Property 14: Time Randomization Across Days** — Same window slot has different minute-level times on different days
    - **Property 15: Minimum 30-Minute Gap** — Any two consecutive same-day posts are >=30 minutes apart
    - **Validates: Requirements 6.1, 6.2, 6.3, 6.4**

  - [ ] 7.3 Implement the `PostScheduler` class that uploads images and messages to the Facebook Graph API with scheduled_publish_time, handles rate limits (HTTP 429 with pause), retries with exponential backoff (2s, 4s, 8s), and enforces 1-second pauses between API calls
    - Validate scheduled_time is 10min-75days in the future before each call
    - On HTTP 429: pause until rate limit window resets
    - On failure: retry up to 3 times with exponential backoff
    - After all retries fail: mark post as FAILED with error details
    - Report total scheduled, failed, and failure details
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 7.4 Write property tests for scheduling logic
    - **Property 16: Scheduling Time Bounds** — Every post's scheduled_time is >=10min and <=75 days in the future
    - **Property 17: Scheduling Report Accuracy** — scheduled_count + failed_count = total posts attempted
    - **Validates: Requirements 7.2, 7.3, 7.7**

- [ ] 8. Implement Bulk Orchestration Engine
  - [ ] 8.1 Implement the `Orchestrator` class that coordinates the full pipeline: calculate total posts (days * posts_per_day), loop through content generation → image generation → text overlay for each post, pause 2s every 5 posts for rate limiting, then assign optimal times and trigger scheduling
    - ONE_WEEK: generate exactly 7 * N posts
    - ONE_MONTH: generate exactly (days_in_month) * N posts
    - Support dry_run mode: generate all content/images without scheduling
    - _Requirements: 8.1, 8.2, 8.3, 1.4_

  - [ ] 8.2 Implement manifest file generation (JSON) that saves all post details, scheduled times, and status to the output directory upon completion, and implement summary report display (total generated, scheduled, failed)
    - Write manifest.json with full post details
    - Display summary to console on completion
    - _Requirements: 8.4, 8.5_

  - [ ]* 8.3 Write property tests for bulk orchestration
    - **Property 18: Bulk Generation Count Correctness** — For any valid config with duration D and posts_per_day N, exactly days_in_duration(D) * N posts are generated
    - **Property 19: Manifest Serialization Round-Trip** — Writing and reading manifest produces equivalent data
    - **Validates: Requirements 8.1, 8.2, 8.4**

- [ ] 9. Implement Error Recovery, Resilience, and Resume Support
  - [ ] 9.1 Implement error recovery flows: halt on expired token (HTTP 401) with progress save, halt on disk space exhaustion with partial report, skip individual content failures and continue, and implement local content store for resume capability
    - On token expiry: save all progress immediately, notify user to refresh token
    - On disk space: halt, report successful count, support resume
    - On individual post failure: log, skip, continue with remaining posts
    - Store generated content locally for resume command
    - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

  - [ ]* 9.2 Write property tests for resilience
    - **Property 20: Resilience Continuation** — When K posts fail content generation, orchestrator still attempts all remaining (total - K) posts
    - **Validates: Requirement 9.3**

- [ ] 10. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 11. Implement CLI Entry Point and Commands
  - [ ] 11.1 Implement the Click-based CLI with commands: `run` (bulk generate and schedule), `preview` (generate sample posts without scheduling), `status` (display scheduled post states), `cancel` (cancel specified post IDs), and `resume` (continue from saved progress)
    - `run` command: accepts --duration, --posts-per-day, --page-id, --dry-run, --output-dir, --categories
    - `preview` command: accepts --count to generate N sample posts
    - `status` command: reads manifest and displays current state
    - `cancel` command: accepts post IDs and cancels them via Facebook API
    - Validate all parameters before initiating pipeline
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7_

  - [ ] 11.2 Implement Facebook token permission validation (check for pages_manage_posts and pages_read_engagement permissions) before scheduling begins
    - Call Facebook debug_token endpoint to verify permissions
    - Halt with descriptive error if required permissions are missing
    - _Requirements: 10.3_

  - [ ]* 11.3 Write property tests for CLI validation and security
    - **Property 1: Configuration Validation Correctness** — CLI accepts valid configs and rejects invalid ones with descriptive errors
    - **Property 21: Token Secrecy** — No log output or console display ever contains the access token string
    - **Validates: Requirements 1.1, 1.2, 1.3, 10.2**

- [ ] 12. Wire all components together and implement end-to-end integration
  - [ ] 12.1 Wire the CLI commands to the Orchestrator, connect Orchestrator to ContentGenerator, ImageGenerator, TextOverlayEngine, and PostScheduler, ensuring the full pipeline executes end-to-end with proper error propagation and progress reporting
    - Ensure CLI → Orchestrator → Components flow works
    - Progress display during execution (post X of Y)
    - Proper error propagation from components to CLI output
    - _Requirements: 1.1, 8.1, 8.2, 8.5_

  - [ ]* 12.2 Write integration tests for the full pipeline using dry_run mode
    - Test full pipeline with mocked AI APIs
    - Verify manifest output correctness
    - Test resume after simulated failure
    - _Requirements: 8.1, 8.4, 9.5_

- [ ] 13. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document's 23 formal properties
- Unit tests validate specific examples and edge cases
- The implementation language is **Python** with Click, Pydantic, Pillow, OpenAI SDK, Requests, and Hypothesis
- All API keys are loaded from environment variables or `.env` files — never hardcoded

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["1.3", "2.1", "4.1", "5.1", "7.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "4.2", "5.2", "7.2"] },
    { "id": 4, "tasks": ["2.4", "4.3", "5.3", "7.3"] },
    { "id": 5, "tasks": ["2.5", "7.4", "8.1"] },
    { "id": 6, "tasks": ["8.2", "9.1"] },
    { "id": 7, "tasks": ["8.3", "9.2", "11.1"] },
    { "id": 8, "tasks": ["11.2", "11.3"] },
    { "id": 9, "tasks": ["12.1"] },
    { "id": 10, "tasks": ["12.2"] }
  ]
}
```
