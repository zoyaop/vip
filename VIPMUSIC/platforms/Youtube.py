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

# ─── API KEY ROTATION ────────────────────────────────────────
API_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS):
        logger.error("Saare YouTube API keys khatam ho gaye!")
        return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        logger.warning(f"Quota khatam → Key #{current_key_index + 1} pe switch kar raha hoon")
        return True
    logger.error("Sabhi API keys exhaust ho gaye!")
    return False

# ─── COOKIE FILE LOGIC ───────────────────────────────────────
def get_cookie_file():
    try:
        folder = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            return None
        chosen = random.choice(txt_files)
        logger.info(f"Cookie use kar raha: {chosen}")
        return chosen
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration: str):
        """ISO 8601 duration ko seconds aur readable string mein convert"""
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration or "")
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        total_sec = h * 3600 + m * 60 + s
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        return dur_str, total_sec

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        msgs = [message]
        if message.reply_to_message:
            msgs.append(message.reply_to_message)

        for msg in msgs:
            if msg.entities:
                for ent in msg.entities:
                    if ent.type == MessageEntityType.URL:
                        return (msg.text or msg.caption)[ent.offset : ent.offset + ent.length]
            if msg.caption_entities:
                for ent in msg.caption_entities:
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            vidid = link
        else:
            m = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = m.group(1) if m else None

        while True:
            yt = get_youtube_client()
            if not yt:
                return None

            try:
                if not vidid:
                    res = await asyncio.to_thread(
                        yt.search().list(q=link, part="id", maxResults=1, type="video").execute
                    )
                    if not res.get("items"):
                        return None
                    vidid = res["items"][0]["id"]["videoId"]

                data = await asyncio.to_thread(
                    yt.videos().list(part="snippet,contentDetails", id=vidid).execute
                )
                if not data.get("items"):
                    return None

                item = data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                dur_str, dur_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, dur_str, dur_sec, thumb, vidid

            except HttpError as e:
                if e.resp.status == 403 and switch_key():
                    continue
                logger.error(f"YouTube API error: {e}")
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res:
            return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {
            "title": title,
            "link": self.base + vidid,
            "vidid": vidid,
            "duration_min": d_min,
            "thumb": thumb
        }, vidid

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            yt = get_youtube_client()
            if not yt:
                return None
            try:
                res = await asyncio.to_thread(
                    yt.search().list(q=link, part="snippet", maxResults=10, type="video").execute
                )
                if not res.get("items"):
                    return None

                item = res["items"][query_type]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]

                vd = await asyncio.to_thread(
                    yt.videos().list(part="contentDetails", id=vidid).execute
                )
                dur_str, _ = self.parse_duration(vd["items"][0]["contentDetails"]["duration"])
                return title, dur_str, thumb, vidid

            except HttpError as e:
                if e.resp.status == 403 and switch_key():
                    continue
                return None

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f'yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download "{link}"'
        
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        ids = [k.strip() for k in stdout.decode().split("\n") if k.strip()]
        return ids

    # ──────────────────────────────────────────────────────────────
    #              DOWNLOAD FUNCTION (sabse important)
    # ──────────────────────────────────────────────────────────────
    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        """
        Download karo aur file path return karo
        Returns: (file_path: str, success: bool)
        """
        if videoid:
            link = self.base + videoid

        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        # Common yt-dlp settings
        common = {
            "quiet": False,               # ← terminal pe progress dikhega
            "no_warnings": False,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "retries": 10,
            "noplaylist": True,           # playlist accidental download rokne ke liye
        }

        if cookie:
            common["cookiefile"] = cookie
            print(f"[COOKIE] Using → {cookie}")

        # Downloads folder bana lo
        os.makedirs("downloads", exist_ok=True)

        try:
            if songvideo:
                print(f"[VIDEO] Shuru → {title}")
                opts = {
                    **common,
                    "format": f"{format_id}+bestaudio/best" if format_id else "bestvideo[height<=?720]+bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "merge_output_format": "mp4",
                }

            elif songaudio:
                print(f"[AUDIO] Shuru → {title}")
                opts = {
                    **common,
                    "format": "bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }],
                }

            else:
                print("[DEFAULT] Audio download shuru")
                opts = {
                    **common,
                    "format": "bestaudio/best",
                    "outtmpl": "downloads/%(title)s - %(id)s.%(ext)s",
                }

            def run_download():
                print("[DEBUG] Options:", json.dumps(opts, indent=2, default=str))
                print(f"[LINK] {link}")
                
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    filename = ydl.prepare_filename(info)
                    print(f"[DONE] File → {filename}")
                    return filename

            file_path = await loop.run_in_executor(None, run_download)

            if file_path and os.path.exists(file_path):
                size_mb = os.path.getsize(file_path) / (1024 * 1024)
                print(f"[SUCCESS] Download complete | Size: {size_mb:.2f} MB | Path: {file_path}")
                return file_path, True
            else:
                print("[FAIL] File disk pe nahi mila!")
                return None, False

        except Exception as ex:
            print("[CRASH] Download fail!")
            import traceback
            traceback.print_exc()
            logger.exception("Download error")
            return None, False
