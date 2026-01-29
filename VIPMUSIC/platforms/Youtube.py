import asyncio
import glob
import os
import random
import re
from typing import Union, Tuple, Optional, Dict, Any

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from VIPMUSIC import LOGGER
# from VIPMUSIC.utils.formatters import time_to_seconds   # ← uncomment if you still use it

logger = LOGGER(__name__)

# ─── API Key Rotation ───────────────────────────────────────
API_KEYS = [k.strip() for k in config.API_KEY.split(",") if k.strip()]
current_api_key_index = 0


def get_youtube_client() -> Optional[Any]:
    global current_api_key_index
    if current_api_key_index >= len(API_KEYS):
        return None
    return build(
        "youtube", "v3",
        developerKey=API_KEYS[current_api_key_index],
        static_discovery=False
    )


def switch_to_next_api_key() -> bool:
    global current_api_key_index
    current_api_key_index += 1
    if current_api_key_index < len(API_KEYS):
        logger.warning(f"Quota exceeded → switching to API key #{current_api_key_index + 1}")
        return True
    logger.error("All YouTube API keys exhausted!")
    return False


# ─── Cookie Helpers ─────────────────────────────────────────
def pick_random_cookie_file() -> Optional[str]:
    try:
        cookie_dir = os.path.join(os.getcwd(), "cookies")
        cookie_files = glob.glob(os.path.join(cookie_dir, "*.txt"))
        if not cookie_files:
            return None
        return random.choice(cookie_files)
    except Exception:
        return None


class YouTubeAPI:
    def __init__(self):
        self.base_url = "https://www.youtube.com/watch?v="
        self.playlist_base = "https://www.youtube.com/playlist?list="
        self.url_pattern = r"(?:youtube\.com|youtu\.be)"

    @staticmethod
    def parse_iso_duration(iso_duration: str) -> Tuple[str, int]:
        """ PT5M30S → "05:30", 330 """
        if not iso_duration:
            return "00:00", 0

        pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
        match = pattern.match(iso_duration)
        if not match:
            return "00:00", 0

        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)

        total_seconds = h * 3600 + m * 60 + s
        time_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        return time_str, total_seconds

    async def exists(self, url: str, is_videoid: Union[bool, str] = False) -> bool:
        if is_videoid:
            url = self.base_url + str(url)
        return bool(re.search(self.url_pattern, url, re.IGNORECASE))

    async def extract_url_from_message(self, message: Message) -> Optional[str]:
        messages_to_check = [message]
        if message.reply_to_message:
            messages_to_check.append(message.reply_to_message)

        for msg in messages_to_check:
            # Check inline URLs
            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        text = msg.text or msg.caption or ""
                        return text[entity.offset : entity.offset + entity.length]

            # Check text links (e.g. in captions)
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url

        return None

    async def get_video_details(
        self,
        query_or_url_or_id: str,
        is_videoid: Union[bool, str] = False
    ) -> Optional[Tuple[str, str, int, str, str]]:
        """ Returns: (title, duration_str, duration_sec, thumbnail, video_id) """

        if is_videoid:
            video_id = str(query_or_url_or_id)
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", query_or_url_or_id)
            video_id = match.group(1) if match else None

        while True:
            client = get_youtube_client()
            if not client:
                return None

            try:
                if not video_id:
                    # Search if no ID provided
                    search_res = await asyncio.to_thread(
                        client.search().list(
                            q=query_or_url_or_id,
                            part="id",
                            maxResults=1,
                            type="video"
                        ).execute()
                    )
                    if not search_res.get("items"):
                        return None
                    video_id = search_res["items"][0]["id"]["videoId"]

                # Get video details
                video_res = await asyncio.to_thread(
                    client.videos().list(
                        part="snippet,contentDetails",
                        id=video_id
                    ).execute()
                )

                if not video_res.get("items"):
                    return None

                item = video_res["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"].get("high", {}).get("url", "")
                dur_str, dur_sec = self.parse_iso_duration(item["contentDetails"]["duration"])

                return title, dur_str, dur_sec, thumb, video_id

            except HttpError as e:
                if e.resp.status == 403 and switch_to_next_api_key():
                    continue
                logger.exception("YouTube API error in get_video_details")
                return None

    async def download(
        self,
        url_or_id: str,
        mystic=None,                   # optional progress callback
        is_videoid: Union[bool, str] = False,
        songaudio: bool = False,
        songvideo: bool = False,
        format_id: Optional[str] = None,
        custom_title: Optional[str] = None
    ) -> Tuple[Optional[str], bool]:
        """
        Returns: (file_path or None, success: bool)
        """
        if is_videoid:
            url = self.base_url + str(url_or_id)
        else:
            url = url_or_id

        os.makedirs("downloads", exist_ok=True)

        cookie_path = pick_random_cookie_file()
        common_opts = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
        }
        if cookie_path:
            common_opts["cookiefile"] = cookie_path

        def execute_ytdl(ytdl_opts: dict) -> Tuple[Optional[str], bool]:
            try:
                with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                    return ydl.prepare_filename(info), True
            except Exception as e:
                logger.exception(f"yt-dlp failed → {url}\n{e}")
                return None, False

        loop = asyncio.get_running_loop()

        # ── Song + Video ─────────────────────────────────────
        if songvideo:
            title = custom_title or "video"
            opts = {
                **common_opts,
                "format": f"{format_id}+bestaudio/best" if format_id else "bestvideo[height<=?720]+bestaudio/best",
                "outtmpl": f"downloads/{title}.%(ext)s",
                "merge_output_format": "mp4",
            }
            path, success = await loop.run_in_executor(None, lambda: execute_ytdl(opts))
            return path, success

        # ── Song (Audio only → mp3) ──────────────────────────
        if songaudio:
            title = custom_title or "audio"
            opts = {
                **common_opts,
                "format": "ba[ext=m4a]/bestaudio/best",
                "outtmpl": f"downloads/{title}.%(ext)s",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",          # 128–320 possible
                }],
                "continuedl": True,
                "retries": 10,
                "fragment_retries": 10,
            }
            path, success = await loop.run_in_executor(None, lambda: execute_ytdl(opts))
            return path, success

        # ── Default (best audio, no conversion) ──────────────
        opts = {
            **common_opts,
            "format": "bestaudio/best",
            "outtmpl": "downloads/%(id)s.%(ext)s",
        }
        path, success = await loop.run_in_executor(None, lambda: execute_ytdl(opts))
        return path, success


    # You can add back / improve these methods later if needed:
    # async def track(...)
    # async def slider(...)
    # async def playlist(...)
