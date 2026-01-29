import asyncio
import glob
import os
import random
import re
import aiohttp
from typing import Union

import yt_dlp
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from googleapiclient.discovery import build 
from googleapiclient.errors import HttpError

import config
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

logger = LOGGER(__name__)

# --- API ROTATION LOGIC ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
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
        logger.warning(f"YouTube Quota Finished. Switching to Key #{current_key_index + 1}")
        return True
    return False

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        
        # Proxy Pool
        self.proxies = []
        # Start Background Proxy Scraper
        asyncio.create_task(self.continuous_proxy_scraper())

    async def continuous_proxy_scraper(self):
        """Har 5-10 second mein fresh proxies scrape karne ke liye loop"""
        proxy_sources = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=1000&country=all&ssl=all&anonymity=all",
            "https://www.proxy-list.download/api/v1/get?type=http",
            "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
            "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt"
        ]
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    for url in proxy_sources:
                        try:
                            async with session.get(url, timeout=5) as resp:
                                if resp.status == 200:
                                    content = await resp.text()
                                    new_proxies = content.splitlines()
                                    self.proxies = list(set(self.proxies + [p.strip() for p in new_proxies if ":" in p]))
                        except:
                            continue
                if len(self.proxies) > 500:
                    self.proxies = self.proxies[-300:]
            except Exception as e:
                logger.error(f"Scraper Error: {e}")
            await asyncio.sleep(5)

    def get_proxy(self):
        return f"http://{random.choice(self.proxies)}" if self.proxies else None

    def get_cookie_file(self):
        try:
            folder_path = f"{os.getcwd()}/cookies"
            txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
            return random.choice(txt_files) if txt_files else None
        except: return None

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        total_seconds = hours * 3600 + minutes * 60 + seconds
        duration_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        return duration_str, total_seconds

    # --- MISSING URL METHOD FIXED ---
    async def url(self, message: Message) -> Union[str, None]:
        messages = [message]
        if message.reply_to_message:
            messages.append(message.reply_to_message)
        for msg in messages:
            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        return (msg.text or msg.caption)[entity.offset : entity.offset + entity.length]
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        return bool(re.search(self.regex, link))

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: 
            vidid = link
        else:
            match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11})", link)
            vidid = match.group(1) if match else None

        while True:
            youtube = get_youtube_client()
            if not youtube: return None
            try:
                if not vidid:
                    search = await asyncio.to_thread(youtube.search().list(q=link, part="id", maxResults=1, type="video").execute)
                    if not search.get("items"): return None
                    vidid = search["items"][0]["id"]["videoId"]
                
                video_data = await asyncio.to_thread(youtube.videos().list(part="snippet,contentDetails", id=vidid).execute)
                if not video_data.get("items"): return None
                
                item = video_data["items"][0]
                title = item["snippet"]["title"]
                thumb = item["snippet"]["thumbnails"]["high"]["url"]
                d_min, d_sec = self.parse_duration(item["contentDetails"]["duration"])
                return title, d_min, d_sec, thumb, vidid
            except HttpError as e:
                if e.resp.status == 403 and switch_key(): continue
                return None

    async def track(self, link: str, videoid: Union[bool, str] = None):
        res = await self.details(link, videoid)
        if not res: return None, None
        title, d_min, d_sec, thumb, vidid = res
        return {"title": title, "link": self.base + vidid, "vidid": vidid, "duration_min": d_min, "thumb": thumb}, vidid

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = self.get_cookie_file()
        proxy = self.get_proxy()
        
        opts = ["yt-dlp", "-4", "--geo-bypass", "-g", "-f", "best[height<=?720]", "--user-agent", self.user_agent, "--referer", "https://www.youtube.com/"]
        if cookie: opts.extend(["--cookies", cookie])
        if proxy: opts.extend(["--proxy", proxy])
        opts.append(link)
        
        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        
        # 403 Fallback: Retry with another IP
        if not stdout and "403" in stderr.decode():
            return await self.video(link)
        
        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        if videoid: link = self.listbase + link
        cookie = self.get_cookie_file()
        proxy = self.get_proxy()
        proxy_arg = f"--proxy {proxy}" if proxy else ""
        cookie_arg = f"--cookies {cookie}" if cookie else ""
        cmd = f'yt-dlp -4 {proxy_arg} {cookie_arg} -i --get-id --flat-playlist --playlist-end {limit} --skip-download "{link}"'
        playlist = await asyncio.create_subprocess_shell(cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, _ = await playlist.communicate()
        return [k.strip() for k in stdout.decode().split("\n") if k.strip()]

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()
        
        for attempt in range(5):
            proxy = self.get_proxy()
            cookie = self.get_cookie_file()
            common_opts = {
                "quiet": True, "no_warnings": True, "geo_bypass": True, "source_address": "0.0.0.0",
                "user_agent": self.user_agent, "proxy": proxy, "cookiefile": cookie, "nocheckcertificate": True,
                "extractor_args": {"youtube": {"player_client": ["android", "web"]}}
            }

            def ytdl_run(opts):
                with yt_dlp.YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(link, download=True)
                    return ydl.prepare_filename(info)

            try:
                if songvideo:
                    opts = {**common_opts, "format": f"{format_id}+140/bestvideo+bestaudio", "outtmpl": f"downloads/{title}.%(ext)s", "merge_output_format": "mp4"}
                elif songaudio:
                    opts = {**common_opts, "format": "bestaudio/best", "outtmpl": f"downloads/{title}.%(ext)s", "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}]}
                else:
                    opts = {**common_opts, "format": "bestaudio/best", "outtmpl": "downloads/%(id)s.%(ext)s"}

                downloaded_file = await loop.run_in_executor(None, lambda: ytdl_run(opts))
                return downloaded_file, True
            except Exception as e:
                if "403" in str(e): continue
                return str(e), False
        return "Failed after IP rotations", False
