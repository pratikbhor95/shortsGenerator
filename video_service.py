import os
import subprocess
import logging
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from database import SessionLocal
from models import VideoJob

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

def fix_path_for_ffmpeg(path):
    """
    FFmpeg's subtitle filter requires a very specific path format on Windows.
    1. Backslashes must become forward slashes.
    2. The drive letter colon (e.g., C:) must be escaped (C\:).
    """
    abs_path = os.path.abspath(path)
    # Step 1: Replace \ with /
    unix_path = abs_path.replace('\\', '/')
    # Step 2: Escape the colon after the drive letter (e.g., E:/ -> E\:/)
    # This is ONLY required inside the subtitles filter string
    return unix_path.replace(':', '\\:')

def get_audio_duration(audio_path):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", audio_path]
    result = subprocess.run(cmd, stdout=subprocess.PIPE, text=True, check=True)
    return float(result.stdout.strip())

def create_ken_burns(img, dur, idx, tmp):
    out = os.path.join(tmp, f"scene_{idx}.mp4")
    frames = int(dur * 24)
    zoom = "min(zoom+0.0015,1.5)" if idx % 2 == 0 else "max(1.5-0.0015*on,1)"
    vf = f"scale=4000:-1,zoompan=z='{zoom}':d={frames}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s=1080x1920,format=yuv420p"
    subprocess.run(["ffmpeg", "-y", "-i", img, "-vf", vf, "-c:v", "libx264", "-t", str(dur), "-r", "24", "-pix_fmt", "yuv420p", "-preset", "fast", out], 
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
    return out

def run_video_pipeline():
    session = SessionLocal()
    temp_dir = "assets/temp"
    
    try:
        job = session.query(VideoJob).filter(VideoJob.status == "voiced", VideoJob.image_status == "completed").first()
        if not job:
            logger.info("Nothing to render. Check your database semaphores.")
            return

        logger.info(f"Rendering Video with FIXED Captions for Job: {job.id}")
        
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        os.makedirs(temp_dir, exist_ok=True)
        
        final_video_path = f"assets/videos/{job.id}.mp4"
        srt_path = job.audio_path.replace(".mp3", ".srt")
        os.makedirs("assets/videos", exist_ok=True)

        # 1. Timing
        sc_dur = get_audio_duration(job.audio_path) / 4

        # 2. Parallel Render
        clips = [None] * 4
        with ThreadPoolExecutor(max_workers=4) as exe:
            futs = {exe.submit(create_ken_burns, job.image_paths[i], sc_dur, i, temp_dir): i for i in range(4)}
            for f in as_completed(futs): clips[futs[f]] = f.result()

        # 3. Create Concat List (SYNTAX FIX)
        concat_file = os.path.join(temp_dir, "concat.txt")
        with open(concat_file, "w") as f:
            for cp in clips:
                # Clean the path FIRST, then put the variable in the f-string
                normalized_path = os.path.abspath(cp).replace('\\', '/')
                f.write(f"file '{normalized_path}'\n")

        # 4. SUBTITLE FIX (The critical part)
        # We need the path to be escaped specifically for the -vf string
        safe_srt_path = fix_path_for_ffmpeg(srt_path)
        # STYLE OVERHAUL:
        # Fontsize=80: Large enough to be the focal point.
        # Alignment=10: This is a "magic" number in libass for middle-center alignment.
        # PrimaryColour=&H00FFFF: Bright Yellow.
        # Outline=4: Thicker border for readability.
        # BorderStyle=1: Ensures the outline is solid.
        # style = "Fontname=Arial,Fontsize=80,PrimaryColour=&H00FFFF,OutlineColour=&H000000,BorderStyle=1,Outline=4,Shadow=0,Alignment=10"

        # STYLE REVISION:
        # Fontsize=60: This is the "sweet spot" for 1080px wide vertical videos.
        # Alignment=2: Pins the text to the bottom-center.
        # MarginV=800: Pushes the text up 800 pixels from the bottom (into the center-ish area).
        # Outline=3: Professional-grade border thickness.
        style = (
            "Fontname=Arial,"
            "Fontsize=75,"
            "PrimaryColour=&H00FFFF,"
            "OutlineColour=&H000000,"
            "BorderStyle=1,"
            "Outline=4,"
            "Shadow=0,"
            "Alignment=5,"
        )
            # "MarginV=400"
        
        logger.info(f"Burning subtitles using path: {safe_srt_path}")
        
        final_cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", concat_file,
            "-i", job.audio_path,
            # Use single quotes around the entire filter value, no quotes inside
            "-vf", f"subtitles='{safe_srt_path}':force_style='{style}'",
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "libx264", "-c:a", "aac", "-shortest", "-preset", "ultrafast",
            final_video_path
        ]
        
        subprocess.run(final_cmd, check=True)

        job.status = "completed"
        session.commit()
        logger.info(f"PIPELINE COMPLETE: {final_video_path}")

    except Exception as e:
        logger.error(f"Render Failed: {e}")
        session.rollback()
        sys.exit(1)
    finally:
        if os.path.exists(temp_dir): shutil.rmtree(temp_dir)
        session.close()

if __name__ == "__main__":
    run_video_pipeline()