import asyncio
import glob
import json
import os
import random
import re
import sys  # ← flush ke liye zaroori
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# API KEY ROTATION
API_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS):
        logger.error("All YouTube API keys exhausted!")
        return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index],
                 cache_discovery=False, static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        logger.warning(f"Switching to API Key #{current_key_index + 1}")
        return True
    logger.error("All keys exhausted!")
    return False

def get_cookie_file():
    try:
        folder = os.path.join(os.getcwd(), "cookies")
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            return None
        cookie = random.choice(txt_files)
        print(f"[COOKIE] Using: {cookie}", flush=True)
        return cookie
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration: str):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration or "")
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        total = h * 3600 + m * 60 + s
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        return dur_str, total

    # ... (exists, url, details, track, slider, playlist functions same rakh sakte ho, change nahi zaroori abhi)

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid:
            link = self.base + videoid

        print(f"[DOWNLOAD START] Link: {link} | Title: {title}", flush=True)

        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        common_opts = {
            "quiet": False,
            "no_warnings": False,
            "verbose": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "retries": 10,
            "noplaylist": True,
        }
        if cookie:
            common_opts["cookiefile"] = cookie

        os.makedirs("downloads", exist_ok=True)

        # Progress hook taaki real-time update dikhe
        def progress_hook(d):
            if d['status'] == 'downloading':
                print(f"[PROGRESS] {d.get('_percent_str', '??%')} | {d.get('_eta_str', '??s left')}", flush=True)
            elif d['status'] == 'finished':
                print("[PROGRESS] Download complete, now post-processing...", flush=True)

        def run_ytdl():
            print("[INSIDE THREAD] yt-dlp version:", yt_dlp.version.__version__, flush=True)
            print("[INSIDE THREAD] Starting extraction...", flush=True)
            sys.stdout.flush()

            opts = {**common_opts}
            opts['progress_hooks'] = [progress_hook]  # ← real progress

            if songvideo:
                print("[MODE] Video + Audio", flush=True)
                opts.update({
                    "format": f"{format_id}+bestaudio/best" if format_id else "bestvideo[height<=?720]+bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "merge_output_format": "mp4",
                })
            elif songaudio:
                print("[MODE] Audio MP3", flush=True)
                opts.update({
                    "format": "bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                })
            else:
                print("[MODE] Default Audio", flush=True)
                opts.update({
                    "format": "bestaudio/best",
                    "outtmpl": "downloads/%(title)s - %(id)s.%(ext)s",
                })

            sys.stdout.flush()

            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(link, download=True)
                    filename = ydl.prepare_filename(info)
                    print(f"[THREAD SUCCESS] File: {filename}", flush=True)
                    if os.path.exists(filename):
                        size_mb = os.path.getsize(filename) / (1024 * 1024)
                        print(f"[SIZE] {size_mb:.2f} MB", flush=True)
                    return filename
                except Exception as e:
                    print(f"[THREAD ERROR] {type(e).__name__}: {str(e)}", flush=True)
                    sys.stdout.flush()
                    raise

        try:
            file_path = await loop.run_in_executor(None, run_ytdl)
            if file_path and os.path.exists(file_path):
                print(f"[MAIN SUCCESS] Downloaded: {file_path}", flush=True)
                return file_path, True
            print("[MAIN FAIL] File not on disk", flush=True)
            return None, False

        except Exception as ex:
            print(f"[MAIN CRASH] {type(ex).__name__}: {str(ex)}", flush=True)
            import traceback
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            return None, False
