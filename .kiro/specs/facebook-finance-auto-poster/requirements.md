# Requirements Document

## Introduction

The Facebook Finance Auto-Poster is an automated content pipeline that generates, designs, and schedules finance-related posts to Facebook pages. The system leverages AI for text content generation (engaging hooks and educational finance content tailored for US audiences) and image generation (high-engagement visuals with text overlays). It supports bulk scheduling — allowing a single script execution to schedule an entire week or month of content (8-10 posts daily) at optimal engagement times for US-based audiences. The system is designed as a CLI-driven automation tool that orchestrates OpenAI for text, DALL-E/Stable Diffusion for images, an image processing pipeline for text overlay composition, and the Facebook Graph API for post scheduling.

## Glossary

- **System**: The Facebook Finance Auto-Poster application as a whole
- **CLI**: The Command-Line Interface entry point for user interaction
- **Orchestrator**: The central engine coordinating content generation, image creation, overlay application, and scheduling
- **Content_Generator**: The component responsible for generating finance-related text content using AI
- **Image_Generator**: The component responsible for creating finance-themed images using AI image generation APIs
- **Text_Overlay_Engine**: The component responsible for compositing hook text onto generated images
- **Post_Scheduler**: The component responsible for calculating optimal posting times and scheduling via Facebook Graph API
- **Topic_Selector**: The sub-component responsible for selecting unique, non-repeating content topics
- **Content_Validator**: The sub-component responsible for validating generated content for compliance and format
- **PostContent**: A structured data object containing hook_text, body_text, category, topic, and hashtags
- **SchedulablePost**: A data object combining PostContent with a final image and scheduled time
- **RunConfig**: Configuration parameters for a bulk generation and scheduling run
- **Prime_Windows**: Time periods during the day when US audience engagement is highest (7-9 AM, 11:30 AM-1:30 PM, 5-7 PM, 8-10 PM EST)
- **Hook_Text**: Short attention-grabbing text (10-60 characters) rendered as an image overlay
- **Category**: One of TIPS, NEWS_COMMENTARY, EDUCATIONAL, MOTIVATIONAL, STATS_FACTS, COMPARISON, or MYTH_BUSTING

## Requirements

### Requirement 1: CLI Configuration and Execution

**User Story:** As a content manager, I want to configure and trigger bulk content generation and scheduling from the command line, so that I can automate my Facebook posting workflow with a single command.

#### Acceptance Criteria

1. WHEN a user provides a run configuration with duration, posts per day, page ID, and API credentials, THE CLI SHALL validate all parameters and initiate the orchestration pipeline
2. WHEN the posts_per_day parameter is less than 1 or greater than 15, THE CLI SHALL reject the configuration and display a descriptive error message
3. WHEN the duration parameter is not ONE_WEEK or ONE_MONTH, THE CLI SHALL reject the configuration and display a descriptive error message
4. WHEN the user specifies dry_run mode, THE System SHALL generate all content and images without scheduling to Facebook
5. WHEN the user invokes the preview command, THE CLI SHALL generate a specified number of sample posts and display them without scheduling
6. WHEN the user invokes the status command, THE CLI SHALL display the current state of all scheduled posts
7. WHEN the user invokes the cancel command with post IDs, THE CLI SHALL cancel the specified scheduled posts on Facebook

### Requirement 2: Content Generation

**User Story:** As a content manager, I want the system to generate diverse, engaging finance-related text content using AI, so that my Facebook page consistently publishes high-quality posts without manual writing.

#### Acceptance Criteria

1. WHEN the Orchestrator requests content for a given topic and style, THE Content_Generator SHALL produce a PostContent object containing hook_text, body_text, category, and hashtags
2. THE Content_Generator SHALL produce hook_text between 10 and 60 characters in length
3. THE Content_Generator SHALL produce body_text between 50 and 500 characters in length
4. THE Content_Generator SHALL produce at most 5 hashtags per post
5. WHEN generating content, THE Content_Generator SHALL target US audiences with finance-relevant topics
6. WHEN the AI API returns an invalid or non-parseable response, THE Content_Generator SHALL retry generation up to 3 times with exponential backoff before marking the post as failed

### Requirement 3: Topic Selection and Diversity

**User Story:** As a content manager, I want the system to select diverse topics without repetition, so that my audience sees varied content and engagement remains high.

#### Acceptance Criteria

1. WHEN selecting a topic, THE Topic_Selector SHALL choose a topic that has not been used within the previous 7-day window of scheduled posts
2. WHEN multiple categories are enabled, THE Topic_Selector SHALL weight selection toward under-represented categories to ensure diversity
3. WHEN scheduling posts for a single day, THE Orchestrator SHALL use at least 3 distinct content categories (or the total number of posts if fewer than 3)
4. THE Topic_Selector SHALL only select topics belonging to the configured content_categories list

### Requirement 4: Image Generation

**User Story:** As a content manager, I want the system to generate professional finance-themed images using AI, so that my posts have high-engagement visuals without requiring a graphic designer.

#### Acceptance Criteria

1. WHEN the Orchestrator requests an image for a given category and style, THE Image_Generator SHALL produce an image at Facebook-recommended dimensions (1200x630 or 1080x1080 pixels)
2. THE Image_Generator SHALL produce images in JPEG or PNG format with a file size under 10 MB
3. WHEN generating an image prompt, THE Image_Generator SHALL include style keywords appropriate to the content category and specify space for text overlay
4. WHEN the image generation API returns an error, THE Image_Generator SHALL retry with a modified prompt up to 3 times before falling back to a pre-made template image from the local library
5. WHEN the image generation API violates content policy, THE Image_Generator SHALL retry with sanitized prompt keywords

### Requirement 5: Text Overlay Composition

**User Story:** As a content manager, I want hook text to be attractively rendered on generated images, so that scrolling users are immediately drawn to the key message of each post.

#### Acceptance Criteria

1. WHEN applying a text overlay, THE Text_Overlay_Engine SHALL render hook_text onto the image with a contrast ratio of at least 4.5:1 against the background
2. WHEN applying a text overlay, THE Text_Overlay_Engine SHALL place text within safe zones leaving margins on all sides (maximum text width of 1000 pixels on a 1200-wide image)
3. WHEN the hook_text does not fit at the default font size, THE Text_Overlay_Engine SHALL reduce font size progressively down to a minimum of 16pt
4. IF the hook_text still does not fit at the minimum font size, THEN THE Text_Overlay_Engine SHALL truncate the text at a word boundary and append an ellipsis
5. THE Text_Overlay_Engine SHALL preserve the original image file and produce a new output image with the overlay applied
6. THE Text_Overlay_Engine SHALL produce output images that maintain the same dimensions as the input image

### Requirement 6: Optimal Posting Time Calculation

**User Story:** As a content manager, I want posts scheduled at optimal times for US audience engagement, so that each post reaches the maximum number of people.

#### Acceptance Criteria

1. THE Post_Scheduler SHALL distribute posts across four US engagement windows: Morning (7-9 AM EST), Lunch (11:30 AM-1:30 PM EST), After-work (5-7 PM EST), and Evening (8-10 PM EST)
2. THE Post_Scheduler SHALL allocate posts proportionally based on engagement window weights (Lunch highest, Morning and After-work high, Evening medium)
3. WHEN calculating times for a day, THE Post_Scheduler SHALL add a random offset within each window to avoid posting at exact same times daily
4. THE Post_Scheduler SHALL enforce a minimum gap of 30 minutes between any two consecutive posts on the same day
5. WHEN the minimum gap constraint cannot be satisfied, THE Post_Scheduler SHALL redistribute posts to adjacent windows

### Requirement 7: Facebook Scheduling

**User Story:** As a content manager, I want posts reliably scheduled via the Facebook Graph API, so that content is published automatically at the planned times without manual intervention.

#### Acceptance Criteria

1. WHEN scheduling a post, THE Post_Scheduler SHALL upload the image and message to the Facebook Graph API with a future scheduled_publish_time
2. THE Post_Scheduler SHALL only schedule posts with a scheduled_time at least 10 minutes in the future
3. THE Post_Scheduler SHALL only schedule posts with a scheduled_time no more than 75 days in the future
4. WHEN the Facebook API returns a rate limit response (HTTP 429), THE Post_Scheduler SHALL pause and wait until the rate limit window resets before resuming
5. WHEN a scheduling API call fails, THE Post_Scheduler SHALL retry up to 3 times with exponential backoff (2s, 4s, 8s delays)
6. IF all retries for a post fail, THEN THE Post_Scheduler SHALL mark the post as FAILED and record the error details
7. WHEN scheduling is complete, THE Post_Scheduler SHALL report the total count of scheduled posts, failed posts, and failure details
8. THE Post_Scheduler SHALL include a 1-second pause between consecutive Facebook API calls to respect rate limits

### Requirement 8: Bulk Orchestration

**User Story:** As a content manager, I want to generate and schedule an entire week or month of content in a single execution, so that I can batch my content workflow efficiently.

#### Acceptance Criteria

1. WHEN a ONE_WEEK duration is configured with N posts per day, THE Orchestrator SHALL generate exactly 7 * N posts
2. WHEN a ONE_MONTH duration is configured with N posts per day, THE Orchestrator SHALL generate exactly (days in month) * N posts
3. WHEN generating content in bulk, THE Orchestrator SHALL pause for 2 seconds every 5 posts to respect AI API rate limits
4. THE Orchestrator SHALL save a manifest file to the output directory containing all post details and scheduled times upon completion
5. WHEN the pipeline completes, THE Orchestrator SHALL display a summary report showing total generated, total scheduled, and total failed counts

### Requirement 9: Error Recovery and Resilience

**User Story:** As a content manager, I want the system to handle failures gracefully and allow resumption, so that transient errors do not waste previously generated content or require starting over.

#### Acceptance Criteria

1. WHEN the Facebook access token is expired or invalid (HTTP 401), THE System SHALL immediately halt scheduling, save all progress, and notify the user to refresh the token
2. WHEN disk space is exhausted during image generation, THE System SHALL halt generation, report how many posts were successfully generated, and support a resume command
3. WHEN an individual post fails content generation, THE Orchestrator SHALL skip that post, log the failure, and continue generating remaining posts
4. WHEN an image generation attempt fails after all retries, THE Image_Generator SHALL use a fallback template image and continue the pipeline
5. THE System SHALL store generated content locally so that a resume command can pick up from where a previous execution stopped

### Requirement 10: Security and Compliance

**User Story:** As a content manager, I want the system to handle credentials securely and generate compliant content, so that my account remains safe and posts do not violate financial regulations or platform policies.

#### Acceptance Criteria

1. THE System SHALL load all API keys and tokens from environment variables or a .env file, never from source code
2. THE System SHALL never log or display access tokens in console output or log files
3. WHEN scheduling begins, THE System SHALL validate that the Facebook token has the required permissions (pages_manage_posts, pages_read_engagement) before proceeding
4. THE Content_Validator SHALL reject generated content that contains specific stock picks, guarantees of returns, or misleading financial claims
5. THE Image_Generator SHALL include negative prompts to prevent inappropriate or misleading imagery in generated images
