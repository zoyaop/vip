import asyncio
import glob
import os
import random
import re
from typing import Union

import aiohttp
import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# --- API KEY ROTATION LOGIC ---
# Config se keys ko list mein convert karein
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

def switch_key():
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        logger.warning(f"YouTube Quota Finished. Switching to Key #{current_key_index + 1}")
        return True
    logger.error("All YouTube API Keys are exhausted!")
    return False

def get_cookie_file():
    try:
        folder_path = os.path.join(os.getcwd(), "cookies")
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        return random.choice(txt_files) if txt_files else None
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        # Base URLs for API and Watch links
        self.search_api_url = "https://www.googleapis.com/youtube/v3/search"
        self.video_api_url = "https://www.googleapis.com/youtube/v3/videos"
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        """ISO 8601 duration string conversion (e.g., PT5M30S -> 05:30)"""
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

    async def fetch_http(self, url, params):
        """Helper to make HTTP GET requests with API rotation"""
        global current_key_index
        while current_key_index < len(API_KEYS):
            params["key"] = API_KEYS[current_key_index]
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params) as response:
                        if response.status == 200:
                            return await response.json()
                        
                        # Check for Quota Exceeded (403) or Invalid Key (400)
                        if response.status in [403, 400, 429]:
                            if not switch_key():
                                return None
                            continue # Try next key
                        else:
                            logger.error(f"YouTube API Error: {response.status}")
                            return None
            except Exception as e:
                logger.error(f"HTTP Request failed: {e}")
                return None
        return None

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

        # 1. Agar ID nahi mili toh Search API use karein
        if not vidid:
            search_params = {"q": link, "part": "id", "maxResults": 1, "type": "video"}
            search_data = await self.fetch_http(self.search_api_url, search_params)
            if not search_data or not search_data.get("items"):
                return None
            vidid = search_data["items"][0]["id"]["videoId"]

        # 2. Video API se snippet aur duration nikalein
        video_params = {"id": vidid, "part": "snippet,contentDetails"}
        video_data = await self.fetch_http(self.video_api_url, video_params)
        if not video_data or not video_data.get("items"):
            return None

        item = video_data["items"][0]
        title = item["snippet"]["title"]
        thumb = item["snippet"]["thumbnails"]["high"]["url"]
        d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
        return title, d_min, d_sec, thumb, vidid

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
        # Search API call for top 10 results
        search_params = {"q": link, "part": "snippet", "maxResults": 10, "type": "video"}
        search_data = await self.fetch_http(self.search_api_url, search_params)
        if not search_data or not search_data.get("items"):
            return None
        
        item = search_data["items"][query_type]
        vidid = item["id"]["videoId"]
        title = item["snippet"]["title"]
        thumb = item["snippet"]["thumbnails"]["high"]["url"]
        
        # Duration ke liye Videos API
        v_params = {"id": vidid, "part": "contentDetails"}
        v_data = await self.fetch_http(self.video_api_url, v_params)
        d_min, _ = self.parse_duration(v_data["items"][0]["contentDetails"]["duration"])
        return title, d_min, thumb, vidid

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        # Clean Title for Filename
        safe_title = re.sub(r'[^\w\-_\. ]', '_', title) if title else "track"
        
        common_opts = {
            "quiet": True, "no_warnings": True, "geo_bypass": True, 
            "nocheckcertificate": True, "outtmpl": f"downloads/{safe_title}.%(ext)s"
        }
        if cookie: common_opts["cookiefile"] = cookie

        if songvideo:
            common_opts["format"] = f"{format_id}+140/bestvideo+bestaudio"
            common_opts["merge_output_format"] = "mp4"
        elif songaudio:
            common_opts["format"] = "bestaudio/best"
            common_opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio", 
                "preferredcodec": "mp3", 
                "preferredquality": "192"
            }]
        else:
            common_opts["format"] = "bestaudio/best"
            common_opts["outtmpl"] = "downloads/%(id)s.%(ext)s"

        def ytdl_run():
            with yt_dlp.YoutubeDL(common_opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            downloaded_file = await loop.run_in_executor(None, ytdl_run)
            return downloaded_file, True
        except Exception as e:
            logger.error(f"Download Error: {e}")
            return str(e), False
