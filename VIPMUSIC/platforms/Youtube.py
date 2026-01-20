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

# --- SMART API ROTATION LOGIC (ONLY API, NO COOKIES) ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
API_INDEX = 0 

def get_youtube_client():
    global API_INDEX
    selected_key = API_KEYS[API_INDEX]
    return build("youtube", "v3", developerKey=selected_key, static_discovery=False)

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
        return "" 
    return out.decode("utf-8")

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

    async def details(self, link: str, videoid: Union[bool, str] = None):
        global API_INDEX
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None
        
        for _ in range(len(API_KEYS)):
            youtube = get_youtube_client() 
            try:
                if not vidid:
                    search_response = await asyncio.to_thread(
                        youtube.search().list(q=link, part="id", maxResults=1, type="video").execute
                    )
                    if not search_response.get("items"): return None
                    vidid = search_response["items"][0]["id"]["videoId"]
                
                video_response = await asyncio.to_thread(
                    youtube.videos().list(part="snippet,contentDetails", id=vidid).execute
                )
                if not video_response.get("items"): return None
                video_data = video_response["items"][0]
                title, d_min, d_sec = video_data["snippet"]["title"], *self.parse_duration(video_data["contentDetails"]["duration"])
                return title, d_min, d_sec, video_data["snippet"]["thumbnails"]["high"]["url"], vidid
            
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    API_INDEX = (API_INDEX + 1) % len(API_KEYS)
                    continue 
                return None
            except Exception:
                return None
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
        # No Cookies used here
        opts = ["yt-dlp", "-g", "-f", "best[height<=?480][ext=mp4]/best", "--no-playlist", "--geo-bypass", f"{link}"]
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, "")

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        # No Cookies used here
        playlist = await shell_cmd(f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}")
        return [k for k in playlist.split("\n") if k != ""]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        global API_INDEX
        for _ in range(len(API_KEYS)):
            youtube = get_youtube_client()
            try:
                search_response = await asyncio.to_thread(
                    youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute
                )
                if not search_response.get("items"): return None
                result = search_response["items"][query_type]
                vidid, title, thumb = result["id"]["videoId"], result["snippet"]["title"], result["snippet"]["thumbnails"]["high"]["url"]
                
                video_res = await asyncio.to_thread(youtube.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(video_res["items"][0]["contentDetails"]["duration"])
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status in [403, 429]:
                    API_INDEX = (API_INDEX + 1) % len(API_KEYS)
                    continue
                return None
        return None

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        # Clean common_opts without cookies
        common_opts = {"geo_bypass": True, "nocheckcertificate": True, "quiet": True, "no_warnings": True}

        def audio_dl():
            ydl_opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, False)
                path = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if not os.path.exists(path): ydl.download([link])
                return path

        try:
            if songvideo:
                fpath = f"downloads/{title}.mp4"
                await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL({**common_opts, "format": f"{format_id}+140", "outtmpl": f"downloads/{title}", "merge_output_format": "mp4"}).download([link]))
                return fpath
            elif songaudio:
                fpath = f"downloads/{title}.mp3"
                await loop.run_in_executor(None, lambda: yt_dlp.YoutubeDL({**common_opts, "format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}).download([link]))
                return fpath

            downloaded_file = await loop.run_in_executor(None, audio_dl)
            return downloaded_file, True
        except Exception:
            return None, False
