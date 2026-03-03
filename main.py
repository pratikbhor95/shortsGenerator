import subprocess
import time
import logging
import sys
import os
import argparse
from sqlalchemy import or_

# Absolute imports from the root directory
from database import SessionLocal
from models import VideoJob

# Setup professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PIPELINE_MANAGER")

def run_service(script_name, lang="en", background=False):
    """
    Executes a script from the /services folder.
    Uses PYTHONPATH to ensure scripts can find modules in the root directory.
    """
    script_path = os.path.join("services", script_name)
    
    if not os.path.exists(script_path):
        logger.error(f"FILE NOT FOUND: {script_path}")
        return None if background else False

    logger.info(f"--- {'STARTING' if not background else 'FORKING'}: {script_name} ({lang}) ---")
    
    # CRITICAL: Prepare environment variables to include project root in Python path
    env = os.environ.copy()
    # This tells the subprocess to look at the current working directory for imports
    env["PYTHONPATH"] = os.getcwd() 
    
    cmd = [sys.executable, script_path, "--lang", lang]
    
    try:
        if background:
            # Forking process for parallel execution (Audio/Images)
            return subprocess.Popen(cmd, env=env)
        else:
            # Blocking execution for sequential steps
            subprocess.run(cmd, env=env, check=True)
            return True
    except subprocess.CalledProcessError:
        logger.error(f"CRITICAL ERROR: {script_name} failed for language: {lang}")
        return False

def main():
    # 1. Handle Command Line Arguments
    parser = argparse.ArgumentParser(description="AI Shorts Generator Pipeline")
    parser.add_argument("--lang", type=str, default="en", choices=["en", "hindi"], 
                        help="Specify language: 'en' (default) or 'hindi'")
    args = parser.parse_args()

    start_time = time.time()
    logger.info(f"INITIATING PIPELINE | Language: {args.lang.upper()}")

    # 2. THE GATEKEEPER: Check for incomplete jobs in DB
    session = SessionLocal()
    existing_job = session.query(VideoJob).filter(
        or_(
            VideoJob.status != "completed",
            VideoJob.image_status != "completed"
        )
    ).first()
    session.close() 

    # 3. PHASE 0: News Scrapping (Skip if resuming)
    if existing_job:
        logger.info(f"RESUMING: Found incomplete job ID {existing_job.id}. Skipping Scraper.")
    else:
        logger.info("SYSTEM IDLE: Triggering Scraper...")
        if not run_service("news_service.py", lang=args.lang):
            sys.exit(1)

    # 4. PHASE 1: Script Generation (LLM)
    if not run_service("script_service.py", lang=args.lang):
        sys.exit(1)

    # 5. PHASE 2: Parallel Asset Generation (Audio & Images)
    logger.info("--- PARALLEL EXECUTION: Audio & Image Services ---")
    proc_audio = run_service("audio_service.py", lang=args.lang, background=True)
    proc_image = run_service("image_service.py", lang=args.lang, background=True)

    # Blocking wait for parallel tasks
    if proc_audio: proc_audio.wait()
    if proc_image: proc_image.wait()

    if (proc_audio and proc_audio.returncode != 0) or (proc_image and proc_image.returncode != 0):
        logger.error("Parallel generation phase failed. Check service logs.")
        sys.exit(1)

    # 6. PHASE 3: Video Rendering (FFmpeg)
    if not run_service("video_service.py", lang=args.lang):
        logger.error("Video rendering failed.")
        sys.exit(1)

    total_time = time.time() - start_time
    logger.info(f"PIPELINE SUCCESSFUL [{args.lang.upper()}]. Total Duration: {total_time:.2f}s")

if __name__ == "__main__":
    main()