import asyncio
import glob
import json
import os
import random
import re
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

# --- API ROTATION ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS):
        return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        logger.warning(f"YouTube Quota Finished. Switching to Key #{current_key_index + 1}")
        return True
    return False

def get_cookie_file():
    try:
        folder_path = os.path.join(os.getcwd(), "cookies")
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        return random.choice(txt_files) if txt_files else None
    except: return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h, m, s = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
        total = h * 3600 + m * 60 + s
        return (f"{h:02d}:{m:02d}:{seconds:02d}" if h > 0 else f"{m:02d}:{s:02d}"), total

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None
        while True:
            youtube = get_youtube_client()
            if not youtube: return None
            try:
                if not vidid:
                    search = await asyncio.to_thread(youtube.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    if not search.get("items"): return None
                    vidid = search["items"][0]["id"]["videoId"]
                video_data = await asyncio.to_thread(youtube.videos().list(part="snippet,contentDetails", id=vidid).execute)
                item = video_data["items"][0]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return item["snippet"]["title"], d_min, d_sec, item["snippet"]["thumbnails"]["high"]["url"], vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key(): continue
                return None

    # --- VIDEO STREAM (Direct Link) ---
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720]", "--geo-bypass", link]
        if cookie: opts.extend(["--cookies", cookie])
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    # --- DOWNLOAD & CONVERT LOGIC ---
    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> Union[tuple, bool]:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "restrictfilenames": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "extractor_args": {"youtube": {"player_client": ["android", "ios"], "skip": ["dash", "hls"]}}
        }
        if cookie: common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    # Pehle download hoga, phir post-processor convert karega
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)
            except Exception as e:
                logger.error(f"Download Error: {str(e)}")
                return None

        # --- AUDIO CONVERSION LOGIC ---
        if songaudio:
            opts = {
                **common_opts,
                "format": "bestaudio/best", # Sabse acchi quality download karega
                "outtmpl": "downloads/%(title)s.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio", # Video/Webm se Audio extract karega
                    "preferredcodec": "mp3",    # MP3 mein convert karega
                    "preferredquality": "192",  # 192kbps quality
                }],
            }
        
        # --- VIDEO DOWNLOAD LOGIC ---
        elif songvideo:
            f_id = f"{format_id}+140/bestvideo+bestaudio/best" if format_id else "bestvideo+bestaudio/best"
            opts = {
                **common_opts,
                "format": f_id,
                "outtmpl": "downloads/%(title)s.%(ext)s",
                "merge_output_format": "mp4",
            }
        else:
            opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}

        downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
        
        # Agar conversion ke baad filename change ho gaya (e.g. .webm to .mp3)
        if downloaded_file:
            if songaudio and not downloaded_file.endswith(".mp3"):
                downloaded_file = os.path.splitext(downloaded_file)[0] + ".mp3"
            return downloaded_file, True
            
        return None, False

    # (Other methods like playlist, slider, exists, url remain the same)
    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        messages = [message, message.reply_to_message] if message.reply_to_message else [message]
        for msg in messages:
            if msg.entities:
                for e in msg.entities:
                    if e.type == MessageEntityType.URL:
                        return (msg.text or msg.caption)[e.offset : e.offset + e.length]
        return None
