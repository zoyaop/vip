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
    return current_key_index < len(API_KEYS)

def get_cookie_file():
    folder_path = os.path.join(os.getcwd(), "cookies")
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    return random.choice(txt_files) if txt_files else None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        # 403 Forbidden se bachne ke liye strong headers
        self.ytdl_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "outtmpl": "downloads/%(id)s.%(ext)s",
            "format": "bestaudio/best", # Sirf audio download karega (VPlay off)
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "referer": "https://www.google.com/",
            "http_chunk_size": 10485760,
        }

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        # Try API First
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
                        duration_str = item["contentDetails"]["duration"]
                        # Convert ISO 8601 duration
                        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
                        h, m, s = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
                        d_min = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                        return item["snippet"]["title"], d_min, (h*3600+m*60+s), item["snippet"]["thumbnails"]["high"]["url"], vidid
            except HttpError:
                switch_key()

        # Fallback to yt-dlp if API fails or Forbidden
        try:
            with yt_dlp.YoutubeDL(self.ytdl_opts) as ydl:
                info = await asyncio.to_thread(ydl.extract_info, f"ytsearch1:{link}" if not vidid else vidid, download=False)
                if 'entries' in info: info = info['entries'][0]
                return info['title'], str(info.get('duration')), info.get('duration'), info.get('thumbnail'), info['id']
        except Exception as e:
            logger.error(f"Error in details: {e}")
            return None

    # VPlay ko disable karne ke liye sirf audio format force kiya gaya hai
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        # Yahan hum --format bestaudio use kar rahe hain taaki video (VPlay) na chale
        opts = ["yt-dlp", "-g", "-f", "bestaudio", "--geo-bypass", "--no-check-certificate", link]
        if cookie: opts.extend(["--cookies", cookie])
        
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        return 0, stderr.decode()

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        # Audio default download logic
        opts = self.ytdl_opts.copy()
        if cookie: opts["cookiefile"] = cookie
        
        # Force Audio even if VPlay is triggered
        if songvideo: # Agar user ne jaan buch kar video manga ho
            opts["format"] = "bestvideo[height<=720]+bestaudio/best"
            opts["merge_output_format"] = "mp4"
        else: # Default behavior: Only Audio
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]

        if title:
            safe_title = re.sub(r'[^\w\s-]', '', title).strip()
            opts["outtmpl"] = f"downloads/{safe_title}.%(ext)s"

        def ytdl_run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            downloaded_file = await loop.run_in_executor(None, ytdl_run)
            return downloaded_file, True
        except Exception as e:
            logger.error(f"Download Error: {e}")
            return str(e), False

    # Is method ko clean rakha gaya hai taaki extra calls na hon
    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid
