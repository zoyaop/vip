# ============== VIP MUSIC BOT - FULL FAST MP3 DOWNLOAD EDITION ==============
# Hinglish + Fast Download 2026 Style | Queue + Player Perfect

import asyncio
import os
import random
import glob
import subprocess
from collections import deque

from pyrogram import filters
from pyrogram.types import Message

from VIPMUSIC import app, LOGGER
from VIPMUSIC.utils.youtube import YouTubeAPI   # tera YouTubeAPI class (niche diya hai update)
from config import API_KEY  # agar chahiye to

logger = LOGGER(__name__)

# =================== GLOBAL QUEUE & LOCK ===================
queues = {}          # chat_id → asyncio.Queue
now_playing = {}     # chat_id → current song dict
player_locks = {}    # chat_id → asyncio.Lock

def get_queue(chat_id: int):
    if chat_id not in queues:
        queues[chat_id] = asyncio.Queue()
    return queues[chat_id]

def get_lock(chat_id: int):
    if chat_id not in player_locks:
        player_locks[chat_id] = asyncio.Lock()
    return player_locks[chat_id]

# =================== FAST DOWNLOAD FUNCTION ===================
async def fast_download_mp3(
    link: str,
    title: str = "song",
    videoid: bool = False,
    user_id=None,
    chat_id=None
) -> tuple[str | None, bool]:
    """
    Sabse tez MP3 download – direct audio + aria2c + concurrent fragments
    """
    if videoid:
        link = f"https://www.youtube.com/watch?v={link}"

    loop = asyncio.get_running_loop()

    # Cookies for 403 fix
    cookie_file = None
    try:
        cookie_folder = f"{os.getcwd()}/cookies"
        txt_files = glob.glob(os.path.join(cookie_folder, '*.txt'))
        if txt_files:
            cookie_file = random.choice(txt_files)
            logger.info(f"Using cookie: {os.path.basename(cookie_file)}")
    except Exception as e:
        logger.warning(f"Cookie nahi mila: {e}")

    # Common yt-dlp options – SPEED KING
    common_opts = {
        "quiet": True,
        "no_warnings": True,
        "geo_bypass": True,
        "nocheckcertificate": True,
        "continuedl": True,
        "retries": 15,
        "fragment_retries": 10,
        "concurrent_fragment_downloads": 12,          # 8-16 best range (fast internet pe 16 bhi daal sakte)
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "web", "default"],
            }
        },
    }

    # aria2c check & enable (sabse bada speed booster)
    aria2c_available = False
    try:
        subprocess.run(["aria2c", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        aria2c_available = True
        common_opts["external_downloader"] = "aria2c"
        common_opts["external_downloader_args"] = [
            "-j", "16", "-x", "16", "-s", "16", "-k", "1M",
            "--summary-interval=0", "--file-allocation=none"
        ]
        logger.info("Aria2c mila → Full speed multi-connection ON 🔥")
    except:
        logger.info("Aria2c nahi hai → normal mode (thoda slow)")

    # curl_cffi for better impersonation (optional but helpful)
    try:
        import curl_cffi
        common_opts["impersonate"] = "chrome124"  # latest chrome 2026 style
    except ImportError:
        pass

    if cookie_file:
        common_opts["cookiefile"] = cookie_file

    # Final opts for MP3
    opts = {
        **common_opts,
        "format": "bestaudio[ext=m4a]/bestaudio/best",   # best audio first
        "outtmpl": f"downloads/{title.replace('/', '_')}.%(ext)s",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "0",           # 0 = best (~320kbps), ya "320" fixed
        }],
        "keepvideo": False,
    }

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = await loop.run_in_executor(None, lambda: ydl.extract_info(link, download=False))
            filename = await loop.run_in_executor(None, lambda: ydl.prepare_filename(info))
            await loop.run_in_executor(None, lambda: ydl.download([link]))

        if os.path.exists(filename.replace(".webm", ".mp3").replace(".m4a", ".mp3")):
            final_file = filename.rsplit(".", 1)[0] + ".mp3"
        else:
            final_file = filename

        if os.path.exists(final_file):
            logger.info(f"Fast MP3 success: {final_file}")
            return final_file, True
        return None, False

    except Exception as e:
        logger.error(f"Download crash: {e}")
        return None, False

# =================== /play COMMAND ===================
@app.on_message(filters.command(["play", "p", "song"]))
async def play_cmd(client, message: Message):
    chat_id = message.chat.id
    if not chat_id:
        return await message.reply("Group mein hi chalega bhai!")

    query = " ".join(message.command[1:]) if len(message.command) > 1 else None

    if not query:
        return await message.reply("Gaana naam ya link daal do yaar 😭")

    yt = YouTubeAPI()
    track = await yt.track(query)
    if not track:
        return await message.reply("YouTube pe nahi mila bhai... sahi link daal")

    song_data = {
        "title": track["title"],
        "vidid": track["vidid"],
        "duration": track["duration_min"],
        "thumb": track["thumb"],
        "link": track["link"],
        "requested_by": message.from_user.id,
        "username": message.from_user.username or message.from_user.first_name
    }

    q = get_queue(chat_id)
    await q.put(song_data)

    position = q.qsize()

    if position == 1 and chat_id not in now_playing:
        asyncio.create_task(play_next(chat_id))
        text = "🔥 **Shuru ho raha hai abhi!**"
    else:
        text = f"🎶 **Queue mein # {position} pe daal diya**"

    await message.reply(
        f"**{song_data['title']}**\n"
        f"⏳ {song_data['duration']} | Requested by: {song_data['username']}\n\n"
        f"{text}"
    )

# =================== PLAYER LOOP ===================
async def play_next(chat_id: int):
    lock = get_lock(chat_id)
    async with lock:
        while True:
            q = get_queue(chat_id)
            if q.empty():
                # Queue khatam
                await stop_vc(chat_id)  # tera stop function
                now_playing.pop(chat_id, None)
                await app.send_message(chat_id, "🥳 Queue khatam! Agla gaana daalo")
                break

            song = await q.get()
            now_playing[chat_id] = song

            try:
                msg = await app.send_message(
                    chat_id,
                    f"⚡ **Fast download chal raha hai...** {song['title']}\nThoda wait (5-20 sec max)"
                )

                file_path, success = await fast_download_mp3(
                    song["vidid"],
                    title=song["title"],
                    videoid=True
                )

                if not success or not file_path:
                    await msg.edit(f"Download fail: {song['title']}\nNext try kar rahe...")
                    continue

                await msg.edit(f"🎧 **Playing now:** {song['title']}")

                # Tera play function (PyTgCalls / pyro voice)
                await play_in_voice_chat(
                    chat_id=chat_id,
                    file_path=file_path,
                    title=song["title"],
                    duration=song["duration"],
                    thumb=song["thumb"],
                    requested_by=song["requested_by"]
                )

                if os.path.exists(file_path):
                    os.remove(file_path)

            except Exception as e:
                logger.error(f"Player error {chat_id}: {e}")
                await app.send_message(chat_id, "Kuch gadbad... next gaana")

            finally:
                q.task_done()

# =================== HELPERS (Tum change kar lena) ===================
async def play_in_voice_chat(**kwargs):
    # Yeh tera asli VC play karne wala function (PyTgCalls ya pyro)
    pass

async def stop_vc(chat_id):
    # VC leave / stop
    pass

# =================== BONUS: /queue command (optional) ===================
@app.on_message(filters.command("queue"))
async def show_queue(client, message):
    chat_id = message.chat.id
    if chat_id not in queues or get_queue(chat_id).empty():
        return await message.reply("Queue khali hai bhai!")

    q = get_queue(chat_id)
    items = []
    async for i, item in enumerate(q._queue, 1):  # peek
        items.append(f"{i}. {item['title']} ({item['duration']})")

    text = "**Current Queue:**\n" + "\n".join(items)
    if chat_id in now_playing:
        text = f"**Now Playing:** {now_playing[chat_id]['title']}\n\n" + text

    await message.reply(text)
