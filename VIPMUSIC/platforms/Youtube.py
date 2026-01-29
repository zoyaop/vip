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
from AnonMusic import LOGGER
from AnonMusic.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# ─── API KEY ROTATION ────────────────────────────────────────────────
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
        logger.warning(f"YouTube API quota exhausted. Switched to key #{current_key_index + 1}")
        return True
    logger.error("All YouTube API keys are exhausted!")
    return False


# ─── COOKIE SELECTION ────────────────────────────────────────────────
def get_cookie_file():
    try:
        folder = os.path.join(os.getcwd(), "cookies")
        txt_files = glob.glob(os.path.join(folder, "*.txt"))
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

    def parse_duration(self, duration: str) -> tuple[str, int]:
        """Convert ISO 8601 duration to HH:MM:SS and total seconds"""
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration or "PT0S")
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        total = h * 3600 + m * 60 + s
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        return dur_str, total

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
        if videoid:
            link = self.base + link
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
            if not youtube:
                return None

            try:
                if not vidid:
                    search = await asyncio.to_thread(
                        youtube.search()
                        .list(q=link, part="id", maxResults=1, type="video")
                        .execute
                    )
                    if not search.get("items"):
                        return None
                    vidid = search["items"][0]["id"]["videoId"]

                video_data = await asyncio.to_thread(
                    youtube.videos()
                    .list(part="snippet,contentDetails", id=vidid)
                    .execute
                )
                if not video_data.get("items"):
                    return None

                item = video_data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])

                return title, d_min, d_sec, thumb, vidid

            except HttpError as e:
                if e.resp.status == 403 and switch_key():
                    continue
                logger.exception("YouTube API error in details()")
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res:
            return None, None
        title, d_min, d_sec, thumb, vidid = res
        data = {
            "title": title,
            "link": self.base + vidid,
            "vidid": vidid,
            "duration_min": d_min,
            "thumb": thumb,
        }
        return data, vidid

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            youtube = get_youtube_client()
            if not youtube:
                return None

            try:
                search = await asyncio.to_thread(
                    youtube.search()
                    .list(q=link, part="snippet", maxResults=10, type="video")
                    .execute
                )
                if not search.get("items"):
                    return None

                item = search["items"][query_type]
                vidid = item["id"]["videoId"]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]

                v_res = await asyncio.to_thread(
                    youtube.videos().list(part="contentDetails", id=vidid).execute
                )
                d_min, _ = self.parse_duration(v_res["items"][0]["contentDetails"]["duration"])

                return title, d_min, thumb, vidid

            except HttpError as e:
                if e.resp.status == 403 and switch_key():
                    continue
                logger.exception("YouTube API error in slider()")
                return None

    async def playlist(self, link: str, limit: int, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link

        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""

        cmd = (
            f'yt-dlp {cookie_arg} -i --get-id --flat-playlist '
            f'--playlist-end {limit} --skip-download "{link}"'
        )

        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        ids = [k.strip() for k in stdout.decode().splitlines() if k.strip()]
        return ids

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link

        cookie = get_cookie_file()
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720]", "--geo-bypass", link]
        if cookie:
            opts.extend(["--cookies", cookie])

        proc = await asyncio.create_subprocess_exec(
            *opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if stdout:
            return 1, stdout.decode().splitlines()[0].strip()
        return 0, stderr.decode()

    async def download(
        self,
        link: str,
        mystic=None,           # can be used for progress if you have one
        video=None,
        videoid=None,
        songaudio=None,
        songvideo=None,
        format_id=None,
        title=None,
    ) -> tuple[str, bool]:
        """
        Returns: (filepath or error message, success: bool)
        """
        if videoid:
            link = self.base + link

        loop = asyncio.get_running_loop()
        cookie = get_cookie_file()

        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "retries": 10,
            "fragment_retries": 10,
            "continuedl": True,
            "concurrent_fragment_downloads": 3,
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "extractor_args": {
                "youtube": {
                    "player_client": ["default", "-ios", "-android_sdkless", "-web_safari"]
                }
            },
        }

        if cookie:
            common_opts["cookiefile"] = cookie

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                try:
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)
                except Exception as e:
                    logger.exception("yt-dlp download failed")
                    raise e

        try:
            if songvideo:
                opts = {
                    **common_opts,
                    "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                    "outtmpl": f"downloads/{title}.%(ext)s",
                    "merge_output_format": "mp4",
                }
                path = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                return path, True

            elif songaudio:
                opts = {
                    **common_opts,
                    "format": "bestaudio/best",
                    "outtmpl": f"downloads/{title}.%(ext)s",
                    "postprocessors": [
                        {
                            "key": "FFmpegExtractAudio",
                            "preferredcodec": "mp3",
                            "preferredquality": "192",
                        }
                    ],
                }
                path = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                return path, True

            else:
                # fallback generic download
                opts = {
                    **common_opts,
                    "format": "bestaudio/best",
                    "outtmpl": "downloads/%(id)s.%(ext)s",
                }
                path = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                return path, True

        except Exception as e:
            logger.exception("Download failed")
            return str(e), False
