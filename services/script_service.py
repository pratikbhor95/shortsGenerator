import os
import json
import logging
import argparse
import sys
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

# Absolute imports for running from main.py
from database import SessionLocal
from models import VideoJob

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("SCRIPT_SERVICE")

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# Consistent Fallback Hierarchy
MODEL_WATERFALL = [
    "gemini-2.5-flash",
    "gemini-3-flash-preview",
    "gemini-2.5-flash-lite",
    "gemini-2.5-pro"
]

def generate_with_fallback(contents: str, config: types.GenerateContentConfig):
    for model_id in MODEL_WATERFALL:
        try:
            logger.info(f"Attempting generation using: {model_id}...")
            return client.models.generate_content(model=model_id, contents=contents, config=config)
        except APIError as e:
            if e.code in [429, 503]:
                logger.warning(f"API Error {e.code} for {model_id}. Switching...")
                continue
            raise
    raise SystemExit("CRITICAL FAILURE: All models in the waterfall failed.")

def generate_script_from_news(title: str, content: str, source: str, date: str, lang: str):
    safe_source = source if source else "verified sources"
    safe_date = date if date else "recently"

    # Language-specific instructions
    if lang == "hindi":
        lang_instructions = (
            "NARRATION LANGUAGE: The 'narration_script' MUST be written entirely in native Devanagari Hindi script (हिंदी). "
            "Do NOT use Romanized Hindi (Hinglish). Explicitly mention source: '{safe_source} के अनुसार...'"
        )
    else:
        lang_instructions = (
            "NARRATION LANGUAGE: English. Explicitly mention source: 'According to {safe_source}...'"
        )

    prompt = f"""
    You are a viral news scriptwriter. Create a fast-paced 60-second video script.
    
    NEWS TITLE: {title}
    PUBLISHED DATE: {safe_date}
    SOURCE: {safe_source}
    CONTENT: {content}

    Constraints:
    1. Output MUST be ONLY valid JSON.
    2. Include exactly 4 visual scene prompts for image generation.
    3. {lang_instructions}
    4. VISUAL PROMPTS LANGUAGE: ALWAYS English (even if narration is Hindi).
    5. CRITICAL: NEVER request maps, specific country flags, or text in the visual prompts. 
       Describe symbolic human actions or objects instead.

    Required JSON Structure:
    {{
        "narration_script": "Engaging text here...",
        "visual_prompts": ["Scene 1", "Scene 2", "Scene 3", "Scene 4"]
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
            raise ValueError("Expected exactly 4 visual prompts.")
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"LLM Structure Failure: {e}")
        raise SystemExit("Invalid LLM output format.")

def run_script_pipeline(lang="en"):
    session = SessionLocal()
    try:
        # Get the latest pending news item
        job = session.query(VideoJob).filter(
            VideoJob.status == "pending",
            VideoJob.content != None
        ).order_by(VideoJob.created_at.desc()).first()

        if not job:
            logger.info(f"No pending news found for {lang} pipeline.")
            return

        logger.info(f"Generating {lang.upper()} script for Job ID: {job.id}")
        
        script_data = generate_script_from_news(
            title=job.title, 
            content=job.content,
            source=job.news_source,
            date=job.published_date,
            lang=lang
        )
        
        job.ai_script = script_data
        job.status = "scripted"
        session.commit()
        logger.info("Success! Job marked as 'scripted'.")

    except Exception as e:
        logger.error(f"Processing Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", type=str, default="en")
    args = parser.parse_args()
    
    run_script_pipeline(lang=args.lang)