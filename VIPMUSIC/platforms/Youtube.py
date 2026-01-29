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

logging.getLogger('googleapiclient.discovery_cache').setLevel(logging.ERROR)

def get_youtube_client():
    if not config.API_KEY:
        return None
    keys = config.API_KEY.split(",") if "," in config.API_KEY else [config.API_KEY]
    selected_key = random.choice(keys).strip()
    try:
        return build("youtube", "v3", developerKey=selected_key, static_discovery=False)
    except:
        return None

def parse_duration(duration):
    pattern = re.compile(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?')
    match = pattern.match(duration)
    if not match: return 0, "00:00"
    h, m, s = [int(match.group(i) or 0) for i in range(1, 4)]
    total = h * 3600 + m * 60 + s
    return total, (f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}")

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"

    def extract_id(self, url):
        match = re.search(r"(?:v=|\/|embed\/|youtu.be\/)([0-9A-Za-z_-]{11})", url)
        return match.group(1) if match else None

    async def url(self, message_1: Message):
        messages = [message_1, message_1.reply_to_message] if message_1.reply_to_message else [message_1]
        for m in messages:
            if m and m.entities:
                for e in m.entities:
                    if e.type == MessageEntityType.URL:
                        return (m.text or m.caption)[e.offset : e.offset + e.length]
            if m and m.caption_entities:
                for e in m.caption_entities:
                    if e.type == MessageEntityType.TEXT_LINK: return e.url
        return None

    async def details(self, link: str, videoid=None):
        vid = videoid or self.extract_id(link)
        if not vid: return None
        
        # Method 1: Google API (Fast)
        client = get_youtube_client()
        if client:
            try:
                loop = asyncio.get_event_loop()
                res = await loop.run_in_executor(None, lambda: client.videos().list(part="snippet,contentDetails", id=vid).execute())
                if res["items"]:
                    item = res["items"][0]
                    dur_sec, dur_min = parse_duration(item["contentDetails"]["duration"])
                    return item["snippet"]["title"], dur_min, dur_sec, item["snippet"]["thumbnails"]["high"]["url"], vid
            except: pass # Agar API fail ho jaye toh niche wale method par jayega

        # Method 2: Fallback to yt-dlp (Slow but Reliable)
        try:
            ydl_opts = {"quiet": True, "no_warnings": True}
            with YoutubeDL(ydl_opts) as ydl:
                info = await asyncio.get_event_loop().run_in_executor(None, lambda: ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False))
                return info['title'], f"{info['duration']//60}:{info['duration']%60:02d}", info['duration'], info['thumbnail'], vid
        except: return None

    async def track(self, link, videoid=None):
        res = await self.details(link, videoid)
        if not res:
            # Empty dict return karein taaki 'NoneType' error na aaye
            return {"title": "Unknown", "duration_min": "00:00"}, None
        data = {"title": res[0], "link": self.base + res[4], "vidid": res[4], "duration_min": res[1], "thumb": res[3]}
        return data, res[4]

    async def playlist(self, link, limit, user_id, videoid=None):
        pid = link.split("list=")[1].split("&")[0] if "list=" in link else link
        client = get_youtube_client()
        if client:
            try:
                res = await asyncio.get_event_loop().run_in_executor(None, lambda: client.playlistItems().list(part="contentDetails", playlistId=pid, maxResults=int(limit)).execute())
                return [i["contentDetails"]["videoId"] for i in res.get("items", [])]
            except: pass
        return []

    async def slider(self, query, query_type, videoid=None):
        client = get_youtube_client()
        if client:
            try:
                res = await asyncio.get_event_loop().run_in_executor(None, lambda: client.search().list(q=query, part="id", maxResults=10, type="video").execute())
                vid = res["items"][query_type]["id"]["videoId"]
                return await self.details(vid, videoid=True)
            except: pass
        return None

    async def download(self, link, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None):
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        def dl(opts):
            with YoutubeDL(opts) as ydl:
                return ydl.prepare_filename(ydl.extract_info(link, download=True))

        opts = {"quiet": True, "no_warnings": True, "geo_bypass": True}
        if songvideo:
            opts.update({"format": f"{format_id}+140", "outtmpl": f"downloads/{title}.mp4", "merge_output_format": "mp4"})
            return await loop.run_in_executor(None, lambda: dl(opts))
        elif songaudio:
            opts.update({"format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]})
            return await loop.run_in_executor(None, lambda: dl(opts))
        elif video:
            if await is_on_off(config.YTDOWNLOADER):
                opts.update({"format": "(bestvideo[height<=720])+(bestaudio[ext=m4a])", "outtmpl": "downloads/%(id)s.%(ext)s"})
                return await loop.run_in_executor(None, lambda: dl(opts)), True
            else:
                proc = await asyncio.create_subprocess_shell(f"yt-dlp -g -f 'best[height<=720]' {link}", stdout=asyncio.subprocess.PIPE)
                out, _ = await proc.communicate()
                return out.decode().split("\n")[0], None
        else:
            opts.update({"format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"})
            return await loop.run_in_executor(None, lambda: dl(opts)), True

    # Dummy methods for compatibility
    async def title(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[0] if res else "Unknown"
    async def duration(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[1] if res else "00:00"
    async def thumbnail(self, link, videoid=None):
        res = await self.details(link, videoid)
        return res[3] if res else None
    async def formats(self, link, videoid=None):
        if videoid: link = self.base + link
        try:
            with YoutubeDL({"quiet": True}) as ydl:
                r = await asyncio.get_event_loop().run_in_executor(None, lambda: ydl.extract_info(link, download=False))
                return [{"format": f.get("format"), "format_id": f.get("format_id"), "ext": f.get("ext")} for f in r["formats"] if "dash" not in str(f.get("format")).lower()], link
        except: return [], link
