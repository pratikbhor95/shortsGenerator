# Automated AI News Shorts Pipeline

A production-grade, end-to-end Python pipeline that automatically ingests daily news, generates scripts and visual prompts via an LLM, synthesizes voiceovers and images, stitches them into a cinematic 30-second YouTube Short using FFmpeg, and handles distribution and state management.



## The Architecture (And Why It Is Built This Way)

Most automated "faceless channel" scripts fail because they rely on fragile web scrapers, expensive video generation APIs, and bloated Python video libraries that cause memory leaks. This project is built to run reliably and cheaply on minimal cloud infrastructure.

1.  **Ingestion:** Uses robust RSS feeds instead of fragile DOM-based web scraping. If a news site changes its CSS, this pipeline doesn't break.
2.  **Cost Efficiency:** Replaces expensive AI video generation with cheaper static image generation. It applies programmatic "Ken Burns" zoom/pan filters via FFmpeg to simulate motion.
3.  **Performance:** Uses raw `subprocess` calls to the `ffmpeg` binary instead of Python wrappers like MoviePy, preventing Out-Of-Memory (OOM) crashes on low-tier servers.
4.  **State Management:** Uses a PostgreSQL database as the single source of truth to track generation and upload status, rather than relying on convoluted lifecycle rules for business logic.

## Tech Stack

| Component | Technology | Purpose |
| :--- | :--- | :--- |
| **Logic & Control** | Python 3.10+ | Core pipeline execution and API orchestration. |
| **API** | FastAPI | Manual job injection and control. |
| **The Brain** | Google Gemini 2.5 Flash | Script generation and strict JSON prompt extraction. |
| **Audio Synthesis** | AWS Polly | High-quality text-to-speech narration and SRT generation. |
| **Visual Assets** | Pollinations AI | Generation of vertical (1080x1920) static image assets. |
| **Video Assembly** | FFmpeg (Raw binary) | Zoompan filtering, audio multiplexing, and final rendering with subtitles. |
| **State Management** | PostgreSQL (Dockerized) | Tracks pipeline status, prevents duplicate uploads, manages retry logic. |
| **Database Migrations** | Alembic | Manages database schema changes. |

## Prerequisites

If you do not have these installed and configured on your host machine, the pipeline will fail.
* **FFmpeg:** Must be installed and accessible in your system's PATH.
* **Docker & Docker Compose:** Required to run the local PostgreSQL database.
* **Python 3.10+**
* **An active AWS account** with credentials configured for programmatic access.
* **API keys** for Google Gemini and Pollinations AI.

## Environment Configuration

Do not hardcode your credentials. Create a `.env` file in the root directory and populate it with your actual keys.

```env
# Google Gemini
GEMINI_API_KEY=your_gemini_key

# Pollinations AI
POLLINATIONS_API_KEY=your_pollinations_key

# AWS Infrastructure
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
AWS_REGION=us-east-1

# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=videopipeline
DB_USER=postgres
DB_PASSWORD=your_secure_password
```

## How to Run

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd ShortsGenerator
   ```

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Set up the environment:**
   - Rename `.env.example` to `.env`.
   - Fill in the required API keys and database credentials in the `.env` file.

4. **Start the database:**
   ```bash
   docker-compose up -d
   ```

5. **Initialize the database:**
   - This will create the necessary tables.
   ```bash
   python init_db.py
   ```
   - Then, apply the migrations:
   ```bash
   alembic upgrade head
   ```

6. **Run the automated pipeline:**
   ```bash
   python pipeline_manager.py
   ```
   This will run the full, automated news-gathering and video generation process.

## Custom Story Ingestion API

This project includes a FastAPI interface to manually inject stories into the pipeline, bypassing the automated news scraper. This is useful for forcing the system to cover a specific topic or for testing.

### 1. Run the API Server
In a separate terminal, start the Uvicorn server from the project root:
```bash
uvicorn api:app --reload
```
The API will be live at `http://127.0.0.1:8000`.

### 2. Submit a Manual Job
Send a `POST` request to the `/api/jobs/manual` endpoint. This will add a new story to the database with a `pending` status, where it will be picked up by the `script_service` on the next pipeline run.

**Example using cURL:**
```bash
curl -X 'POST' \
  'http://127.0.0.1:8000/api/jobs/manual' \
  -H 'accept: application/json' \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "NVIDIA Unveils Next-Gen Blackwell GPUs",
    "url": "https://example.com/nvidia-blackwell-gpus",
    "source_name": "The Verge",
    "description": "A detailed brief about the new Blackwell architecture and its implications for AI."
  }'
```

The API will protect against duplicate URLs, ensuring pipeline integrity.

## Project Structure
```
.
├── alembic/              # Database migration scripts
├── assets/               # Generated assets (audio, images, videos)
├── .gitignore
├── alembic.ini           # Alembic configuration
├── api.py                # FastAPI manual ingestion API
├── audio_service.py      # Generates audio from script
├── config.py             # Application configuration
├── database.py           # Database connection setup
├── docker-compose.yml    # Docker configuration for PostgreSQL
├── image_service.py      # Generates images from visual prompts
├── init_db.py            # Initializes the database schema
├── models.py             # SQLAlchemy database models
├── news_service.py       # Fetches news articles
├── pipeline_manager.py   # Main pipeline orchestrator
├── readme.md             # This file
├── requirements.txt      # Python dependencies
├── script_service.py     # Generates video script from news
└── video_service.py      # Renders the final video
```
