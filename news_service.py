import os
import json
import logging
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from rapidfuzz import fuzz
from sqlalchemy import select
from database import SessionLocal
from models import VideoJob

# --- CONFIGURATION ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NEWS_SERVICE")

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Use ACTUAL valid model IDs (Flash 2.0 and 1.5)
MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro"
]

def generate_with_fallback(prompt, config):
    for model_id in MODEL_WATERFALL:
        try:
            logger.info(f"Attempting with {model_id}...")
            return client.models.generate_content(model=model_id, contents=prompt, config=config)
        except APIError as e:
            if e.code == 429:
                logger.warning(f"Quota hit for {model_id}. Waiting 5s...")
                time.sleep(5)
                continue
            logger.error(f"Error on {model_id}: {e}")
    raise SystemExit("CRITICAL: Waterfall exhausted.")

def scrape_news():
    session = SessionLocal()
    try:
        # 1. History for Deduplication (Last 30 Days)
        one_month_ago = datetime.now() - timedelta(days=30)
        recent = session.query(VideoJob.title, VideoJob.news_url).filter(VideoJob.created_at >= one_month_ago).all()
        existing_urls = {j.news_url for j in recent if j.news_url}
        existing_titles = [j.title for j in recent]

        # STEP A: Search (Tools ONLY - No JSON mode)
        search_prompt = "Find 5 unique, positive news stories from India today (achievements/tech/infra)."
        search_config = types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
        search_res = generate_with_fallback(search_prompt, search_config)
        
        # Extract metadata for URL mapping
        url_map = {}
        try:
            chunks = search_res.candidates[0].grounding_metadata.grounding_chunks
            for c in chunks:
                if c.web: url_map[c.web.title.lower()] = c.web.uri
        except: pass

        # STEP B: Format (JSON Mode - No Tools)
        format_prompt = f"Convert to JSON list with 'title', 'description', 'source'. Content: {search_res.text}"
        json_config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        json_res = generate_with_fallback(format_prompt, json_config)
        news_items = json.loads(json_res.text)

        # 2. Process Batch
        for item in news_items:
            title = item.get('title', 'Untitled')
            # Unique fallback URL to avoid collision
            final_url = next((u for t, u in url_map.items() if fuzz.partial_ratio(t, title.lower()) > 80), 
                             f"https://www.google.com/search?q={title.replace(' ', '+')[:50]}")

            is_dup = (final_url in existing_urls) or \
                     any(fuzz.token_sort_ratio(title.lower(), t.lower()) > 85 for t in existing_titles)

            if not is_dup:
                session.add(VideoJob(
                    title=title, content=item.get('description', ''),
                    news_url=final_url, news_source=item.get('source', 'Web'),
                    status="pending", created_at=datetime.now()
                ))
                existing_urls.add(final_url)
                existing_titles.append(title)
                logger.info(f"ADDED: {title}")
            else:
                logger.info(f"SKIPPED Duplicate: {title}")

        session.commit()
    except Exception as e:
        logger.error(f"Failed: {e}"); session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    scrape_news()