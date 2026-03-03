import os
import logging
import urllib.request
import urllib.parse
import time
from database import SessionLocal
from models import VideoJob
from sqlalchemy.orm.attributes import flag_modified
from dotenv import load_dotenv

# Initialize configuration
load_dotenv()
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("IMAGE_SERVICE")

def generate_image(prompt, path):
    """
    Authenticated 2026 Pollinations API call for Flux Schnell.
    """
    api_key = os.getenv("POLLINATIONS_API_KEY")
    if not api_key:
        raise ValueError("POLLINATIONS_API_KEY is missing from .env file.")

    # Step 1: Sanitize and Encode Prompt (Prevents 'Control Characters' error)
    # Removing trailing periods and encoding spaces to %20
    clean_prompt = prompt.strip().rstrip('.')
    encoded_prompt = urllib.parse.quote(clean_prompt)
    
    # Step 2: Build the 2026 Unified Endpoint URL
    # width=1080&height=1920 is native vertical for Shorts
    url = f"https://gen.pollinations.ai/image/{encoded_prompt}?width=1080&height=1920&model=flux&nologo=true"

    # Step 3: Set Mandatory Headers
    headers = {
        'Authorization': f'Bearer {api_key}',
        'User-Agent': 'ShortsGenerator_v1.5_Production',
        'Accept': 'image/jpeg'
    }

    # Step 4: Execution with Retry Logic
    for attempt in range(3):
        try:
            logger.info(f"Attempt {attempt+1}: Requesting {clean_prompt[:40]}...")
            req = urllib.request.Request(url, headers=headers)
            
            with urllib.request.urlopen(req, timeout=60) as response:
                if response.status == 200:
                    data = response.read()
                    
                    # VALIDATION: Ensure it's not a 3KB error page
                    if len(data) < 10000:
                        logger.warning(f"File too small ({len(data)} bytes). Retrying...")
                        time.sleep(5)
                        continue
                    
                    with open(path, 'wb') as f:
                        f.write(data)
                    return path
                    
        except urllib.error.HTTPError as e:
            error_body = e.read().decode()
            logger.error(f"API Error ({e.code}): {error_body}")
            if e.code == 401:
                logger.critical("Unauthorized! Check if your API key is valid.")
                return None
            time.sleep(5)
        except Exception as e:
            logger.error(f"Connection Error: {e}")
            time.sleep(5)
            
    return None

def run_image_pipeline():
    session = SessionLocal()
    try:
        # Target 'voiced' status if executing manually after audio, otherwise target 'scripted' for end-to-end automation
        job = session.query(VideoJob).filter(
            VideoJob.status == "scripted",
            VideoJob.image_status == "pending"
        ).first()

        if not job:
            logger.info("No 'scripted' jobs with 'pending' images found.")
            return

        logger.info(f"--- STARTING IMAGE GEN FOR JOB: {job.id} ---")
        prompts = job.ai_script.get("visual_prompts", [])
        job_dir = f"assets/images/{job.id}"
        os.makedirs(job_dir, exist_ok=True)

        saved_paths = []
        for i, prompt in enumerate(prompts):
            image_path = os.path.join(job_dir, f"s{i+1}.jpg")
            
            # Request images sequentially to protect credit limits
            result = generate_image(prompt, image_path)
            
            if result:
                saved_paths.append(image_path)
                logger.info(f"SUCCESS: Saved Image {i+1}/4")
            else:
                logger.error(f"FAILURE: Could not generate Image {i+1}")
                break # Stop if a single image fails to keep DB integrity

        # Final DB Update
        if len(saved_paths) == len(prompts):
            job.image_paths = saved_paths
            job.image_status = "completed"
            flag_modified(job, "image_paths") # Crucial for JSON column detection
            session.commit()
            logger.info("--- DATABASE COMMITTED: Image pipeline successful ---")
        else:
            logger.error("Pipeline incomplete. Check API status/credits.")
            session.rollback()

    finally:
        session.close()

if __name__ == "__main__":
    run_image_pipeline()