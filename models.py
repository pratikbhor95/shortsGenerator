from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.dialects.postgresql import UUID
import uuid
from datetime import datetime, timezone
from database import Base

class VideoJob(Base):
    __tablename__ = "video_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    
    # Authenticity Columns
    title = Column(String(500), nullable=False)
    news_url = Column(String(1000), unique=True, nullable=False) # Unique URL prevents dupes
    news_source = Column(String(255), nullable=True) # e.g., "The Hindu", "MEA India"
    published_date = Column(String(100), nullable=True) # Stored as string for flexibility
    
    # Content & Processing
    content = Column(Text, nullable=False) # Detailed news summary
    ai_script = Column(JSON, nullable=True) # Isolated JSON (narration + scenes)
    audio_path = Column(String(500), nullable=True) # Local path or S3 URL
    
    status = Column(String(50), default="pending") # pending, scripted, voiced, completed
    
    # Timestamps
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    image_paths = Column(JSON, nullable=True) # Will store a list of 4 local file paths for generated images
    image_status = Column(String, default="pending") # pending, completed, failed

    def __repr__(self):
        return f"<VideoJob(id={self.id}, title={self.title[:30]}..., status={self.status})>"