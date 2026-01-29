import asyncio
import glob
import os
import random
import re
from typing import Union, Tuple

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# API Key Rotation
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
        logger.warning(f"Quota exceeded → Switching to API Key #{current_key_index + 1}")
        return True
    logger.error("All YouTube API keys exhausted!")
    return False

# Random Cookie
def get_cookie_file():
    try:
        folder = f"{os.getcwd()}/cookies"
        cookies = glob.glob(os.path.join(folder, '*.txt'))
        return random.choice(cookies) if cookies else None
    except Exception:
        return None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.user_agent = (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )

    def parse_duration(self, duration: str) -> Tuple[str, int]:
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h = int(match.group(1) or 0)
        m = int(match.group(2) or 0)
        s = int(match.group(3) or 0)
        total_sec = h * 3600 + m * 60 + s
        dur_str = f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
        return dur_str, total_sec

    async def exists(self, link: str, videoid: Union[bool, str] = None) -> bool:
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
                        return (msg.text or msg.caption)[ent.offset:ent.offset + ent.length]
            if msg.caption_entities:
                for ent in msg.caption_entities:
                    if ent.type == MessageEntityType.TEXT_LINK:
                        return ent.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        vidid = link if videoid else re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
        vidid = vidid.group(1) if isinstance(vidid, re.Match) else vidid

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
                logger.error(f"API Error: {e}")
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res:
            return None, None
        title, dur_min, _, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": dur_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        cookie = get_cookie_file()
        cmd = [
            "yt-dlp", "-g", "-f", "best[height<=?720]",
            "--geo-bypass", "--user-agent", self.user_agent,
            "--extractor-args", "youtube:player_client=android,web,ios;skip=dash,hls",
            link
        ]
        if cookie:
            cmd.extend(["--cookies", cookie])
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        output = out.decode().strip()
        return (1, output.split("\n")[0] if output else "") if out else (0, err.decode())

    async def playlist(self, link: str, limit: int, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        cookie = get_cookie_file()
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f"yt-dlp {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [line.strip() for line in out.decode().split("\n") if line.strip()]

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
                dur_res = await asyncio.to_thread(
                    yt.videos().list(part="contentDetails", id=vidid).execute
                )
                dur_min, _ = self.parse_duration(dur_res["items"][0]["contentDetails"]["duration"])
                return title, dur_min, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key():
                    continue
                return None

    async def download(
        self,
        link: str,
        mystic=None,
        video: bool = False,          # ← Key: True for /vplay, False for /play
        videoid=None,
        songaudio=None,
        songvideo=None,
        format_id=None,
        title="music"
    ) -> Tuple[Union[str, None], bool, str]:
        """
        Returns: (file_path, success: bool, stream_type: "audio"|"video"|None)
        """
        if videoid:
            link = self.base + videoid if isinstance(videoid, str) else link

        cookie = get_cookie_file()
        common = {
            "quiet": True,
            "no_warnings": True,
            "geo_bypass": True,
            "nocheckcertificate": True,
            "user_agent": self.user_agent,
            "retries": 10,
            "fragment_retries": 10,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "web"],
                    "skip": ["dash", "hls", "translated_subs"]
                }
            },
            "format_sort": ["abr:160", "ext:webm", "codec:opus", "+size", "+br"]
        }
        if cookie:
            common["cookiefile"] = cookie

        loop = asyncio.get_running_loop()

        def ytdl_extract(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        try:
            if video or songvideo:  # /vplay mode
                opts = {
                    **common,
                    "format": "bestvideo[height<=?720]+251/140/bestaudio/best",
                    "outtmpl": f"downloads/v_{title}.%(ext)s",
                    "merge_output_format": "mp4"
                }
                path = await loop.run_in_executor(None, lambda: ytdl_extract(opts))
                return path, True, "video"

            else:  # /play → audio only
                opts = {
                    **common,
                    "format": "251/250/249/bestaudio[ext=webm]/bestaudio/best",
                    "outtmpl": f"downloads/a_{title}.%(ext)s",
                    # No postprocessor → keep native opus/webm (best for 2026 pytgcalls/ntgcalls)
                }
                path = await loop.run_in_executor(None, lambda: ytdl_extract(opts))
                return path, True, "audio"

        except Exception as e:
            logger.error(f"Download error: {e}", exc_info=True)
            return None, False, None
