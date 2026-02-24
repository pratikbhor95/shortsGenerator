import os
import json
from dotenv import load_dotenv
from google import genai  # NEW IMPORT
from google.genai import types
from database import SessionLocal
from models import VideoJob

load_dotenv()

# The client automatically picks up GEMINI_API_KEY from .env
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

def fetch_india_positive_news():
    # Use gemini-2.0-flash for better speed and current availability
    model_id = "gemini-2.5-flash" 
    
    prompt = """
    Search for and provide the top 3-5 nationwide news stories from India for today.
    Constraints:
    1. Focus: Nationwide India news.
    2. Sentiment: Strictly POSITIVE or constructive news.
    3. Priority: External Affairs (diplomacy, trade, foreign relations).
    
    Return the data ONLY as a valid JSON list of objects:
    [{"title": "...", "description": "...", "url": "..."}]
    """

    # NEW SYNTAX: client.models.generate_content
    response = client.models.generate_content(
        model=model_id,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json" # FORCE JSON OUTPUT
        )
    )
    
    return json.loads(response.text)

def save_news_to_db():
    try:
        news_items = fetch_india_positive_news()
        session = SessionLocal()
        
        for item in news_items:
            # Logic: Check for duplicates before inserting
            exists = session.query(VideoJob).filter(VideoJob.title == item['title']).first()
            if not exists:
                new_job = VideoJob(
                    title=item['title'],
                    news_url=item.get('url', 'https://mea.gov.in'),
                    content=item['description'],
                    status="pending"
                )
                session.add(new_job)
                print(f"Stored: {item['title'][:50]}...")
        
        session.commit()
    except Exception as e:
        print(f"Error: {e}")
    finally:
        session.close()

if __name__ == "__main__":
    save_news_to_db()