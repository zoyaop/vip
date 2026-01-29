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

# --- API ROTATION LOGIC ---
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
        logger.warning(f"YouTube Quota Exhausted. Switching to Key #{current_key_index + 1}")
        return True
    return False

# --- COOKIE LOGIC ---
def get_cookie_file():
    folder_path = os.path.join(os.getcwd(), "cookies")
    if not os.path.exists(folder_path):
        return None
    txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
    return random.choice(txt_files) if txt_files else None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.ytdl_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

    def parse_duration(self, duration):
        if not duration: return "00:00", 0
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

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

        # Try with API first
        while True:
            youtube = get_youtube_client()
            if not youtube:
                break # Fallback to ytdl
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
                if e.resp.status == 403:
                    if switch_key(): continue
                    else: break
                return None

        # FALLBACK: Search using yt-dlp if API fails
        try:
            opts = self.ytdl_opts.copy()
            cookie = get_cookie_file()
            if cookie: opts["cookiefile"] = cookie
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                search_query = f"ytsearch1:{link}" if not vidid else vidid
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                if 'entries' in info: info = info['entries'][0]
                
                return (
                    info['title'],
                    time_to_seconds(info.get('duration', 0))[0], # assuming you have a formatter
                    info.get('duration', 0),
                    info.get('thumbnail'),
                    info['id']
                )
        except Exception as e:
            logger.error(f"YT-DLP Fallback Error: {e}")
            return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        # Safe filename
        safe_title = re.sub(r'[^\w\s-]', '', title).strip() if title else "track"
        
        opts = self.ytdl_opts.copy()
        if cookie: opts["cookiefile"] = cookie

        if songvideo:
            opts.update({
                "format": f"{format_id}+140/bestvideo+bestaudio",
                "outtmpl": f"downloads/{safe_title}.%(ext)s",
                "merge_output_format": "mp4",
            })
        elif songaudio:
            opts.update({
                "format": "bestaudio/best",
                "outtmpl": f"downloads/{safe_title}.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            opts["outtmpl"] = "downloads/%(id)s.%(ext)s"

        def ytdl_run():
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            downloaded_file = await loop.run_in_executor(None, ytdl_run)
            return downloaded_file, True
        except Exception as e:
            logger.error(f"Download Error: {e}")
            return str(e), True
