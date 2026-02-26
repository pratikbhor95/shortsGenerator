import subprocess
import time
import logging
import sys
import os
from sqlalchemy import or_
from database import SessionLocal
from models import VideoJob

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PIPELINE_MANAGER")

def run_sequential(script_name):
    """Executes a script and blocks until completion."""
    logger.info(f"--- STARTING: {script_name} ---")
    try:
        subprocess.run([sys.executable, script_name], check=True)
        return True
    except subprocess.CalledProcessError:
        logger.error(f"CRITICAL ERROR: {script_name} failed.")
        return False

def main():
    session = SessionLocal()
    start_time = time.time()
    
    # STEP 0: THE GATEKEEPER CHECK
    # Check if there are ANY jobs that aren't finished yet
    existing_job = session.query(VideoJob).filter(
        or_(
            VideoJob.status != "completed",
            VideoJob.image_status != "completed"
        )
    ).first()
    session.close() # Close session immediately to avoid DB locks during subprocesses

    if existing_job:
        logger.info(f"RESUMING: Found incomplete job {existing_job.id}. Skipping News Fetch.")
    else:
        logger.info("SYSTEM IDLE: Fetching new news...")
        if not run_sequential("news_service.py"): 
            sys.exit(1)

    # PHASE 1: Generate Script (Gemini)
    if not run_sequential("script_service.py"): 
        sys.exit(1)

    # PHASE 2: Concurrent Asset Generation (Audio & Images)
    # We run these in parallel to save time
    logger.info("--- FORKING: Audio & Image services ---")
    proc_audio = subprocess.Popen([sys.executable, "audio_service.py"])
    proc_image = subprocess.Popen([sys.executable, "image_service.py"])

    proc_audio.wait()
    proc_image.wait()

    if proc_audio.returncode != 0 or proc_image.returncode != 0:
        logger.error("Parallel asset generation failed.")
        sys.exit(1)

    # PHASE 3: Final Rendering (FFmpeg)
    if not run_sequential("video_service.py"):
        sys.exit(1)

    total_time = time.time() - start_time
    logger.info(f"PIPELINE SUCCESSFUL. Total duration: {total_time:.2f}s")

if __name__ == "__main__":
    main()