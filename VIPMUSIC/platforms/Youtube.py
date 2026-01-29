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

# Cookies logic
def get_cookie_file():
    try:
        folder = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(folder, '*.txt'))
        if not txt_files:
            logger.warning("Cookies folder mein koi .txt file nahi mila → fresh cookies daalo for better success")
            return None
        cookie = random.choice(txt_files)
        logger.info(f"Cookie use kar raha: {os.path.basename(cookie)}")
        return cookie
    except Exception as e:
        logger.error(f"Cookie load error: {e}")
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
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "continuedl": True,
            "retries": 15,
            "fragment_retries": 10,
        }

        # Impersonate optional – agar curl_cffi installed hai to use karo
        try:
            import curl_cffi
            common_opts["impersonate"] = "chrome"  # auto latest version lega
            logger.info("curl_cffi detected → impersonate 'chrome' enabled")
        except ImportError:
            logger.warning("curl_cffi not found → impersonate skipped (install 'yt-dlp[default,curl-cffi]' to enable)")

        if cookie:
            common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        downloaded_file = None
        success = False

        # Try 1: Normal attempt with safe format (prefer combined to avoid 403)
        try:
            if songvideo:
                opts = {
                    **common_opts,
                    "format": "best[ext=mp4][height<=720]/bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best",
                    "outtmpl": f"downloads/{title}.%(ext)s",
                    "merge_output_format": "mp4",
                }
            elif songaudio:
                opts = {
                    **common_opts,
                    "format": "bestaudio[ext=m4a]/bestaudio/best",
                    "outtmpl": f"downloads/{title}.%(ext)s",
                    "postprocessors": [{
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }]
                }
            else:
                opts = {
                    **common_opts,
                    "format": "best",
                    "outtmpl": "downloads/%(id)s.%(ext)s",
                }

            downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
            success = True
            logger.info(f"Download successful: {downloaded_file}")

        except Exception as e:
            logger.error(f"Primary download failed: {str(e)}")

        # Try 2: Super safe fallback (format 18 = 360p mp4, almost never 403)
        if not success:
            try:
                opts = {
                    **common_opts,
                    "format": "18",  # 360p mp4 – very stable in 2026
                    "outtmpl": f"downloads/{title or '%(id)s'}.%(ext)s",
                }
                # Remove merge/postprocessor as not needed
                opts.pop("merge_output_format", None)
                if "postprocessors" in opts:
                    del opts["postprocessors"]

                downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                success = True
                logger.info(f"Fallback to format 18 successful: {downloaded_file}")
            except Exception as fb_e:
                logger.error(f"Fallback failed too: {str(fb_e)}")

        return downloaded_file, success
