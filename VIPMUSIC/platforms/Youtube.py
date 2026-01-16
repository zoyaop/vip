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

import config # सुनिश्चित करें कि config.py सही से इम्पोर्ट हो रहा है
from BIGFM.utils.formatters import time_to_seconds

# --- API ROTATION LOGIC ---
# config.py में API_KEY = "key1, key2, key3" इस तरह से लिखें
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]

def get_youtube_client():
    """रैंडम तरीके से एक API Key चुनकर क्लाइंट बनाता है"""
    selected_key = random.choice(API_KEYS)
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
        else:
            return errorz.decode("utf-8")
    return out.decode("utf-8")

# --- COOKIES FILE SETUP ---
cookie_txt_file = "BIGFM/cookies.txt"
if not os.path.exists(cookie_txt_file):
    cookie_txt_file = None

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
        if videoid: vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None
        
        youtube = get_youtube_client() # हर बार नई Key का मौका
        
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
            if e.resp.status == 403: # Quota Exceeded
                print("One API Key Quota Finished, Retrying with another...")
                return await self.details(link, videoid) # दोबारा कोशिश करें (नई key के साथ)
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
        opts = ["yt-dlp", "-g", "-f", "best[height<=?480][ext=mp4]/best", "--no-playlist", "--geo-bypass", f"{link}"]
        if cookie_txt_file:
            opts.insert(1, "--cookies")
            opts.insert(2, cookie_txt_file)
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie_cmd = f"--cookies {cookie_txt_file}" if cookie_txt_file else ""
        playlist = await shell_cmd(f"yt-dlp {cookie_cmd} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}")
        return [k for k in playlist.split("\n") if k != ""]

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
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
            if e.resp.status == 403:
                return await self.slider(link, query_type, videoid)
            return None

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        common_opts = {"geo_bypass": True, "nocheckcertificate": True, "quiet": True, "no_warnings": True}
        if cookie_txt_file: common_opts["cookiefile"] = cookie_txt_file

        def audio_dl():
            ydl_opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, False)
                path = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if not os.path.exists(path): ydl.download([link])
                return path

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
