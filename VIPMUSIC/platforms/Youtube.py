import asyncio
import os
import re
import aiohttp
import yt_dlp
from typing import Union, Tuple
from pathlib import Path
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message
from dotenv import load_dotenv

# Project Specific Imports
from VIPMUSIC import LOGGER
from VIPMUSIC.utils.formatters import time_to_seconds

# Environment variables load karein
load_dotenv()

try:
    from py_yt import VideosSearch
except ImportError:
    from youtubesearchpython.__future__ import VideosSearch

# --- CONFIGURATION ---
API_URL = os.getenv("API_URL", "https://shrutibots.site")
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "downloads")
# Download folder automatic ban jayega agar nahi hai
Path(DOWNLOAD_DIR).mkdir(parents=True, exist_ok=True)

class YouTubeAPI:
    def __init__(self):
        self.base_url = "https://www.youtube.com/watch?v="
        self.regex = r"(?:youtube\.com|youtu\.be)"
        self.list_base = "https://youtube.com/playlist?list="

    async def _fetch_from_api(self, video_id: str, mode: str) -> Union[str, None]:
        """
        Private method: API se audio/video download karne ke liye.
        Isme redirect aur error handling optimized hai.
        """
        file_ext = "mp3" if mode == "audio" else "mp4"
        file_path = Path(DOWNLOAD_DIR) / f"{video_id}.{file_ext}"

        # Agar file pehle se hai to download skip karein
        if file_path.exists():
            return str(file_path)

        try:
            # 10 minute ka timeout (badi files ke liye)
            timeout = aiohttp.ClientTimeout(total=600, connect=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                
                # Step 1: Download Token mangna
                params = {"url": video_id, "type": mode}
                async with session.get(f"{API_URL}/download", params=params) as resp:
                    if resp.status != 200:
                        LOGGER.error(f"API Downloader Error: Status {resp.status}")
                        return None
                    data = await resp.json()
                    token = data.get("download_token")
                
                if not token:
                    LOGGER.error("API Error: Token nahi mila.")
                    return None

                # Step 2: Streaming Download
                stream_url = f"{API_URL}/stream/{video_id}?type={mode}&token={token}"
                async with session.get(stream_url, allow_redirects=True) as file_resp:
                    if file_resp.status != 200:
                        return None
                    
                    with open(file_path, "wb") as f:
                        async for chunk in file_resp.content.iter_chunked(32768): # 32KB chunks
                            f.write(chunk)

                if file_path.exists() and file_path.stat().st_size > 0:
                    return str(file_path)
                    
        except Exception as e:
            LOGGER.error(f"Download Exception: {str(e)}")
            if file_path.exists():
                file_path.unlink() # Kharab file delete karein
        return None

    async def exists(self, link: str, videoid: Union[bool, str] = None):
        if videoid:
            link = self.base_url + link
        return bool(re.search(self.regex, link))

    async def url(self, message: Message) -> Union[str, None]:
        """Message ya Reply se YouTube link nikalne ke liye"""
        messages = [message]
        if message.reply_to_message:
            messages.append(message.reply_to_message)
        
        for msg in messages:
            text = msg.text or msg.caption
            if not text: continue

            if msg.entities:
                for entity in msg.entities:
                    if entity.type == MessageEntityType.URL:
                        return text[entity.offset : entity.offset + entity.length]
            if msg.caption_entities:
                for entity in msg.caption_entities:
                    if entity.type == MessageEntityType.TEXT_LINK:
                        return entity.url
        return None

    async def details(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base_url + link
        search = VideosSearch(link, limit=1)
        res = (await search.next())["result"][0]
        return (
            res["title"],
            res["duration"],
            int(time_to_seconds(res["duration"])),
            res["thumbnails"][0]["url"].split("?")[0],
            res["id"]
        )

    async def download(
        self,
        link: str,
        mystic,
        video: bool = False,
        videoid: Union[bool, str] = None,
        **kwargs
    ) -> Tuple[Union[str, None], bool]:
        """Entry point for downloading audio/video"""
        if videoid:
            link = self.base_url + link
        
        # ID nikalna link se
        v_id = link.split('v=')[-1].split('&')[0] if 'v=' in link else link
        mode = "video" if video else "audio"
        
        try:
            await mystic.edit_text(f"📥 **Downloading {mode}...**\n\n**Video ID:** `{v_id}`")
        except:
            pass
        
        file_path = await self._fetch_from_api(v_id, mode)
        
        if file_path:
            return file_path, True
        return None, False

    async def playlist(self, link, limit, user_id, videoid: Union[bool, str] = None):
        """Playlist se video IDs nikalne ke liye"""
        if videoid: link = self.list_base + link
        cmd = f"yt-dlp -i --get-id --flat-playlist --playlist-end {limit} '{link}'"
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, _ = await proc.communicate()
        return [vid for vid in stdout.decode().split("\n") if vid]

    async def track(self, link: str, videoid: Union[bool, str] = None):
        if videoid: link = self.base_url + link
        search = VideosSearch(link, limit=1)
        res = (await search.next())["result"][0]
        track_details = {
            "title": res["title"],
            "link": res["link"],
            "vidid": res["id"],
            "duration_min": res["duration"],
            "thumb": res["thumbnails"][0]["url"].split("?")[0],
        }
        return track_details, res["id"]
