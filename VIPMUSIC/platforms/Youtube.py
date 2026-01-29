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
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            logger.warning("Cookies folder empty → fresh cookies daalo (Chrome export) for less 403")
            return None
        cookie = random.choice(txt_files)
        logger.info(f"Using cookie: {os.path.basename(cookie)}")
        return cookie
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
                logger.error(f"API error: {e}")
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, _, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = get_cookie_file()
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720]", "--geo-bypass", link]
        if cookie: opts.extend(["--cookies", cookie])

        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0].strip()
        logger.error(f"Video URL fetch fail: {stderr.decode()}")
        return 0, None

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f"yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await proc.communicate()
        return [k.strip() for k in stdout.decode().split("\n") if k.strip()]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            yt = get_youtube_client()
            if not yt: return None
            try:
                srch = await asyncio.to_thread(yt.search().list(q=link, part="snippet", maxResults=10, type="video").execute)
                if not srch.get("items"): return None

                item = srch["items"][query_type]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]

                vres = await asyncio.to_thread(yt.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(vres["items"][0]["contentDetails"]["duration"])
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key(): continue
                logger.error(f"Slider error: {e}")
                return None

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> tuple:
        if not videoid:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            videoid = match.group(1) if match else str(random.randint(1000, 9999))
        
        link = self.base + videoid
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        # IMPORTANT: Unique filenames to prevent crashing and switching
        # Har song ab apni ID ke naam se save hoga
        temp_video_file = f"downloads/temp_{videoid}.mp4"
        mp3_file = f"downloads/{videoid}.mp3"

        if os.path.exists(mp3_file):
            return mp3_file, True

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "retries": 10,
            "fragment_retries": 5,
            "extractor_args": {"youtube": {"player_client": ["default", "ios", "web"]}},
            "concurrent_fragment_downloads": 10,
        }

        try:
            import subprocess
            subprocess.run(["aria2c", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            common_opts["external_downloader"] = "aria2c"
            common_opts["external_downloader_args"] = ["-x", "16", "-k", "1M", "-s", "16"]
        except: pass

        if cookie: common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            # Step 1: Fast video download
            video_opts = {
                **common_opts,
                "format": "22/best[ext=mp4][height<=720]/best",
                "outtmpl": temp_video_file,
            }
            downloaded_temp = await loop.run_in_executor(None, lambda: ytdl_run(video_opts))

            # Step 2: FFmpeg Convert (Best for stability)
            ffmpeg_cmd = [
                "ffmpeg", "-i", downloaded_temp,
                "-vn", "-acodec", "libmp3lame", "-q:a", "2",
                "-threads", "0", "-y", mp3_file
            ]
            proc = await asyncio.create_subprocess_exec(*ffmpeg_cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await proc.communicate()

            if os.path.exists(downloaded_temp):
                os.remove(downloaded_temp)

            return mp3_file, True

        except Exception as e:
            logger.error(f"Download Error: {e}")
            try:
                # Fallback Audio logic
                opts = {
                    **common_opts,
                    "format": "bestaudio",
                    "outtmpl": f"downloads/{videoid}.%(ext)s",
                    "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
                }
                res = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                return res, True
            except:
                return None, False
