import subprocess
import time
import logging
import sys
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("PIPELINE_MANAGER")

def run_sequential(script_name):
    """Executes a script and blocks until completion. Returns True only on success."""
    logger.info(f"--- STARTING: {script_name} ---")
    try:
        # sys.executable ensures we use the same Python interpreter and .venv
        subprocess.run([sys.executable, script_name], check=True)
        return True
    except subprocess.CalledProcessError:
        logger.error(f"CRITICAL ERROR: {script_name} failed (non-zero exit code).")
        return False
    except Exception as e:
        logger.error(f"UNEXPECTED ERROR in {script_name}: {e}")
        return False

def main():
    start_time = time.time()
    logger.info("ShortsGenerator Engine Initialized.")

    # PHASE 1: Sequential Logical Foundation
    # --------------------------------------------------
    if not run_sequential("news_service.py"): 
        logger.error("Pipeline Aborted at News stage.")
        sys.exit(1)
        
    if not run_sequential("script_service.py"): 
        logger.error("Pipeline Aborted at Script stage.")
        sys.exit(1)

    # PHASE 2: Concurrent Asset Generation
    # --------------------------------------------------
    logger.info("--- FORKING: Launching Audio & Image services in parallel ---")
    
    # Start processes without blocking
    proc_audio = subprocess.Popen([sys.executable, "audio_service.py"])
    proc_image = subprocess.Popen([sys.executable, "image_service.py"])

    # Blocking wait for both forks to rejoin
    logger.info("Waiting for parallel API responses (AWS & Hugging Face)...")
    proc_audio.wait()
    proc_image.wait()

    # Check return codes for parallel services
    if proc_audio.returncode != 0:
        logger.error("Audio Service failed. Check audio_service.py logs.")
        sys.exit(1)
    if proc_image.returncode != 0:
        logger.error("Image Service failed. Check image_service.py logs.")
        sys.exit(1)

    logger.info("Parallel asset generation successful.")

    # PHASE 3: The Gatekeeper - Final Rendering
    # --------------------------------------------------
    if not run_sequential("video_service.py"):
        logger.error("Pipeline Aborted at Video Rendering stage.")
        sys.exit(1)

    total_time = time.time() - start_time
    logger.info("==============================================")
    logger.info(f"PIPELINE FULLY SUCCESSFUL. Total duration: {total_time:.2f}s")
    logger.info("==============================================")

if __name__ == "__main__":
    main()