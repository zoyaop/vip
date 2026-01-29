import asyncio
import glob
import json
import os
import random
import re
from typing import Union, List, Set

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# --- STRONGER API SEQUENTIAL ROTATION LOGIC ---
API_KEYS: List[str] = [k.strip() for k in config.API_KEY.split(",")]
exhausted_keys: Set[str] = set()
current_key_index = 0
key_lock = asyncio.Lock() # Multiple requests ko handle karne ke liye

def get_youtube_client():
    global current_key_index
    
    if len(exhausted_keys) >= len(API_KEYS):
        return None

    # Check if current key is already exhausted, if so move next
    start_index = current_key_index
    while API_KEYS[current_key_index] in exhausted_keys:
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        if current_key_index == start_index:
            return None
            
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

async def switch_key():
    """Key khatam hone par agla key select karta hai safely"""
    global current_key_index
    async with key_lock:
        current_key = API_KEYS[current_key_index]
        if current_key not in exhausted_keys:
            logger.warning(f"YouTube Quota Finished for Key #{current_key_index + 1}")
            exhausted_keys.add(current_key)
        
        current_key_index = (current_key_index + 1) % len(API_KEYS)
        
        if len(exhausted_keys) >= len(API_KEYS):
            logger.error("All YouTube API Keys are exhausted!")
            return False
        return True

# --- COOKIE LOGIC ---
def get_cookie_file():
    try:
        folder_path = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        if not txt_files:
            return None
        return random.choice(txt_files)
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        """ISO 8601 duration conversion"""
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        messages = [message]
        if message.reply_to_message:
            messages.append(message.reply_to_message)
        for msg in messages:
            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        return (msg.text or msg.caption)[entity.offset : entity.offset + entity.length]
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: 
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        # Jitni keys hain utni baar try karega agar quota error aata hai
        for _ in range(len(API_KEYS)):
            youtube = get_youtube_client()
            if not youtube: return None
            
            try:
                if not vidid:
                    search = await asyncio.to_thread(youtube.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    if not search.get("items"): return None
                    vidid = search["items"][0]["id"]["videoId"]
                
                video_data = await asyncio.to_thread(youtube.videos().list(part="snippet,contentDetails", id=vidid).execute)
                if not video_data.get("items"): return None
                
                item = video_data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, d_min, d_sec, thumb, vidid

            except HttpError as e:
                if e.resp.status in [403, 429]: # Quota or Rate Limit
                    if await switch_key(): continue
                break
        return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720]", "--geo-bypass", link]
        if cookie: opts.extend(["--cookies", cookie])
        
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f"yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        playlist = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await playlist.communicate()
        return [k.strip() for k in stdout.decode().split("\n") if k.strip()]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        for _ in range(len(API_KEYS)):
            youtube = get_youtube_client()
            if not youtube: return None
            try:
                search = await asyncio.to_thread(youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute)
                if not search.get("items"): return None
                
                item = search["items"][query_type]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                
                v_res = await asyncio.to_thread(youtube.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(v_res["items"][0]["contentDetails"]["duration"])
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status in [403, 429] and await switch_key(): continue
                break
        return None

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        common_opts = {"quiet": True, "no_warnings": True, "geo_bypass": True, "nocheckcertificate": True}
        if cookie: common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        if songvideo:
            opts = {**common_opts, "format": f"{format_id}+140/bestvideo+bestaudio", "outtmpl": f"downloads/{title}.%(ext)s", "merge_output_format": "mp4"}
        elif songaudio:
            opts = {**common_opts, "format": "bestaudio/best", "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}

        downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
        return downloaded_file
