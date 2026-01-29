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

# API keys rotation
API_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]
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
        logger.warning(f"Quota khatam! Key #{current_key_index + 1} pe switch kar raha hoon")
        return True
    logger.error("Saare YouTube API keys khatam ho gaye!")
    return False

def get_cookie_file():
    try:
        folder = f"{os.getcwd()}/cookies"
        if not os.path.exists(folder):
            os.makedirs(folder)
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            return None
        return random.choice(txt_files)
    except Exception as e:
        logger.error(f"Cookie error: {e}")
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        total_sec = h * 3600 + m * 60 + s
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        return dur_str, total_sec

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        msgs = [message]
        if message.reply_to_message:
            msgs.append(message.reply_to_message)
        for msg in msgs:
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == MessageEntityType.URL:
                        return (msg.text or msg.caption)[ent.offset:ent.offset + ent.length]
            if msg.caption_entities:
                for ent in msg.caption_entities:
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        while True:
            yt = get_youtube_client()
            if not yt: return None
            try:
                if not vidid:
                    srch = await asyncio.to_thread(yt.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    if not srch.get("items"): return None
                    vidid = srch["items"][0]["id"]["videoId"]

                data = await asyncio.to_thread(yt.videos().list(part="snippet,contentDetails", id=vidid).execute)
                if not data.get("items"): return None

                item = data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, d_min, d_sec, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key(): continue
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, _, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> tuple:
        if videoid: 
            link = self.base + videoid
        else:
            # Link se ID nikalna zaroori hai unique filename ke liye
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            videoid = match.group(1) if match else str(random.randint(10000, 99999))

        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        # Unique Filenames using videoid to prevent overwriting
        save_path = f"downloads/{videoid}"
        mp3_file = f"{save_path}.mp3"
        
        # Agar file pehle se downloaded hai to wahi return karo (Fast Queueing)
        if os.path.exists(mp3_file):
            return mp3_file, True

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "retries": 10,
            "extractor_args": {"youtube": {"player_client": ["android", "web", "ios"]}},
        }
        if cookie: common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            # Optimized direct audio download (Faster & Stable)
            audio_opts = {
                **common_opts,
                "format": "bestaudio/best",
                "outtmpl": save_path + ".%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            }
            
            downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(audio_opts))
            # yt-dlp might append .mp3 after post-processing
            if not downloaded_file.endswith(".mp3"):
                downloaded_file = mp3_file
                
            return downloaded_file, True

        except Exception as e:
            logger.error(f"Download Error: {e}")
            return None, False
