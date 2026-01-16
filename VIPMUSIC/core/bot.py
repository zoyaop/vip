# Copyright (C) 2024 by THE-VIP-BOY-OP@Github, <https://github.com/THE-VIP-BOY-OP>.
# This file is part of <https://github.com/THE-VIP-BOY-OP/VIP-MUSIC> project,
# and is released under the "GNU v3.0 License Agreement".
# Please see <https://github.com/THE-VIP-BOY-OP/VIP-MUSIC/blob/master/LICENSE>
# All rights reserved.

import asyncio
import threading
import uvloop
from flask import Flask
import pyrogram 
from pyrogram import Client, idle
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatWriteForbidden, PeerIdInvalid, FloodWait
from pyrogram.types import (
    BotCommand,
    BotCommandScopeAllChatAdministrators,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

import config
from ..logging import LOGGER

uvloop.install()

# Flask app initialize
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run():
    app.run(host="0.0.0.0", port=8000, debug=False)

# VIPBot Class
class VIPBot(Client):
    def __init__(self):
        LOGGER(__name__).info("Starting Bot")
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
        self.name = get_me.first_name + " " + (get_me.last_name or "")
        self.mention = get_me.mention

        button = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text="๏ ᴀᴅᴅ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ ๏",
                        url=f"https://t.me/{self.username}?startgroup=true",
                    )
                ]
            ]
        )

        if config.LOG_GROUP_ID:
            try:
                # --- यहाँ सुधार किया गया है: पहले ग्रुप को ढूँढना (Resolve Peer) ---
                await self.get_chat(config.LOG_GROUP_ID)
                
                await self.send_photo(
                    config.LOG_GROUP_ID,
                    photo=config.START_IMG_URL,
                    caption=f"╔════❰𝐖𝐄𝐋𝐂𝐎𝐌𝐄❱════❍⊱❁۪۪\n║\n║┣⪼🥀𝐁𝐨𝐭 𝐒𝐭𝐚𝐫𝐭𝐞𝐝 𝐁𝐚𝐛𝐲🎉\n║\n║┣⪼ {self.name}\n║\n║┣⪼🎈𝐈𝐃:- `{self.id}` \n║\n║┣⪼🎄@{self.username} \n║ \n║┣⪼💖𝐓𝐡𝐚𝐧𝐤𝐬 𝐅𝐨𝐫 𝐔𝐬𝐢𝐧𝐠😍\n║\n╚════════════════❍⊱❁",
                    reply_markup=button,
                )
            except PeerIdInvalid:
                LOGGER(__name__).error(f"❌ Error: LOG_GROUP_ID ({config.LOG_GROUP_ID}) invalid. Bot ko group mein add karke admin banayein!")
            except ChatWriteForbidden:
                LOGGER(__name__).error(f"❌ Error: Bot log group mein message nahi bhej sakta. Admin banayein!")
            except Exception as e:
                LOGGER(__name__).error(f"❌ Unexpected error in Log Group: {e}")
        else:
            LOGGER(__name__).warning("LOG_GROUP_ID set nahi hai.")

        # Commands setup
        if config.SET_CMDS:
            try:
                await self.set_bot_commands(
                    commands=[
                        BotCommand("start", "Start the bot"),
                        BotCommand("help", "Get the help menu"),
                        BotCommand("ping", "Check if the bot is alive or dead"),
                    ],
                    scope=BotCommandScopeAllPrivateChats(),
                )
                await self.set_bot_commands(
                    commands=[
                        BotCommand("play", "Start playing requested song"),
                        BotCommand("stop", "Stop the current song"),
                        BotCommand("pause", "Pause the current song"),
                        BotCommand("resume", "Resume the paused song"),
                        BotCommand("queue", "Check the queue of songs"),
                        BotCommand("skip", "Skip the current song"),
                        BotCommand("volume", "Adjust the music volume"),
                        BotCommand("lyrics", "Get lyrics of the song"),
                    ],
                    scope=BotCommandScopeAllGroupChats(),
                )
                await self.set_bot_commands(
                    commands=[
                        BotCommand("start", "❥ Start the bot"),
                        BotCommand("ping", "❥ Check the ping"),
                        BotCommand("help", "❥ Get help"),
                        BotCommand("vctag", "❥ Tag all for voice chat"),
                        BotCommand("stopvctag", "❥ Stop tagging for VC"),
                        BotCommand("tagall", "❥ Tag all members by text"),
                        BotCommand("cancel", "❥ Cancel the tagging"),
                        BotCommand("settings", "❥ Get the settings"),
                        BotCommand("reload", "❥ Reload the bot"),
                        BotCommand("play", "❥ Play the requested song"),
                        BotCommand("vplay", "❥ Play video along with music"),
                        BotCommand("end", "❥ Empty the queue"),
                        BotCommand("playlist", "❥ Get the playlist"),
                        BotCommand("stop", "❥ Stop the song"),
                        BotCommand("lyrics", "❥ Get the song lyrics"),
                        BotCommand("song", "❥ Download the requested song"),
                        BotCommand("video", "❥ Download the requested video song"),
                        BotCommand("sudolist", "❥ Check the sudo list"),
                        BotCommand("owner", "❥ Check the owner"),
                        BotCommand("update", "❥ Update bot"),
                        BotCommand("gstats", "❥ Get stats of the bot"),
                        BotCommand("repo", "❥ Check the repo"),
                    ],
                    scope=BotCommandScopeAllChatAdministrators(),
                )
            except Exception as e:
                LOGGER(__name__).error(f"Failed to set bot commands: {e}")

        LOGGER(__name__).info(f"MusicBot Started as {self.name}")

# Define the async boot function
async def anony_boot():
    bot = VIPBot()
    await bot.start()
    await idle()

if __name__ == "__main__":
    LOGGER(__name__).info("Starting Flask server...")
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    LOGGER(__name__).info("Starting VIPBot...")
    asyncio.run(anony_boot())
