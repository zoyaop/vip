import asyncio
import glob
import os
import random
import re
import logging
from typing import Union
from googleapiclient.discovery import build
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from yt_dlp import YoutubeDL

import config
from VIPMUSIC.utils.database import is_on_off
from VIPMUSIC.utils.formatters import time_to_seconds

# Logging band karne ke liye taaki discovery cache warning na aaye
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

def get_youtube_client():
    try:
        # static_discovery=False lagane se 'file_cache' wala error nahi aayega
        return build(
            "youtube", 
            "v3", 
            developerKey=config.API_KEY, 
            static_discovery=False
        )
    except Exception as e:
        print(f"Error creating YouTube client: {e}")
        return None

def parse_duration(duration):
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration)
    if not match:
        return 0, "00:00"
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = int(match.group(3) or 0)
    total_seconds = hours * 3600 + minutes * 60 + seconds
    duration_str = f"{hours}:" if hours > 0 else ""
    duration_str += f"{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}"
    return total_seconds, duration_str

def cookies():
    folder_path = f"{os.getcwd()}/cookies"
    txt_files = glob.glob(os.path.join(folder_path, "*.txt"))
    if not txt_files:
        return None
    return f"cookies/{os.path.basename(random.choice(txt_files))}"

def get_ytdl_options(ytdl_opts, commamdline=True) -> Union[str, dict, list]:
    cookie_file = cookies()
    if commamdline:
        if isinstance(ytdl_opts, list):
            if os.getenv("TOKEN_ALLOW") == "True":
                ytdl_opts += ["--username", "oauth2", "--password", "''"]
            elif cookie_file:
                ytdl_opts += ["--cookies", cookie_file]
    else:
        if isinstance(ytdl_opts, dict):
            if os.getenv("TOKEN_ALLOW") == "True":
                ytdl_opts.update({"username": "oauth2", "password": ""})
            elif cookie_file:
                ytdl_opts["cookiefile"] = cookie_file
    return ytdl_opts

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    out, _ = await proc.communicate()
    return out.decode("utf-8") if out else ""

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.client = get_youtube_client()

    def extract_id(self, url):
        pattern = r"(?:v=|\/|embed\/|youtu.be\/)([0-9A-Za-z_-]{11})"
        match = re.search(pattern, url)
        return match.group(1) if match else None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if not videoid:
            videoid = self.extract_id(link)
        if not videoid: return None

        loop = asyncio.get_event_loop()
        try:
            search_response = await loop.run_in_executor(None, lambda: self.client.videos().list(
                part="snippet,contentDetails",
                id=videoid
            ).execute())
            if not search_response["items"]: return None
            item = search_response["items"][0]
            title = item["snippet"]["title"]
            thumbnail = item["snippet"]["thumbnails"]["high"]["url"]
            duration_sec, duration_min = parse_duration(item["contentDetails"]["duration"])
            return title, duration_min, duration_sec, thumbnail, videoid
        except Exception:
            return None

    async def title(self, link: str, videoid=None):
        res = await self.details(link, videoid)
        return res[0] if res else "Unknown"

    async def playlist(self, link, limit, user_id, videoid=None):
        playlist_id = link.split("list=")[1].split("&")[0] if "list=" in link else link
        loop = asyncio.get_event_loop()
        results = []
        try:
            response = await loop.run_in_executor(None, lambda: self.client.playlistItems().list(
                part="contentDetails",
                playlistId=playlist_id,
                maxResults=int(limit)
            ).execute())
            for item in response.get("items", []):
                results.append(item["contentDetails"]["videoId"])
        except Exception: pass
        return results

    async def track(self, link: str, videoid=None):
        res = await self.details(link, videoid)
        if not res: return None, None
        track_details = {
            "title": res[0],
            "link": self.base + res[4],
            "vidid": res[4],
            "duration_min": res[1],
            "thumb": res[3],
        }
        return track_details, res[4]

    async def slider(self, query: str, query_type: int, videoid=None):
        loop = asyncio.get_event_loop()
        try:
            search_response = await loop.run_in_executor(None, lambda: self.client.search().list(
                q=query,
                part="id,snippet",
                maxResults=10,
                type="video"
            ).execute())
            items = search_response.get("items", [])
            if not items: return None
            vidid = items[query_type]["id"]["videoId"]
            return await self.details(vidid, videoid=True)
        except Exception: return None

    async def download(self, link, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()

        def dl(opts):
            with YoutubeDL(get_ytdl_options(opts, False)) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        if songvideo:
            fpath = f"downloads/{title}.mp4"
            opts = {"format": f"{format_id}+140", "outtmpl": fpath, "merge_output_format": "mp4", "quiet": True}
            await loop.run_in_executor(None, lambda: dl(opts))
            return fpath
        elif songaudio:
            fpath = f"downloads/{title}.mp3"
            opts = {"format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}], "quiet": True}
            await loop.run_in_executor(None, lambda: dl(opts))
            return fpath
        elif video:
            if await is_on_off(config.YTDOWNLOADER):
                opts = {"format": "(bestvideo[height<=?720])+(bestaudio[ext=m4a])", "outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True}
                return await loop.run_in_executor(None, lambda: dl(opts)), True
            else:
                res = await shell_cmd(f"yt-dlp -g -f 'best[height<=720]' {link}")
                return res.split("\n")[0], None
        else:
            opts = {"format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True}
            return await loop.run_in_executor(None, lambda: dl(opts)), True
