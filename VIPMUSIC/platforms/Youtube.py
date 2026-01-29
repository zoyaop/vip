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

logger = LOGGER(__name__)

# --- API ROTATION ---
API_KEYS = [k.strip() for k in config.API_KEY.split(",")]
current_key_index = 0

def get_youtube_client():
    global current_key_index
    if current_key_index >= len(API_KEYS): return None
    return build("youtube", "v3", developerKey=API_KEYS[current_key_index], static_discovery=False)

def switch_key():
    global current_key_index
    current_key_index += 1
    return current_key_index < len(API_KEYS)

class YouTubeAPI:
    def __init__(self):
        self.base = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.listbase = "https://youtube.com/playlist?list="
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        self.proxies = [] # Scraped proxies store honge yahan

    async def scrape_proxies(self):
        """Scrapes fresh HTTP proxies from multiple sources"""
        proxy_urls = [
            "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
            "https://www.proxy-list.download/api/v1/get?type=https",
            "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt"
        ]
        new_proxies = []
        async with aiohttp.ClientSession() as session:
            for url in proxy_urls:
                try:
                    async with session.get(url, timeout=10) as resp:
                        if resp.status == 200:
                            text = await resp.text()
                            new_proxies.extend(text.splitlines())
                except Exception as e:
                    logger.error(f"Proxy Scrape Error from {url}: {e}")
        
        # Filter valid looking proxies
        self.proxies = [p.strip() for p in new_proxies if ":" in p]
        random.shuffle(self.proxies)
        logger.info(f"Total Scraped Proxies: {len(self.proxies)}")

    async def get_proxy(self):
        """Get a random proxy, scrape if list is empty"""
        if not self.proxies:
            await self.scrape_proxies()
        if self.proxies:
            proxy = random.choice(self.proxies)
            return f"http://{proxy}"
        return None

    def parse_duration(self, duration):
        match = re.search(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        h, m, s = int(match.group(1) or 0), int(match.group(2) or 0), int(match.group(3) or 0)
        total_seconds = h * 3600 + m * 60 + s
        return (f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"), total_seconds

    async def video(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base + link
        cookie = self.get_cookie_file()
        proxy = await self.get_proxy()
        
        opts = [
            "yt-dlp", "-4", "--geo-bypass", "-g", "-f", "best[height<=?720]",
            "--user-agent", self.user_agent,
            "--referer", "https://www.youtube.com/"
        ]
        if cookie: opts.extend(["--cookies", cookie])
        if proxy: opts.extend(["--proxy", proxy])
        opts.append(link)

        proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
        
        # Agar proxy fail ho jaye toh bina proxy ke try karein
        if not stdout:
            opts = [o for o in opts if "--proxy" not in o] # Remove proxy
            proc = await asyncio.create_subprocess_exec(*opts, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            stdout, stderr = await proc.communicate()

        return (1, stdout.decode().split("\n")[0]) if stdout else (0, stderr.decode())

    async def download(self, link: str, mystic, video=None, videoid=None, songaudio=None, songvideo=None, format_id=None, title=None) -> str:
        if videoid: link = self.base + link
        loop = asyncio.get_running_loop()

        def ytdl_run(opts):
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(link, download=True)
                return ydl.prepare_filename(info)

        # Retry logic with Proxy Rotation
        for attempt in range(3): # 3 baar koshish karega alag IPs se
            proxy = await self.get_proxy()
            cookie = self.get_cookie_file()
            
            common_opts = {
                "quiet": True, "no_warnings": True, "geo_bypass": True,
                "source_address": "0.0.0.0",
                "user_agent": self.user_agent,
                "proxy": proxy,
                "cookiefile": cookie,
                "extractor_args": {"youtube": {"player_client": ["android", "web"], "skip": ["dash", "hls"]}}
            }

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
                logger.warning(f"Attempt {attempt+1} failed with proxy {proxy}: {e}")
                if "403" in str(e) or "Forbidden" in str(e):
                    if proxy in self.proxies: self.proxies.remove(proxy.replace("http://", ""))
                    continue # Try with next proxy
                return str(e), False

        return "Failed after multiple proxy rotations.", False

    def get_cookie_file(self):
        try:
            folder_path = f"{os.getcwd()}/cookies"
            txt_files = glob.glob(os.path.join(folder_path, '*.txt'))
            return random.choice(txt_files) if txt_files else None
        except: return None
