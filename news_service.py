import os
import json
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from sqlalchemy.exc import IntegrityError
from database import SessionLocal
from models import VideoJob

# Setup logging for visibility
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# The Fallback Hierarchy
MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite"
]

def generate_with_fallback(contents: str, config: types.GenerateContentConfig):
    """Loops through models to bypass 429 Quota or 503 Overload errors."""
    for model_id in MODEL_WATERFALL:
        try:
            logger.info(f"Attempting generation using: {model_id}...")
            response = client.models.generate_content(
                model=model_id, 
                contents=contents,
                config=config
            )
            return response
        except APIError as e:
            # 429 = Quota Exhausted, 503 = Server Overloaded
            if e.code in [429, 503]:
                logger.warning(f"API Error {e.code} for {model_id}. Switching to next model...")
                continue
            else:
                logger.error(f"API Error with {model_id}: {e}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error with {model_id}: {e}")
            raise

    raise SystemExit("CRITICAL FAILURE: All models in the waterfall failed.")

def fetch_india_positive_news():
    """Two-step process: 1. Live Search (Grounding) -> 2. JSON Extraction."""
    logger.info("Step 1: Fetching live grounded news for Feb 25, 2026...")
    grounding_tool = types.Tool(google_search=types.GoogleSearch())
    search_prompt = "Find 1-2 positive nationwide India news stories for today, February 25, 2026. Focus strictly on external affairs, diplomacy, and trade."
    
    # Using the fallback wrapper instead of calling the client directly
    search_response = generate_with_fallback(
        contents=search_prompt,
        config=types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=1.0 # Required for best grounding results
        )
    )
    
    # Extract metadata for absolute authenticity
    sources = []
    if search_response.candidates and search_response.candidates[0].grounding_metadata:
        metadata = search_response.candidates[0].grounding_metadata
        for chunk in metadata.grounding_chunks or []:
            if chunk.web:
                sources.append({"title": chunk.web.title, "uri": chunk.web.uri})

    logger.info("Step 2: Structuring news and mapping sources to JSON...")
    
    # Notice the double braces {{ }} to prevent Python f-string crashes
    format_prompt = f"""
    Convert the following news and verified sources into a strict JSON list.
    News Data: {search_response.text}
    Verified Sources: {json.dumps(sources)}
    
    Required JSON Format:
    [
        {{
            "title": "Short catchy headline",
            "description": "2-3 sentence summary",
            "url": "Original source URL from the verified sources",
            "source_name": "Publisher name (e.g., The Hindu)",
            "published_date": "YYYY-MM-DD or 'Today'"
        }}
    ]
    """
    
    # Using the fallback wrapper again for JSON formatting
    json_response = generate_with_fallback(
        contents=format_prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.2 # Lower temperature for strict JSON formatting
        )
    )
    
    return json.loads(json_response.text)

def save_news_to_db():
    session = None
    try:
        news_items = fetch_india_positive_news()
        session = SessionLocal()
        
        inserted_count = 0
        for item in news_items:
            # Defensive check before hitting the DB's Unique Constraint
            exists = session.query(VideoJob).filter(VideoJob.news_url == item.get('url')).first()
            
            if not exists and item.get('url'):
                new_job = VideoJob(
                    title=item.get('title', 'Untitled'),
                    content=item.get('description', ''),
                    news_url=item.get('url'),
                    news_source=item.get('source_name', 'Unknown'),
                    published_date=item.get('published_date', 'Unknown'),
                    status="pending"
                )
                session.add(new_job)
                inserted_count += 1
                logger.info(f"Queued for insertion: {item.get('title')[:40]}...")
            else:
                logger.warning(f"Skipped duplicate or invalid URL: {item.get('url')}")

        session.commit()
        logger.info(f"Success: {inserted_count} new stories added to the database.")

    except IntegrityError as e:
        logger.error(f"Database Integrity Error: {e}")
        if session: session.rollback()
    except Exception as e:
        logger.error(f"Pipeline Error: {e}")
        if session: session.rollback()
    finally:
        if session:
            session.close()

if __name__ == "__main__":
    save_news_to_db()