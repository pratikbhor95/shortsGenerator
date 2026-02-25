import os
import json
import logging
import urllib.request
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from database import SessionLocal
from models import VideoJob

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

def generate_image(prompt, path):
    url = "https://router.huggingface.co/hf-inference/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {os.getenv('HF_TOKEN')}", "Content-Type": "application/json"}
    payload = {
        "inputs": f"{prompt}, digital art, editorial illustration, stylized drawing, masterpiece",
        "parameters": {"negative_prompt": "photorealistic, maps, flags, text, blurry"}
    }
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req) as res:
        with open(path, 'wb') as f: f.write(res.read())
    return path

def run_image_pipeline():
    session = SessionLocal()
    job_dir = None
    try:
        job = session.query(VideoJob).filter(VideoJob.status == "voiced").first()
        if not job: return

        logger.info(f"Parallel Image Gen for Job: {job.id}")
        prompts = job.ai_script.get("visual_prompts", [])
        job_dir = f"assets/images/{job.id}"
        os.makedirs(job_dir, exist_ok=True)

        paths = [None] * 4
        with ThreadPoolExecutor(max_workers=4) as exe:
            futures = {exe.submit(generate_image, prompts[i], f"{job_dir}/s{i+1}.jpg"): i for i in range(4)}
            for f in as_completed(futures):
                paths[futures[f]] = f.result()

        job.image_paths = paths
        job.image_status = "completed"  # Semaphore 2
        session.commit()
        logger.info("Image Service: SUCCESS")
    except Exception as e:
        logger.error(f"Image Error: {e}")
        if job_dir: shutil.rmtree(job_dir)
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    run_image_pipeline()