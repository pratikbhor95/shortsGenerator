import os
import json
import logging
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from rapidfuzz import fuzz
from sqlalchemy import select
from database import SessionLocal
from models import VideoJob
from datetime import date

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NEWS_SERVICE")

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Waterfall excluding lite-models that might have different tool support
MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite"
]

def generate_with_fallback(prompt, config, use_json=False):
    """Retries with different models. Drops JSON mode if tools are present."""
    for model_id in MODEL_WATERFALL:
        try:
            # STEP 0: Safety Check - API doesn't allow JSON + Tools
            current_config = config
            if config.tools and use_json:
                logger.warning("Tools detected. Disabling native JSON mode to avoid 400 error.")
                # We will parse JSON manually from the text instead
            
            logger.info(f"Attempting with {model_id}...")
            response = client.models.generate_content(
                model=model_id, contents=prompt, config=current_config
            )
            return response
        except APIError as e:
            if e.code == 429:
                logger.warning(f"Quota exceeded for {model_id}. Waiting 10s...")
                time.sleep(10) # Brief pause to let rate limits breathe
                continue
            raise
    raise SystemExit("CRITICAL: All models failed.")

def scrape_news():
    session = SessionLocal()
    try:
        # STEP 1: Fetch Search Results (Plain Text to avoid 400 error)
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        search_prompt = f"Find exactly ONE unique, positive India news story for today {date.today()}. Focus on national achievements."
        
        # We don't use response_mime_type here
        search_config = types.GenerateContentConfig(tools=[grounding_tool], temperature=1.0)
        search_response = generate_with_fallback(search_prompt, search_config)
        
        # STEP 2: Extract JSON from the grounded text (No tools here)
        logger.info("Structuring grounded news into JSON...")
        format_prompt = f"Convert this news into valid JSON with keys 'title', 'description', 'url', 'source_name'. Content: {search_response.text}"
        
        # Native JSON mode is safe here because tools=[ ]
        json_config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        json_response = generate_with_fallback(format_prompt, json_config)
        
        # 1. Parsing safety: Gemini sometimes wraps objects in a list
        raw_data = json.loads(json_response.text)
        
        if isinstance(raw_data, list):
            # If it's a list, take the first dictionary
            item = raw_data[0] if len(raw_data) > 0 else {}
        else:
            # If it's already a dictionary, use it directly
            item = raw_data

        # item = json.loads(json_response.text)
        title = item.get('title', 'Untitled')
        url = item.get('url', '')
        
        # STEP 3: Deduplication
        url_exists = session.query(VideoJob).filter(VideoJob.news_url == item.get('url')).first()
        
        # Check against last 15 titles to prevent clones
        stmt = select(VideoJob.title).order_by(VideoJob.created_at.desc()).limit(15)
        existing_titles = session.execute(stmt).scalars().all()
        is_duplicate = any(fuzz.token_sort_ratio(title.lower(), t.lower()) > 70 for t in existing_titles)

        if not url_exists and not is_duplicate:
            new_job = VideoJob(
                title=title,
                content=item.get('description', ''),
                news_url=item.get('url'),
                news_source=item.get('source_name', 'Unknown'),
                status="pending"
            )
            session.add(new_job)
            session.commit()
            logger.info(f"SUCCESS: Queued unique story: {title}")
        else:
            logger.info("Skipped: Story already exists.")

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    scrape_news()