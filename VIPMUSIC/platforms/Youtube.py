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

# --- SMART API ROTATION LOGIC ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
API_INDEX = 0 

# Path to cookies file if you decide to use one
COOKIE_PATH = "cookies.txt"

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
        err_msg = errorz.decode("utf-8").lower()
        if "unavailable videos are hidden" in err_msg:
            return out.decode("utf-8")
        # Ignore minor warnings but log potential bot detection
        if "sign in to confirm" in err_msg:
            print("ERROR: YouTube is requesting bot verification (Cookies needed).")
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

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        
        # ADDED Bypassing logic
        opts = [
            "yt-dlp", "-g", "-f", "best[height<=?480][ext=mp4]/best",
            "--no-playlist", "--geo-bypass",
            "--extractor-args", "youtube:player_client=web,android", # Bypasses some bot checks
        ]
        
        if os.path.exists(COOKIE_PATH):
            opts.extend(["--cookies", COOKIE_PATH])
            
        opts.append(link)
        
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, "")

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie_arg = f"--cookies {COOKIE_PATH}" if os.path.exists(COOKIE_PATH) else ""
        
        # Added extractor-args to playlist shell command
        cmd = f"yt-dlp {cookie_arg} --extractor-args 'youtube:player_client=web,android' -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        playlist = await shell_cmd(cmd)
        return [k for k in playlist.split("\n") if k != ""]

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        
        # Common options with bot-bypass headers
        common_opts = {
            "geo_bypass": True, 
            "nocheckcertificate": True, 
            "quiet": True, 
            "no_warnings": True,
            "extractor_args": {"youtube": {"player_client": ["web", "android"]}}
        }
        
        if os.path.exists(COOKIE_PATH):
            common_opts["cookiefile"] = COOKIE_PATH

        def audio_dl():
            ydl_opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, download=False)
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

            downloaded_file, status = await loop.run_in_executor(None, audio_dl), True
            return downloaded_file, status
        except Exception as e:
            print(f"Download Error: {e}")
            return None, False
