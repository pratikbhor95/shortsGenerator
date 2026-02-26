import os
import json
import logging
import time
from datetime import date
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from rapidfuzz import fuzz
from sqlalchemy import select
from database import SessionLocal
from models import VideoJob

logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("NEWS_SERVICE")

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro"
]

def generate_with_fallback(prompt, config, use_json=False):
    for model_id in MODEL_WATERFALL:
        try:
            current_config = config
            if getattr(config, 'tools', None) and use_json:
                logger.warning("Tools detected. Disabling native JSON mode.")
            
            logger.info(f"Attempting with {model_id}...")
            response = client.models.generate_content(
                model=model_id, contents=prompt, config=current_config
            )
            return response
        except APIError as e:
            if e.code == 429:
                logger.warning(f"Quota exceeded for {model_id}. Waiting 10s...")
                time.sleep(10)
                continue
            raise
    raise SystemExit("CRITICAL: All models failed.")

def scrape_news():
    session = SessionLocal()
    try:
        # STEP 1: Grounded Search
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        search_prompt = f"Find exactly ONE unique, positive India news story for today {date.today()}. Focus on national achievements."
        
        search_config = types.GenerateContentConfig(tools=[grounding_tool], temperature=1.0)
        search_response = generate_with_fallback(search_prompt, search_config)
        
        # CRITICAL FIX: Extract the actual URL from the Grounding Metadata
        # The text DOES NOT contain the URL. We must dig into the API response object.
        extracted_url = None
        extracted_source = "Unknown"
        
        try:
            chunks = search_response.candidates[0].grounding_metadata.grounding_chunks
            for chunk in chunks:
                if hasattr(chunk, 'web') and chunk.web and chunk.web.uri:
                    extracted_url = chunk.web.uri
                    extracted_source = chunk.web.title or "Web Source"
                    break # Grab the first valid link
        except Exception as e:
            logger.warning(f"Failed to parse grounding metadata: {e}")

        # STEP 2: Extract JSON (Only ask for title and description now)
        logger.info("Structuring grounded news into JSON...")
        format_prompt = f"Convert this news into valid JSON with keys 'title', 'description'. Content: {search_response.text}"
        
        json_config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.1)
        json_response = generate_with_fallback(format_prompt, json_config)
        
        raw_data = json.loads(json_response.text)
        item = raw_data[0] if isinstance(raw_data, list) and len(raw_data) > 0 else raw_data
        
        title = item.get('title', 'Untitled')
        
        # VALIDATION GATE: Never let a null URL hit the database
        final_url = extracted_url or item.get('url') # Fallback if metadata extraction failed
        if not final_url or final_url.lower() == "null":
            logger.error(f"Validation Failed: No valid URL found for story '{title}'. Aborting save.")
            return

        # STEP 3: Deduplication
        url_exists = session.query(VideoJob).filter(VideoJob.news_url == final_url).first()
        
        stmt = select(VideoJob.title).order_by(VideoJob.created_at.desc()).limit(15)
        existing_titles = session.execute(stmt).scalars().all()
        is_duplicate = any(fuzz.token_sort_ratio(title.lower(), t.lower()) > 50 for t in existing_titles)

        if not url_exists and not is_duplicate:
            new_job = VideoJob(
                title=title,
                content=item.get('description', ''),
                news_url=final_url,
                news_source=extracted_source,
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