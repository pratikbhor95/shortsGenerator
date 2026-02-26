import os
import json
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Assuming these exist in your project structure
from database import SessionLocal
from models import VideoJob

# Setup strict logging for production
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise SystemExit("CRITICAL ERROR: GEMINI_API_KEY is missing from your .env file.")

client = genai.Client(api_key=api_key)

# The Fallback Hierarchy: Prioritizing speed and cost, falling back to heavier models if rate-limited.
MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3.0-flash", # Assuming you might upgrade to the latest flash
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro"
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
                logger.error(f"API Error with {model_id}: {e.message}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error with {model_id}: {e}")
            raise

    raise SystemExit("CRITICAL FAILURE: All models in the waterfall failed. Check your API quota.")

def generate_script_from_news(title: str, content: str, source: str, date: str):
    """Generates a structured JSON script utilizing source and date metadata."""
    
    safe_source = source if source else "verified sources"
    safe_date = date if date else "recently"

    # Architecture Decision: Native Devanagari for voice, English for images.
    prompt = f"""
    You are a viral news scriptwriter. Create a fast-paced 60-second video script.
    
    NEWS TITLE: {title}
    PUBLISHED DATE: {safe_date}
    SOURCE: {safe_source}
    CONTENT: {content}

    Constraints:
    1. Output MUST be ONLY valid JSON. No conversational text outside the JSON.
    2. Include exactly 4 visual scene prompts for image generation.
    3. NARRATION LANGUAGE: The 'narration_script' MUST be written entirely in native Devanagari Hindi script (हिंदी). Do NOT use Romanized Hindi (Hinglish).
    4. VISUAL PROMPTS LANGUAGE: The 'visual_prompts' MUST be written in English.
    5. The narration MUST explicitly mention the source ("{safe_source} के अनुसार...") to build trust.
    6. CRITICAL: NEVER request maps, specific country flags, or text in the visual prompts. Describe symbolic human actions or objects instead.

    Required JSON Structure:
    {{
        "narration_script": "टेक दुनिया में हंगामा मच गया है! क्या भारतीय आईटी सेक्टर खत्म होने की कगार पर है? ...",
        "visual_prompts": [
            "A stylized digital brain with complex neural networks...",
            "Three large modern corporate buildings dissolving...",
            "A robotic arm effortlessly constructing a digital structure...",
            "A graph showing a steep downward trend..."
        ]
    }}
    """

    response = generate_with_fallback(
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.7 
        )
    )

    try:
        data = json.loads(response.text)
        if len(data.get("visual_prompts", [])) != 4:
            raise ValueError("LLM failed to provide exactly 4 visual prompts.")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"LLM Structure Failure: {e}")
        logger.error(f"Raw LLM Output for debugging:\n{response.text}")
        raise SystemExit("Pipeline stopped: Invalid LLM output format. Check your prompt constraints.")

def run_script_pipeline():
    """Main execution loop for grabbing pending jobs and generating scripts."""
    session = SessionLocal()
    try:
        # Grab the oldest pending news item to process them sequentially
        job = session.query(VideoJob).filter(
            VideoJob.status == "pending",
            VideoJob.content != None
        ).order_by(VideoJob.created_at.asc()).first()

        if not job:
            logger.info("No pending news items found. Pipeline sleeping.")
            return

        logger.info(f"Processing Job ID: {job.id} | Title: {job.title[:50]}...")
        
        script_data = generate_script_from_news(
            title=job.title, 
            content=job.content,
            source=job.news_source,
            date=job.published_date
        )
        
        # Store the JSON directly into the database
        job.ai_script = script_data
        job.status = "scripted"
        
        session.commit()
        logger.info(f"Success! Script stored securely. Job {job.id} marked as 'scripted'.")

    except Exception as e:
        logger.error(f"Database/Processing Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    logger.info("Starting Script Generation Service...")
    run_script_pipeline()