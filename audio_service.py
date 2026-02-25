import os
import json
import logging
import datetime
import boto3
from dotenv import load_dotenv
from database import SessionLocal
from models import VideoJob

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

polly = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
).client('polly')

def generate_srt(speech_marks_data, srt_path):
    lines = [json.loads(l) for l in speech_marks_data.splitlines() if json.loads(l)['type'] == 'word']
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, word in enumerate(lines):
            start_srt = str(datetime.timedelta(milliseconds=word['time']))[:-3].replace('.', ',')
            if not start_srt.startswith("0"): start_srt = "0" + start_srt
            end_ms = lines[i+1]['time'] if i+1 < len(lines) else word['time'] + 400
            end_srt = str(datetime.timedelta(milliseconds=end_ms))[:-3].replace('.', ',')
            if not end_srt.startswith("0"): end_srt = "0" + end_srt
            f.write(f"{i+1}\n0{start_srt} --> 0{end_srt}\n{word['value'].upper()}\n\n")

def run_audio_pipeline():
    session = SessionLocal()
    try:
        job = session.query(VideoJob).filter(VideoJob.status == "scripted").first()
        if not job: return

        logger.info(f"Generating Audio/SRT for Job: {job.id}")
        text = job.ai_script.get("narration_script")
        
        # Audio
        audio_res = polly.synthesize_speech(Text=text, OutputFormat='mp3', VoiceId='Matthew')
        audio_path = f"assets/audio/{job.id}.mp3"
        os.makedirs("assets/audio", exist_ok=True)
        with open(audio_path, 'wb') as f:
            f.write(audio_res['AudioStream'].read())

        # Marks
        marks_res = polly.synthesize_speech(Text=text, OutputFormat='json', VoiceId='Matthew', SpeechMarkTypes=['word'])
        generate_srt(marks_res['AudioStream'].read().decode('utf-8'), audio_path.replace(".mp3", ".srt"))

        job.audio_path = audio_path
        job.status = "voiced"  # Semaphore 1
        session.commit()
        logger.info("Audio Service: SUCCESS")
    except Exception as e:
        logger.error(f"Audio Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    run_audio_pipeline()