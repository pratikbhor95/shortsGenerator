import logging
from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel, HttpUrl
from sqlalchemy.orm import Session
from database import SessionLocal
from models import VideoJob

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s | %(levelname)s | %(message)s')
logger = logging.getLogger("API_SERVICE")

app = FastAPI(
    title="ShortsGenerator API",
    description="Manual ingestion interface for the AI Video Pipeline",
    version="1.0.0"
)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic schema for input validation
class ManualJobInput(BaseModel):
    title: str
    url: HttpUrl
    source_name: str = "Manual Entry"
    description: str = "A manually injected story for the pipeline."

    class Config:
        json_schema_extra = {
            "example": {
                "title": "SpaceX Successfully Launches New Satellite",
                "url": "https://example.com/spacex-launch",
                "source_name": "TechCrunch",
                "description": "Provide a brief summary here so the script service has context."
            }
        }

@app.post("/api/jobs/manual", status_code=201)
def inject_manual_job(job_in: ManualJobInput, db: Session = Depends(get_db)):
    """
    Injects a specific news story directly into the pipeline database.
    Bypasses the LLM news scraper.
    """
    # 1. Check for strict URL duplicates to protect pipeline integrity
    existing_job = db.query(VideoJob).filter(VideoJob.news_url == str(job_in.url)).first()
    if existing_job:
        raise HTTPException(status_code=400, detail="This URL is already in the database.")

    # 2. Insert as 'pending' so script_service.py picks it up
    try:
        new_job = VideoJob(
            title=job_in.title,
            content=job_in.description,
            news_url=str(job_in.url),
            news_source=job_in.source_name,
            status="pending"  # The critical trigger for your state machine
        )
        db.add(new_job)
        db.commit()
        db.refresh(new_job)
        
        logger.info(f"Manual job injected successfully: {new_job.title}")
        return {"message": "Job queued successfully", "job_id": str(new_job.id)}
    
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to insert manual job: {e}")
        raise HTTPException(status_code=500, detail="Database insertion failed.")