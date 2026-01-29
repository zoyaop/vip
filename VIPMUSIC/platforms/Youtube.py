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
from ytmusicapi import YTMusic

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# --- API SEQUENTIAL ROTATION LOGIC (Google Cloud V3) ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

# --- YTMusic API Backup ---
try:
    ytmusic = YTMusic("headers.json") if os.path.exists("headers.json") else YTMusic()
except Exception:
    ytmusic = YTMusic()

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

    # --- API Rotation Methods ---
    def get_client(self):
        global current_key_index
        if current_key_index >= len(API_KEYS):
            return None
        return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

    def switch_key(self):
        global current_key_index
        current_key_index += 1
        if current_key_index < len(API_KEYS):
            logger.warning(f"YouTube Quota Finished. Switching to Key #{current_key_index + 1}")
            return True
        logger.error("All YouTube API Keys are exhausted!")
        return False

    # --- URL Extraction Function (Fixed AttributeError) ---
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

    # --- Link Check ---
    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    # --- Duration Parser ---
    def parse_duration(self, duration: str):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

    # --- Metadata Fetcher (Official Web 3 + YTMusic Backup) ---
    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: 
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        while True:
            client = self.get_client()
            if not client: break
            try:
                if not vidid:
                    search = await asyncio.to_thread(client.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    if not search.get("items"): break
                    vidid = search["items"][0]["id"]["videoId"]
                
                v_data = await asyncio.to_thread(client.videos().list(part="snippet,contentDetails", id=vidid).execute)
                if not v_data.get("items"): break
                
                item = v_data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, d_min, d_sec, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and self.switch_key(): continue
                break

        # Backup YTMusic
        try:
            search = await asyncio.to_thread(ytmusic.search, link, filter="songs", limit=1)
            if search:
                item = search[0]
                return item["title"], item.get("duration", "04:00"), time_to_seconds(item.get("duration", "04:00")), item["thumbnails"][-1]["url"], item["videoId"]
        except: pass
        return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    # --- Streaming Link Fetcher (Flexible Format to fix 'Format Not Available') ---
    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        
        opts = [
            "yt-dlp", "-g", 
            "-f", "ba/bestaudio/best", # Flexible format
            "--geo-bypass", "--nocheckcertificate",
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "--extractor-args", "youtube:player_client=android_test,web,mweb",
            link
        ]
        if cookie: opts.extend(["--cookies", cookie])
        
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    # --- Playlist Extraction ---
    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        try:
            p_id = link.split("list=")[1].split("&")[0]
            client = self.get_client()
            if client:
                res = await asyncio.to_thread(client.playlistItems().list(part="contentDetails", playlistId=p_id, maxResults=limit).execute)
                return [item["contentDetails"]["videoId"] for item in res.get("items", [])]
        except: pass
        try:
            p_id = link.split("list=")[1].split("&")[0]
            res = await asyncio.to_thread(ytmusic.get_playlist, p_id, limit=int(limit))
            return [t['videoId'] for t in res['tracks']]
        except: return []

    # --- Search Menu (Slider) ---
    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            client = self.get_client()
            if not client: break
            try:
                search = await asyncio.to_thread(client.search().list(q=link, part="snippet", maxResults=10, type="video").execute)
                item = search["items"][query_type]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                v_res = await asyncio.to_thread(client.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(v_res["items"][0]["contentDetails"]["duration"])
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and self.switch_key(): continue
                break
        return None

    # --- Final Downloader (Bypass All Errors) ---
    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()
        
        # Bypass Settings
        common_opts = {
            "quiet": True, "no_warnings": True, "geo_bypass": True, "nocheckcertificate": True,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "extractor_args": {"youtube": {"player_client": ["android_test", "web", "mweb"]}}
        }
        if cookie: common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        # Fix: Requested Format Not Available
        if songvideo:
            f_str = f"{format_id}+ba/bv+ba/best" if format_id else "bv+ba/best"
            opts = {**common_opts, "format": f_str, "outtmpl": f"downloads/{title}.%(ext)s", "merge_output_format": "mp4"}
        elif songaudio:
            opts = {**common_opts, "format": "ba/bestaudio/best", "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            opts = {**common_opts, "format": "ba/bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}

        try:
            downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
            return downloaded_file, True
        except Exception as e:
            logger.error(f"Download Final Error: {e}")
            return str(e), False   
