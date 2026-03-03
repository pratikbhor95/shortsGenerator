import os
import json
import logging
import datetime
import argparse
import boto3
from dotenv import load_dotenv

# Absolute imports for main.py execution
from database import SessionLocal
from models import VideoJob

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("AUDIO_SERVICE")
load_dotenv()

# Initialize Polly client
polly = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_REGION")
).client('polly')

def generate_srt(speech_marks_data, srt_path):
    """Parses Polly speech marks to generate a standard SRT subtitle file."""
    lines = [json.loads(l) for l in speech_marks_data.splitlines() if json.loads(l)['type'] == 'word']
    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, word in enumerate(lines):
            start_srt = str(datetime.timedelta(milliseconds=word['time']))[:-3].replace('.', ',')
            if not start_srt.startswith("0"): start_srt = "0" + start_srt
            
            # End time is the start of next word, or +400ms for the last word
            end_ms = lines[i+1]['time'] if i+1 < len(lines) else word['time'] + 400
            end_srt = str(datetime.timedelta(milliseconds=end_ms))[:-3].replace('.', ',')
            if not end_srt.startswith("0"): end_srt = "0" + end_srt
            
            f.write(f"{i+1}\n0{start_srt} --> 0{end_srt}\n{word['value'].upper()}\n\n")

def run_audio_pipeline(lang="en"):
    session = SessionLocal()
    try:
        # Get the latest scripted job
        job = session.query(VideoJob).filter(VideoJob.status == "scripted").order_by(VideoJob.created_at.desc()).first()
        if not job:
            logger.info(f"No 'scripted' jobs found for {lang} audio pipeline.")
            return

        logger.info(f"Generating {lang.upper()} Audio/SRT for Job: {job.id}")
        text = job.ai_script.get("narration_script")
        
        # --- VOICE SELECTION LOGIC ---
        # English: 'Matthew' (Male) or 'Stephen'
        # Hindi: 'Kajal' (Female) or 'Aditi'
        if lang == "hindi":
            voice_id = 'Kajal' # High-quality Hindi Neural voice
        else:
            voice_id = 'Stephen' # Standard English News voice

        os.makedirs("assets/audio", exist_ok=True)
        audio_path = f"assets/audio/{job.id}.mp3"

        # 1. Synthesize Speech (Audio File)
        audio_res = polly.synthesize_speech(
            Text=text, 
            OutputFormat='mp3', 
            VoiceId=voice_id, 
            Engine='neural'
        )
        with open(audio_path, 'wb') as f:
            f.write(audio_res['AudioStream'].read())

        # 2. Synthesize Speech Marks (For Subtitles)
        marks_res = polly.synthesize_speech(
            Text=text, 
            OutputFormat='json', 
            VoiceId=voice_id, 
            SpeechMarkTypes=['word'], 
            Engine='neural'
        )
        generate_srt(
            marks_res['AudioStream'].read().decode('utf-8'), 
            audio_path.replace(".mp3", ".srt")
        )

        # Update Database
        job.audio_path = audio_path
        job.status = "voiced"
        session.commit()
        logger.info(f"Audio Service Success: {voice_id} used for Job {job.id}")

    except Exception as e:
        logger.error(f"Audio Error: {e}")
        session.rollback()
    finally:
        session.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", type=str, default="en")
    args = parser.parse_args()
    
    run_audio_pipeline(lang=args.lang)