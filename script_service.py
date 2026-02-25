import os
import json
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError
from database import SessionLocal
from models import VideoJob

# Setup logging
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

def generate_script_from_news(title: str, content: str, source: str, date: str):
    """Generates a structured JSON script utilizing source and date metadata."""
    
    # Fallbacks in case the metadata is missing
    safe_source = source if source else "verified sources"
    safe_date = date if date else "recently"

    prompt = f"""
    You are a viral news scriptwriter. Create a fast-paced 60-second video script.
    
    NEWS TITLE: {title}
    PUBLISHED DATE: {safe_date}
    SOURCE: {safe_source}
    CONTENT: {content}

    Constraints:
    1. Output MUST be ONLY valid JSON.
    2. No conversational text outside the JSON.
    3. Include exactly 4 visual scene prompts for image generation.
    4. The narration MUST explicitly mention the source ("According to {safe_source}...") to build trust.
    5. CRITICAL: NEVER request maps, specific country flags, or text in the visual prompts. Describe symbolic human actions or objects instead (e.g., 'two diplomats shaking hands' instead of 'the flags of India and Japan').

    Required JSON Structure:
    {{
        "narration_script": "Engaging voiceover text...",
        "visual_prompts": [
            "Scene 1 description",
            "Scene 2 description",
            "Scene 3 description",
            "Scene 4 description"
        ]
    }}
    """

    # Using the fallback wrapper
    response = generate_with_fallback(
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7 # Slight creativity for engaging narration
        )
    )

    try:
        data = json.loads(response.text)
        if len(data.get("visual_prompts", [])) != 4:
            raise ValueError("LLM failed to provide exactly 4 visual prompts.")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"LLM Structure Failure: {e}")
        raise SystemExit("Pipeline stopped: Invalid LLM output format.")

def run_script_pipeline():
    session = SessionLocal()
    try:
        # LOGIC: Grab the LATEST pending news item to save your quota
        job = session.query(VideoJob).filter(
            VideoJob.status == "pending",
            VideoJob.content != None
        ).order_by(VideoJob.created_at.desc()).first()

        if not job:
            logger.info("No pending news items found.")
            return

        logger.info(f"Processing Latest News: {job.title[:50]}...")
        
        # Inject the DB columns into the generator
        script_data = generate_script_from_news(
            title=job.title, 
            content=job.content,
            source=job.news_source,
            date=job.published_date
        )
        
        job.ai_script = script_data
        job.status = "scripted"
        
        session.commit()
        logger.info(f"Success! Script stored securely in Job ID: {job.id}")

    except Exception as e:
        logger.error(f"Processing Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    run_script_pipeline()