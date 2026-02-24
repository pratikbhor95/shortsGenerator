# Automated AI News Shorts Pipeline

A production-grade, end-to-end Python pipeline that automatically ingests daily news, generates scripts and visual prompts via an LLM, synthesizes voiceovers and images, stitches them into a cinematic 30-second YouTube Short using FFmpeg, and handles distribution and state management.



## The Architecture (And Why It Is Built This Way)

Most automated "faceless channel" scripts fail because they rely on fragile web scrapers, expensive video generation APIs, and bloated Python video libraries that cause memory leaks. This project is built to run reliably and cheaply on minimal cloud infrastructure.

1.  **Ingestion:** Uses robust RSS feeds instead of fragile DOM-based web scraping. If a news site changes its CSS, this pipeline doesn't break.
2.  **Cost Efficiency:** Replaces $4.00/video AI video generation with $0.20/video static image generation. It applies programmatic "Ken Burns" zoom/pan filters via FFmpeg to simulate motion.
3.  **Performance:** Uses raw `subprocess` calls to the `ffmpeg` binary instead of Python wrappers like MoviePy, preventing Out-Of-Memory (OOM) crashes on low-tier servers.
4.  **State Management:** Uses a PostgreSQL database as the single source of truth to track generation and upload status, rather than relying on convoluted AWS S3 lifecycle rules for business logic.

## Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Logic & Control** | Python 3.10+ | Core pipeline execution and API orchestration. |
| **The Brain** | Google Gemini 1.5 Flash | Script generation and strict JSON prompt extraction. |
| **Audio Synthesis** | OpenAI TTS API | High-quality text-to-speech narration. |
| **Visual Assets** | DALL-E 3 API | Generation of vertical (1024x1792) static image assets. |
| **Video Assembly** | FFmpeg (Raw binary) | Zoompan filtering, audio multiplexing, and final rendering. |
| **State Management** | PostgreSQL (Dockerized) | Tracks pipeline status, prevents duplicate uploads, manages retry logic. |
| **Cloud Storage** | AWS S3 | Stores the final `.mp4` payloads for 37 days. |
| **Distribution** | YouTube Data API v3 / AWS SES | Uploads to YouTube Shorts; emails pre-signed fallback links on failure. |

## Prerequisites

If you do not have these installed and configured on your host machine, the pipeline will fail.
* **FFmpeg:** Must be installed and accessible in your system's PATH.
* **Docker & Docker Compose:** Required to run the local PostgreSQL database.
* **Python 3.10+**

## Environment Configuration

Do not hardcode your credentials. Create a `.env` file in the root directory and populate it with your actual keys.

```env
# Google Gemini (Free Tier)
GEMINI_API_KEY=your_gemini_key

# OpenAI (For TTS and DALL-E 3)
OPENAI_API_KEY=your_openai_key

# AWS Infrastructure
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1
S3_BUCKET_NAME=your_news_shorts_bucket

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=videopipeline
DB_USER=postgres
DB_PASSWORD=your_secure_password