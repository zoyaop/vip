import asyncio
import os
import re
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError

import config
from VIPMUSIC.utils.formatters import time_to_seconds

# --- API SEQUENTIAL ROTATION LOGIC ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0  # पहली की से शुरू करें

def get_youtube_client():
    """वर्तमान इंडेक्स वाली API Key का उपयोग करके क्लाइंट बनाता है"""
    global current_key_index
    if current_key_index >= len(API_KEYS):
        return None # सभी कीज़ खत्म हो गईं
    
    selected_key = API_KEYS[current_key_index]
    return build("youtube", "v3", developerKey=selected_key, static_discovery=False)

def switch_to_next_key():
    """कोटा खत्म होने पर अगली की पर स्विच करता है"""
    global current_key_index
    current_key_index += 1
    if current_key_index < len(API_KEYS):
        print(f"Quota Exceeded! Switching to API Key #{current_key_index + 1}")
        return True
    else:
        print("All API Keys are exhausted!")
        return False

# --- COOKIES FILE SETUP ---
cookie_txt_file = "cookies/cookies.txt"
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

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: 
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        while True: # Retry loop for switching keys
            youtube = get_youtube_client()
            if not youtube: return None

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
                title = video_data["snippet"]["title"]
                thumb = video_data["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(video_data["contentDetails"]["duration"])
                
                return title, d_min, d_sec, thumb, vidid

            except HttpError as e:
                if e.resp.status == 403: # Quota Error
                    if switch_to_next_key():
                        continue # अगली की के साथ दोबारा कोशिश करें
                    else:
                        return None # कोई की नहीं बची
                return None

    async def slider(self, link: str, query_type: int, videoid: Union[bool, str] = None):
        while True:
            youtube = get_youtube_client()
            if not youtube: return None
            
            try:
                search_response = await asyncio.to_thread(
                    youtube.search().list(q=link, part="snippet", maxResults=10, type="video").execute
                )
                if not search_response.get("items"): return None
                
                result = search_response["items"][query_type]
                vidid = result["id"]["videoId"]
                title = result["snippet"]["title"]
                thumb = result["snippet"]["thumbnails"]["high"]["url"]
                
                video_res = await asyncio.to_thread(youtube.videos().list(part="contentDetails", id=vidid).execute)
                d_min, _ = self.parse_duration(video_res["items"][0]["contentDetails"]["duration"])
                
                return title, d_min, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403:
                    if switch_to_next_key():
                        continue
                    else:
                        return None
                return None

    # --- बाकी फंक्शन्स (डाउनलोड आदि) वैसे ही रहेंगे ---
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

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        opts = ["yt-dlp", "-g", "-f", "best[height<=?720][ext=mp4]/best", "--no-playlist", f"{link}"]
        if cookie_txt_file:
            opts.insert(1, "--cookies"), opts.insert(2, cookie_txt_file)
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        common_opts = {"quiet": True, "no_warnings": True, "geo_bypass": True}
        if cookie_txt_file: common_opts["cookiefile"] = cookie_txt_file

        def ytdl_download(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        if songvideo:
            opts = {**common_opts, "format": f"{format_id}+140/bestvideo+bestaudio", "merge_output_format": "mp4", "outtmpl": f"downloads/{title}.mp4"}
        elif songaudio:
            opts = {**common_opts, "format": "bestaudio/best", "outtmpl": f"downloads/{title}.mp3", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
        else:
            opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}

        filepath = await loop.run_in_executor(None, lambda: ytdl_download(opts))
        return filepath, True
