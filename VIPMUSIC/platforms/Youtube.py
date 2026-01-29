import asyncio
import glob
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
from AnonMusic import LOGGER
from AnonMusic.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# --- API KEY ROTATION ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS): return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    return current_key_index < len(API_KEYS)

# --- ADVANCED COOKIE & HEADER ROTATION ---
def get_cookie_file():
    folder_path = os.path.join(os.getcwd(), "cookies")
    if not os.path.exists(folder_path): return None
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    return random.choice(txt_files) if txt_files else None

# User agents pool to avoid 403
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Android 14; Mobile; rv:123.0) Gecko/123.0 Firefox/123.0"
]

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        if not duration: return "00:00", 0
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h, m, s = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
        total = h * 3600 + m * 60 + s
        return (f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"), total

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        # 1. Sabse pehle API se try karein (Fastest)
        youtube = get_youtube_client()
        if youtube:
            try:
                if not vidid:
                    search = await asyncio.to_thread(youtube.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    vidid = search["items"][0]["id"]["videoId"] if search.get("items") else None
                
                if vidid:
                    video_data = await asyncio.to_thread(youtube.videos().list(part="snippet,contentDetails", id=vidid).execute)
                    if video_data.get("items"):
                        item = video_data["items"][0]
                        d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                        return item["snippet"]["title"], d_min, d_sec, item["snippet"]["thumbnails"]["high"]["url"], vidid
            except HttpError:
                switch_key()

        # 2. Agar API fail ho (403), toh yt-dlp internal search use karein
        try:
            opts = {
                "quiet": True, "no_warnings": True, "geo_bypass": True,
                "user_agent": random.choice(USER_AGENTS),
                "cookiefile": get_cookie_file(),
                "extract_flat": True, # Faster
            }
            with yt_dlp.YoutubeDL(opts) as ydl:
                search_query = f"ytsearch1:{link}" if not vidid else f"https://www.youtube.com/watch?v={vidid}"
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                if 'entries' in info: info = info['entries'][0]
                return info['title'], str(info.get('duration')), info.get('duration'), info.get('thumbnail'), info['id']
        except Exception as e:
            logger.error(f"Search failed completely: {e}")
            return None

    async def video(self, link: str, videoid: Union[bool, str] = None):
        """VPlay (Video) Off karke sirf Audio Link nikalne ke liye"""
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        
        # 'bestaudio' priority taaki VPlay (video stream) load na ho
        opts = [
            "yt-dlp", "-g", 
            "-f", "bestaudio", 
            "--geo-bypass", 
            "--no-check-certificate",
            "--user-agent", random.choice(USER_AGENTS)
        ]
        if cookie: opts.extend(["--cookies", cookie])
        
        try:
            proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()
            if stdout: return 1, stdout.decode().split("\n")[0]
            return 0, stderr.decode()
        except Exception as e:
            return 0, str(e)

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        """Robust Downloader: 403 Forbidden Error ko bypass karne ke liye"""
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        
        # Custom YTDL Options for stability
        opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "cookiefile": get_cookie_file(),
            "user_agent": random.choice(USER_AGENTS),
            "source_address": "0.0.0.0", # Force IPv4
        }

        if songvideo:
            opts.update({"format": "bestvideo[height<=720]+bestaudio/best", "merge_output_format": "mp4"})
        else: # Default behavior: Audio Only
            opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]
            })

        # Filename sanitize
        safe_title = re.sub(r'[^\w\s-]', '', title).strip() if title else "track"
        opts["outtmpl"] = f"downloads/{safe_title}.%(ext)s"

        def ytdl_run():
            # Yahan hum multiple clients try karenge agar fail hota hai (Self-Healing)
            clients = ["android", "ios", "web", "mweb"]
            for client in clients:
                try:
                    temp_opts = opts.copy()
                    temp_opts["extractor_args"] = {"youtube": {"player_client": [client]}}
                    with yt_dlp.YoutubeDL(temp_opts) as ydl:
                        info = ydl.extract_info(link, download=True)
                        return ydl.prepare_filename(info)
                except Exception as e:
                    if client == clients[-1]: raise e # Last attempt fail
                    continue

        try:
            downloaded_file = await loop.run_in_executor(None, ytdl_run)
            return downloaded_file, True
        except Exception as e:
            return str(e), False

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid
