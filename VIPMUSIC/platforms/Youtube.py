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

# Discovery cache warnings band karne ke liye
logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

def get_youtube_client():
    # Check if multiple keys are provided (comma separated)
    if isinstance(config.API_KEY, str):
        if "," in config.API_KEY:
            # Comma se split karke random key uthayega
            api_keys = [k.strip() for k in config.API_KEY.split(",")]
            selected_key = random.choice(api_keys)
        else:
            selected_key = config.API_KEY
    elif isinstance(config.API_KEY, list):
        selected_key = random.choice(config.API_KEY)
    else:
        selected_key = config.API_KEY

    try:
        return build(
            "youtube", 
            "v3", 
            developerKey=selected_key, 
            static_discovery=False
        )
    except Exception as e:
        print(f"Error creating YouTube client: {e}")
        return None

def parse_duration(duration):
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration)
    if not match: return 0, "00:00"
    hours, minutes, seconds = [int(match.group(i) or 0) for i in range(1, 4)]
    total_seconds = hours * 3600 + minutes * 60 + seconds
    return total_seconds, (f"{hours}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes}:{seconds:02d}")

def cookies():
    folder_path = f"{os.getcwd()}/cookies"
    txt_files = glob.glob(os.path.join(folder_path, "*.txt"))
    return f"cookies/{os.path.basename(random.choice(txt_files))}" if txt_files else None

def get_ytdl_options(ytdl_opts, commamdline=True):
    cookie_file = cookies()
    if commamdline and isinstance(ytdl_opts, list):
        if os.getenv("TOKEN_ALLOW") == "True": ytdl_opts += ["--username", "oauth2", "--password", "''"]
        elif cookie_file: ytdl_opts += ["--cookies", cookie_file]
    elif not commamdline and isinstance(ytdl_opts, dict):
        if os.getenv("TOKEN_ALLOW") == "True": ytdl_opts.update({"username": "oauth2", "password": ""})
        elif cookie_file: ytdl_opts["cookiefile"] = cookie_file
    return ytdl_opts

async def shell_cmd(cmd):
    proc = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await proc.communicate()
    return out.decode("utf-8") if out else ""

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def extract_id(self, url):
        match = re.search(r"(?:v=|\/|embed\/|youtu.be\/)([0-9A-Za-z_-]{11})", url)
        return match.group(1) if match else None

    async def exists(self, link: str, videoid=None):
        return True if videoid or re.search(self.regex, link) else False

    async def url(self, message_1: Message):
        messages = [message_1, message_1.reply_to_message] if message_1.reply_to_message else [message_1]
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        return (message.text or message.caption)[entity.offset : entity.offset + entity.length]
            if message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK: return entity.url
        return None

    async def details(self, link: str, videoid=None):
        vid = videoid or self.extract_id(link)
        if not vid: return None
        client = get_youtube_client()
        loop = asyncio.get_event_loop()
        try:
            res = await loop.run_in_executor(None, lambda: client.videos().list(part="snippet,contentDetails", id=vid).execute())
            if not res["items"]: return None
            item = res["items"][0]
            dur_sec, dur_min = parse_duration(item["contentDetails"]["duration"])
            return item["snippet"]["title"], dur_min, dur_sec, item["snippet"]["thumbnails"]["high"]["url"], vid
        except: return None

    async def title(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[0] if res else "Unknown"

    async def duration(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[1] if res else "00:00"

    async def thumbnail(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[3] if res else None

    async def video(self, link, videoid=None):
        if videoid: link = self.base + link
        cmd = get_ytdl_options(["yt-dlp", "-g", "-f", "best[height<=720]", link])
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        out, err = await proc.communicate()
        return (1, out.decode().split("\n")[0]) if out else (0, err.decode())

    async def playlist(self, link, limit, user_id, videoid=None):
        pid = link.split("list=")[1].split("&")[0] if "list=" in link else link
        client = get_youtube_client()
        loop = asyncio.get_event_loop()
        try:
            res = await loop.run_in_executor(None, lambda: client.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=int(limit)).execute())
            return [item["contentDetails"]["videoId"] for item in res.get("items", [])]
        except: return []

    async def track(self, link, videoid=None):
        res = await self.details(link, videoid)
        if not res: return None, None
        return {"title": res[0], "link": self.base + res[4], "vidid": res[4], "duration_min": res[1], "thumb": res[3]}, res[4]

    async def formats(self, link, videoid=None):
        if videoid: link = self.base + link
        ydl = YoutubeDL(get_ytdl_options({"quiet": True}, False))
        loop = asyncio.get_event_loop()
        formats_available = []
        try:
            r = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=False))
            for f in r["formats"]:
                if "dash" not in str(f.get("format")).lower():
                    formats_available.append({"format": f.get("format"), "filesize": f.get("filesize"), "format_id": f.get("format_id"), "ext": f.get("ext"), "format_note": f.get("format_note"), "yturl": link})
        except: pass
        return formats_available, link

    async def slider(self, query, query_type, videoid=None):
        client = get_youtube_client()
        loop = asyncio.get_event_loop()
        try:
            res = await loop.run_in_executor(None, lambda: client.search().list(q=query, part="id", maxResults=10, type="video").execute())
            return await self.details(res["items"][query_type]["id"]["videoId"], videoid=True)
        except: return None

    async def download(self, link, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        def dl(opts):
            with YoutubeDL(get_ytdl_options(opts, False)) as ydl:
                return ydl.prepare_filename(ydl.extract_info(link, download=True))

        if songvideo:
            fpath = f"downloads/{title}.mp4"
            await loop.run_in_executor(None, lambda: dl({"format": f"{format_id}+140", "outtmpl": fpath, "merge_output_format": "mp4", "quiet": True}))
            return fpath
        elif songaudio:
            fpath = f"downloads/{title}.mp3"
            await loop.run_in_executor(None, lambda: dl({"format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}], "quiet": True}))
            return fpath
        elif video:
            if await is_on_off(config.YTDOWNLOADER):
                return await loop.run_in_executor(None, lambda: dl({"format": "(bestvideo[height<=720])+(bestaudio[ext=m4a])", "outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True})), True
            res = await shell_cmd(f"yt-dlp -g -f 'best[height<=720]' {link}")
            return res.split("\n")[0], None
        return await loop.run_in_executor(None, lambda: dl({"format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s", "quiet": True})), True
