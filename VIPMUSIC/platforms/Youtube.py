import asyncio
import os
import re
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build # Official Google API

from VIPMUSIC.utils.formatters import time_to_seconds

# --- CONFIGURATION ---
# Get your API KEY from https://console.cloud.google.com/
API_KEY = "AIzaSyCi7cuAr68B3xPxeXueL5ctrohUKN9vOkI" 

# Global instance of YouTube API
youtube = build("youtube", "v3", developerKey=API_KEY)

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

# Cookies handling for yt-dlp
cookies_file = "VIPMUSIC/cookies.txt"
if not os.path.exists(cookies_file):
    cookies_file = None

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="

    def parse_duration(self, duration):
        """Converts ISO 8601 duration (PT4M13S) to MM:SS and total seconds"""
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        
        total_seconds = hours * 3600 + minutes * 60 + seconds
        if hours > 0:
            duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        else:
            duration_str = f"{minutes:02d}:{seconds:02d}"
            
        return duration_str, total_seconds

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        if re.search(self.regex, link):
            return True
        return False

    async def url(self, message_1: Message) -> Union[str, None]:
        messages = [message_1]
        if message_1.reply_to_message:
            messages.append(message_1.reply_to_message)
        
        for message in messages:
            if message.entities:
                for entity in message.entities:
                    if entity.type == MessageEntityType.URL:
                        text = message.text or message.caption
                        return text[entity.offset : entity.offset + entity.length]
            elif message.caption_entities:
                for entity in message.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            vidid = link
        else:
            # Extract Video ID from URL
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        # If it's a search query instead of a link
        if not vidid:
            search_response = await asyncio.to_thread(
                youtube.search().list(q=link, part="id", maxResults=1, type="video").execute
            )
            if not search_response.get("items"):
                return None
            vidid = search_response["items"][0]["id"]["videoId"]

        # Fetch video details
        video_response = await asyncio.to_thread(
            youtube.videos().list(part="snippet,contentDetails", id=vidid).execute
        )
        
        if not video_response.get("items"):
            return None

        video_data = video_response["items"][0]
        title = video_data["snippet"]["title"]
        thumbnail = video_data["snippet"]["thumbnails"]["high"]["url"]
        duration_iso = video_data["contentDetails"]["duration"]
        
        duration_min, duration_sec = self.parse_duration(duration_iso)
        
        return title, duration_min, duration_sec, thumbnail, vidid

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
        if not res:
            return None, None
        
        title, duration_min, duration_sec, thumbnail, vidid = res
        track_details = {
            "title": title,
            "link": self.base + vidid,
            "vidid": vidid,
            "duration_min": duration_min,
            "thumb": thumbnail,
        }
        return track_details, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base + link
        
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720][width<=?1280]", f"{link}"]
        if cookies_file:
            opts.insert(1, "--cookies")
            opts.insert(2, cookies_file)

        proc = await asyncio.create_subprocess_exec(
            *opts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if stdout:
            return 1, stdout.decode().split("\n")[0]
        else:
            return 0, stderr.decode()

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid:
            link = self.listbase + link
        
        cookie_cmd = f"--cookies {cookies_file}" if cookies_file else ""
        playlist = await shell_cmd(
            f"yt-dlp {cookie_cmd} -i --get-id --flat-playlist --playlist-end {limit} --skip-download {link}"
        )
        try:
            result = [k for k in playlist.split("\n") if k != ""]
        except:
            result = []
        return result

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        search_response = await asyncio.to_thread(
            youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute
        )
        
        if not search_response.get("items"):
            return None

        result = search_response["items"][query_type]
        vidid = result["id"]["videoId"]
        title = result["snippet"]["title"]
        thumbnail = result["snippet"]["thumbnails"]["high"]["url"]
        
        # Need secondary call for duration
        video_res = await asyncio.to_thread(
            youtube.videos().list(part="contentDetails", id=vidid).execute
        )
        duration_iso = video_res["items"][0]["contentDetails"]["duration"]
        duration_min, _ = self.parse_duration(duration_iso)

        return title, duration_min, thumbnail, vidid

    async def download(
        self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None
    ) -> str:
        if videoid:
            link = self.base + link
        loop = asyncio.get_running_loop()

        common_opts = {
            "geo_bypass": True,
            "nocheckcertificate": True,
            "quiet": True,
            "no_warnings": True,
        }
        if cookies_file:
            common_opts["cookiefile"] = cookies_file

        def audio_dl():
            ydl_opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, False)
                path = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if not os.path.exists(path):
                    ydl.download([link])
                return path

        def video_dl():
            ydl_opts = {**common_opts, "format": "(bestvideo[height<=?720][width<=?1280][ext=mp4])+(bestaudio[ext=m4a])", "outtmpl": "downloads/%(id)s.%(ext)s"}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(link, False)
                path = os.path.join("downloads", f"{info['id']}.{info['ext']}")
                if not os.path.exists(path):
                    ydl.download([link])
                return path

        if songvideo:
            fpath = f"downloads/{title}.mp4"
            def sv_dl():
                with yt_dlp.YoutubeDL({**common_opts, "format": f"{format_id}+140", "outtmpl": f"downloads/{title}", "merge_output_format": "mp4"}) as ydl:
                    ydl.download([link])
            await loop.run_in_executor(None, sv_dl)
            return fpath

        elif songaudio:
            fpath = f"downloads/{title}.mp3"
            def sa_dl():
                with yt_dlp.YoutubeDL({**common_opts, "format": format_id, "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}) as ydl:
                    ydl.download([link])
            await loop.run_in_executor(None, sa_dl)
            return fpath

        if video:
            downloaded_file = await loop.run_in_executor(None, video_dl)
        else:
            downloaded_file = await loop.run_in_executor(None, audio_dl)
        
        return downloaded_file, True
