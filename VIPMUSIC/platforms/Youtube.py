# utils/youtube.py   (or jo bhi file name hai)

import asyncio
import glob
import os
import random
import re
import sys
import json
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

# API KEY ROTATION
API_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS):
        logger.error("All YouTube API keys exhausted!")
        return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index],
                 cache_discovery=False, static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        logger.warning(f"Switching to Key #{current_key_index + 1}")
        return True
    logger.error("All keys exhausted!")
    return False

def get_cookie_file():
    try:
        folder = os.path.join(os.getcwd(), "cookies")
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            return None
        cookie = random.choice(txt_files)
        print(f"[COOKIE] Using: {cookie}", flush=True)
        return cookie
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration or "")
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

        while True:
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
                if e.resp.status == 403 and switch_key(): continue
                logger.error(f"API error: {e}")
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
        return (1, stdout.decode().split("\n")[0].strip()) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f'yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download "{link}"'
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return [k.strip() for k in stdout.decode().splitlines() if k.strip()]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            youtube = get_youtube_client()
            if not youtube: return None
            try:
                search = await asyncio.to_thread(youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute)
                if not search.get("items"): return None
                
                item = search["items"][query_type % len(search["items"])]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                
                v_res = await asyncio.to_thread(youtube.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(v_res["items"][0]["contentDetails"]["duration"])
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key(): continue
                return None

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid: link = self.base + videoid

        print(f"[DOWNLOAD] Starting for: {link} | Title: {title or 'N/A'}", flush=True)

        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        common_opts = {
            "quiet": False,
            "verbose": True,
            "no_warnings": False,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "retries": 10,
            "noplaylist": True,
        }
        if cookie:
            common_opts["cookiefile"] = cookie

        os.makedirs("downloads", exist_ok=True)

        def progress_hook(d):
            if d['status'] == 'downloading':
                print(f"[YT-DLP PROGRESS] {d.get('_percent_str', '??%')} | ETA: {d.get('_eta_str', '??')}", flush=True)
            elif d['status'] == 'finished':
                print("[YT-DLP] Download done, processing...", flush=True)

        def ytdl_run():
            opts = common_opts.copy()
            opts['progress_hooks'] = [progress_hook]

            if songvideo:
                opts.update({
                    "format": f"{format_id}+bestaudio/best" if format_id else "bestvideo[height<=720]+bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "merge_output_format": "mp4"
                })
                print("[MODE] Song Video", flush=True)
            elif songaudio:
                opts.update({
                    "format": "bestaudio/best",
                    "outtmpl": f"downloads/{title} - %(id)s.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192"
                    }]
                })
                print("[MODE] Song Audio (MP3)", flush=True)
            else:
                opts.update({
                    "format": "bestaudio/best",
                    "outtmpl": "downloads/%(title)s - %(id)s.%(ext)s"
                })
                print("[MODE] Default Audio", flush=True)

            print("[YT-DLP OPTIONS]", json.dumps(opts, indent=2, default=str), flush=True)

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                filename = ydl.prepare_filename(info)
                print(f"[DOWNLOAD COMPLETE] File: {filename}", flush=True)
                return filename

        try:
            downloaded_file = await loop.run_in_executor(None, ytdl_run)
            if os.path.exists(downloaded_file):
                print(f"[SUCCESS] Path: {downloaded_file}", flush=True)
                return downloaded_file, True
            print("[FAIL] File not found after download", flush=True)
            return None, False
        except Exception as e:
            print(f"[DOWNLOAD CRASH] {type(e).__name__}: {str(e)}", flush=True)
            import traceback
            traceback.print_exc(file=sys.stdout)
            sys.stdout.flush()
            return None, False
