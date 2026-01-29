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

logger = LOGGER(__name__)

# --- STRONG API ROTATION SYSTEM ---
# Config se keys load karke ek list mein rakhein
WORKING_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]

def get_youtube_client():
    """Current working key ke saath client return karega"""
    if not WORKING_KEYS:
        return None
    return build("youtube", "v3", developerKey=WORKING_KEYS[0], static_discovery=False)

def mark_key_as_dead():
    """Kharab ya exhausted key ko list se nikal deta hai"""
    if WORKING_KEYS:
        dead_key = WORKING_KEYS.pop(0)
        logger.warning(f"API Key Exhausted/Invalid: {dead_key[:10]}... | Remaining: {len(WORKING_KEYS)}")
    return len(WORKING_KEYS) > 0

# --- COOKIE LOGIC ---
def get_cookie_file():
    try:
        folder_path = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
        return random.choice(txt_files) if txt_files else None
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        if not duration: return "00:00", 0
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h, m, s = [int(match.group(i) or 0) for i in range(1, 4)]
        total_seconds = h * 3600 + m * 60 + s
        duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        return duration_str, total_seconds

    # --- INSTANT DETAILS FETCHING ---
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: 
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        while True:
            youtube = get_youtube_client()
            if not youtube: # Agar API khatam, to seedha yt-dlp (Fallback)
                return await self.fallback_details(link, vidid)

            try:
                if not vidid:
                    search = await asyncio.to_thread(
                        youtube.search().list(q=link, part="id", maxResults=1, type="video").execute
                    )
                    if not search.get("items"):
                        return await self.fallback_details(link, vidid)
                    vidid = search["items"][0]["id"]["videoId"]
                
                video_data = await asyncio.to_thread(
                    youtube.videos().list(part="snippet,contentDetails", id=vidid).execute
                )
                if not video_data.get("items"):
                    return await self.fallback_details(link, vidid)
                
                item = video_data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, d_min, d_sec, thumb, vidid

            except HttpError as e:
                if e.resp.status in [403, 400]: # Quota/Invalid Key
                    if mark_key_as_dead(): continue
                break
            except Exception:
                break
        
        return await self.fallback_details(link, vidid)

    # --- FALLBACK SEARCH (JAB API FAIL HO) ---
    async def fallback_details(self, query, vidid=None):
        try:
            ydl_opts = {"quiet": True, "cookiefile": get_cookie_file(), "skip_download": True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                search_query = f"https://www.youtube.com/watch?v={vidid}" if vidid else f"ytsearch:{query}"
                info = await asyncio.to_thread(ydl.extract_info, search_query, download=False)
                if 'entries' in info: info = info['entries'][0]
                
                m, s = divmod(info.get("duration", 0), 60)
                h, m = divmod(m, 60)
                d_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
                return info['title'], d_str, info.get("duration", 0), info.get("thumbnail"), info['id']
        except Exception:
            return None

    # --- INSTANT STREAM LINK (NO DOWNLOAD) ---
    async def get_stream_link(self, link: str):
        """Ye link direct VC player ko diya jayega bina download kiye"""
        loop = asyncio.get_running_loop()
        ydl_opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "skip_download": True,
            "cookiefile": get_cookie_file()
        }
        try:
            def extract():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    return ydl.extract_info(link, download=False)['url']
            return await loop.run_in_executor(None, extract)
        except Exception as e:
            logger.error(f"Streaming Error: {e}")
            return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    # --- FASTEST PLAY LOGIC FOR VC ---
    async def play_instant(self, query):
        """Esko apne play command mein use karein"""
        details, vidid = await self.track(query)
        if not vidid: return None
        
        stream_url = await self.get_stream_link(details['link'])
        details['stream_link'] = stream_url
        return details

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f"yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return [k.strip() for k in stdout.decode().split("\n") if k.strip()]
