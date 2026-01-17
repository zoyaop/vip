import asyncio
import threading
import uvloop
from flask import Flask
from pyrogram import Client, idle
from pyrogram.types import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from pyrogram.errors import PeerIdInvalid

# Yahan humne config.py ko connect kiya hai
import config 

# Basic Logging setup
import logging
logging.basicConfig(level=logging.INFO)
LOGGER = logging.getLogger("VIPMUSIC")

uvloop.install()
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot Chal Raha Hai Beta!"

def run_flask():
    # Flask server for 24/7 (Heroku/Render ke liye)
    app.run(host="0.0.0.0", port=8000)

class VIPBot(Client):
    def __init__(self):
        LOGGER.info("Bot Start ho raha hai... Thoda sabar karo!")
        super().__init__(
            "VIPMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
        )

    async def start(self):
        await super().start()
        get_me = await self.get_me()
        self.username = get_me.username
        self.id = get_me.id
        self.name = f"{get_me.first_name} {get_me.last_name or ''}"

        # Button setup
        button = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text="๏ ᴀᴅᴅ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ ๏", url=f"https://t.me/{self.username}?startgroup=true")]]
        )

        # LOG_GROUP_ID logic (Yahan se config connect ho raha hai)
        if config.LOG_GROUP_ID:
            try:
                # Group mein message bhejna
                await self.send_photo(
                    chat_id=config.LOG_GROUP_ID,
                    photo=config.START_IMG_URL,
                    caption=f"╔════❰𝐖𝐄𝐋𝐂𝐎𝐌𝐄❱════❍⊱❁۪۪\n║\n║┣⪼🥀𝐁𝐨𝐭 𝐒𝐭𝐚𝐫𝐭𝐞𝐝 𝐁𝐚𝐛𝐲🎉\n║\n║┣⪼ {self.name}\n║\n║┣⪼🎈𝐈𝐃:- `{self.id}` \n║\n║┣⪼🎄@{self.username} \n║ \n║┣⪼💖𝐓𝐡𝐚𝐧𝐤𝐬 𝐅𝐨𝐫 𝐔𝐬𝐢𝐧𝐠😍\n║\n╚════════════════❍⊱❁",
                    reply_markup=button,
                )
                LOGGER.info(f"Done! Log group mein startup message bhej diya gaya hai.")
            except PeerIdInvalid:
                LOGGER.error("Error: Bot ko log group mein Admin banao aur wahan /start likho!")
            except Exception as e:
                LOGGER.error(f"Kuch toh gadbad hai: {e}")

        # Auto-set commands
        if config.SET_CMDS:
            try:
                await self.set_bot_commands([
                    BotCommand("start", "Bot shuru karein"),
                    BotCommand("help", "Help menu dekhein"),
                    BotCommand("play", "Gaana bajayein"),
                ], scope=BotCommandScopeAllPrivateChats())
            except Exception as e:
                LOGGER.error(f"Commands set nahi ho paaye: {e}")

        LOGGER.info(f"MusicBot Started as @{self.username}")

async def anony_boot():
    bot = VIPBot()
    await bot.start()
    await idle()

if __name__ == "__main__":
    # Flask ko background thread mein chalayein
    t = threading.Thread(target=run_flask)
    t.daemon = True
    t.start()
    
    # Main Bot ko chalayein
    asyncio.run(anony_boot())
