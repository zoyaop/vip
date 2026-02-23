# Copyright (C) 2024 by THE-VIP-BOY-OP@Github, <https://github.com/THE-VIP-BOY-OP>.
# This file is part of <https://github.com/THE-VIP-BOY-OP/VIP-MUSIC> project.

import asyncio
import threading
import uvloop
import pyrogram
from flask import Flask
from pyrogram import Client, idle
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import ChatWriteForbidden, PeerIdInvalid
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

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running"

def run():
    app.run(host="0.0.0.0", port=8000, debug=False)

class VIPBot(Client):
    def __init__(self):
        LOGGER(__name__).info("Starting Bot")
        super().__init__(
            "VIPMUSIC",
            api_id=config.API_ID,
            api_hash=config.API_HASH,
            bot_token=config.BOT_TOKEN,
            ipv6=False, # <--- यहाँ IPv4 सुनिश्चित करने के लिए 'ipv6=False' जोड़ा गया है
        )

    async def start(self):
        await super().start()
        get_me = await self.get_me()
        self.username = get_me.username
        self.id = get_me.id
        self.name = get_me.first_name + " " + (get_me.last_name or "")
        self.mention = get_me.mention

        button = InlineKeyboardMarkup(
            [[InlineKeyboardButton(text="๏ ᴀᴅᴅ ᴍᴇ ɪɴ ɢʀᴏᴜᴘ ๏", url=f"https://t.me/{self.username}?startgroup=true")]]
        )

        if config.LOG_GROUP_ID:
            try:
                # ID ko number (int) mein badalna zaroori hai
                LOGGER_ID = int(config.LOG_GROUP_ID)
                
                await self.send_photo(
                    chat_id=LOGGER_ID,
                    photo=config.START_IMG_URL,
                    caption=f"╔════❰𝐖𝐄𝐋𝐂𝐎𝐌𝐄❱════❍⊱❁۪۪\n║\n║┣⪼🥀𝐁𝐨𝐭 𝐒𝐭𝐚𝐫𝐭𝐞𝐝 𝐁𝐚𝐛𝐲🎉\n║\n║┣⪼ {self.name}\n║\n║┣⪼🎈𝐈𝐃:- `{self.id}` \n║\n║┣⪼🎄@{self.username} \n║ \n║┣⪼💖𝐓𝐡𝐚𝐧𝐤𝐬 𝐅𝐨𝐫 𝐔𝐬𝐢𝐧𝐠😍\n║\n╚════════════════❍⊱❁",
                    reply_markup=button,
                )
            except PeerIdInvalid:
                LOGGER(__name__).error("Log Group Error: Bot ko log group mein admin banayein aur wahan /start likhein!")
            except ChatWriteForbidden:
                LOGGER(__name__).error("Log Group Error: Bot ke paas message bhejne ki permission nahi hai!")
            except Exception as e:
                LOGGER(__name__).error(f"Unexpected Log Group Error: {e}")
        else:
            LOGGER(__name__).warning("LOG_GROUP_ID set nahi hai, startup message skip kar diya.")

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
                        BotCommand("play", "❥ Play the requested song"),
                        BotCommand("stop", "❥ Stop the song"),
                        BotCommand("pause", "❥ Pause the song"),
                        BotCommand("resume", "❥ Resume the song"),
                        BotCommand("skip", "❥ Skip the current song"),
                    ],
                    scope=BotCommandScopeAllGroupChats(),
                )
            except Exception as e:
                LOGGER(__name__).error(f"Failed to set bot commands: {e}")

        LOGGER(__name__).info(f"MusicBot Started as {self.name}")

async def anony_boot():
    bot = VIPBot()
    await bot.start()
    await idle()

if __name__ == "__main__":
    t = threading.Thread(target=run)
    t.daemon = True
    t.start()
    asyncio.run(anony_boot())
