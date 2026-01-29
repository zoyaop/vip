import asyncio
import os
import re
import random
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError

import config
from VIPMUSIC.utils.formatters import time_to_seconds

# --- API ROTATION LOGIC ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    selected_key = API_KEYS[current_key_index]
    return build("youtube", "v3", developerKey=selected_key, static_discovery=False)

def rotate_api_key():
    global current_key_index
    current_key_index = (current_key_index + 1) % len(API_KEYS)

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    out, errorz = await proc.communicate()
    if errorz:
        if "unavailable videos are hidden" in (errorz.decode("utf-8")).lower():
            return out.decode("utf-8")
        return errorz.decode("utf-8")
    return out.decode("utf-8")

# --- COOKIES FILE SETUP ---
cookie_txt_file = "VIPMUSIC/cookies.txt"
if not os.path.exists(cookie_txt_file):
    cookie_txt_file = None

# --- लेटेस्ट YT-DLP 403 BYPASS SETTINGS ---
YTDL_OPTIONS = {
    "quiet": True,
    "no_warnings": True,
    "geo_bypass": True,
    "nocheckcertificate": True,
    "user_agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 11; en_US) gzip",
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "ios"],
            "skip": ["dash", "hls"]
        }
    }
}
if cookie_txt_file:
    YTDL_OPTIONS["cookiefile"] = cookie_txt_file

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    # --- यह वो फंक्शन है जिसकी वजह से एरर आ रहा था ---
    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message: messages.append(message_1.reply_to_message)
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset : entity.offset + entity.length]
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None, retry=0):
        if retry >= len(API_KEYS): return None
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None
        
        youtube = get_youtube_client()
        try:
            if not vidid:
                search = await asyncio.to_thread(youtube.search().list(q=link, part="id", maxResults=1, type="video").execute)
                if not search.get("items"): return None
                vidid = search["items"][0]["id"]["videoId"]
            
            video_resp = await asyncio.to_thread(youtube.videos().list(part="snippet,contentDetails", id=vidid).execute)
            if not video_resp.get("items"): return None
            
            data = video_resp["items"][0]
            d_min, d_sec = self.parse_duration(data["contentDetails"]["duration"])
            return data["snippet"]["title"], d_min, d_sec, data["snippet"]["thumbnails"]["high"]["url"], vidid
        except HttpError as e:
            if e.resp.status in [403, 429]:
                rotate_api_key()
                return await self.details(link, videoid, retry + 1)
            return None

    async def title(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        return res[0] if res else "Unknown"

    async def duration(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        return res[1] if res else "00:00"

    async def thumbnail(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        return res[3] if res else None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        # 403 bypass logic with shell execution
        cookie_cmd = f"--cookies {cookie_txt_file}" if cookie_txt_file else ""
        opts = ["yt-dlp", "-g", "-f", "best[height<=?480][ext=mp4]/best", "--extractor-args", "youtube:player_client=android", "--user-agent", YTDL_OPTIONS["user_agent"], "--no-playlist", f"{link}"]
        if cookie_txt_file:
            opts.insert(1, "--cookies")
            opts.insert(2, cookie_txt_file)
            
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()

        def dl_logic():
            opts = YTDL_OPTIONS.copy()
            if songvideo:
                opts.update({"format": f"{format_id}+140/best", "outtmpl": f"downloads/{title}.%(ext)s", "merge_output_format": "mp4"})
            elif songaudio:
                opts.update({"format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
            else:
                opts.update({"format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"})
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        downloaded_file = await loop.run_in_executor(None, dl_logic)
        return (downloaded_file, True) if (songaudio or songvideo) else downloaded_file

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie_cmd = f"--cookies {cookie_txt_file}" if cookie_txt_file else ""
        playlist = await shell_cmd(f"yt-dlp {cookie_cmd} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}")
        return [k for k in playlist.split("\n") if k != ""]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        youtube = get_youtube_client()
        try:
            search_response = await asyncio.to_thread(youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute)
            if not search_response.get("items"): return None
            result = search_response["items"][query_type]
            vidid, title, thumb = result["id"]["videoId"], result["snippet"]["title"], result["snippet"]["thumbnails"]["high"]["url"]
            video_res = await asyncio.to_thread(youtube.videos().list(part="contentDetails", id=vidid).execute)
            d_min, _ = self.parse_duration(video_res["items"][0]["contentDetails"]["duration"])
            return title, d_min, thumb, vidid
        except Exception:
            return None
