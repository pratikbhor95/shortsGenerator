import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID
from database import Base # Absolute import
from sqlalchemy.sql import func

class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title = Column(String(500)) # New field for headlines
    news_url = Column(String, nullable=False)
    content = Column(Text) # New field for Gemini's detailed description
    status = Column(String(20), nullable=False, default="pending")
    s3_key = Column(String(255), nullable=True)
    
    created_at = Column(
        DateTime(timezone=True), 
        server_default=func.now()
    )
    updated_at = Column(
        DateTime(timezone=True), 
        server_default=func.now(),
        onupdate=func.now()
    )