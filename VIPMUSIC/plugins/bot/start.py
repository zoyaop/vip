#
# Copyright (C) 2024 by THE-VIP-BOY-OP@Github, < https://github.com/THE-VIP-BOY-OP >.
#
# This file is part of < https://github.com/THE-VIP-BOY-OP/VIP-MUSIC > project,
# and is released under the MIT License.
# Please see < https://github.com/THE-VIP-BOY-OP/VIP-MUSIC/blob/master/LICENSE >
#
# All rights reserved.
#

import asyncio
import time
import random

from pyrogram import filters
from pyrogram.enums import ChatType, ParseMode, ChatAction
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message
from youtubesearchpython.__future__ import VideosSearch
from pyrogram.errors import RPCError

import config
from config import BANNED_USERS, START_IMG_URL
from strings import get_string
from VIPMUSIC import HELPABLE, Telegram, YouTube, app
from VIPMUSIC.misc import SUDOERS, _boot_
from VIPMUSIC.plugins.play.playlist import del_plist_msg
from VIPMUSIC.plugins.sudo.sudoers import sudoers_list
from VIPMUSIC.utils.database import (
    add_served_chat,
    add_served_user,
    blacklisted_chats,
    get_assistant,
    get_lang,
    get_userss,
    is_banned_user,
    is_on_off,
    is_served_private_chat,
)
from VIPMUSIC.utils.decorators.language import LanguageStart
from VIPMUSIC.utils.formatters import get_readable_time
from VIPMUSIC.utils.functions import MARKDOWN, WELCOMEHELP
from VIPMUSIC.utils.inline import alive_panel, private_panel, start_pannel

from .help import paginate_modules

loop = asyncio.get_running_loop()

@app.on_message(group=-1)
async def ban_new(client, message):
    user_id = (
        message.from_user.id if message.from_user and message.from_user.id else 777000
    )
    if await is_banned_user(user_id):
        try:
            await message.chat.ban_member(user_id)
            await message.reply_text("😳 You are Banned from this Bot.")
        except:
            pass


@app.on_message(filters.command(["start"]) & filters.private & ~BANNED_USERS)
@LanguageStart
async def start_comm(client, message: Message, _):
    chat_id = message.chat.id
    await add_served_user(message.from_user.id)
    
    # --- EFFECT: Emoji Reaction (Safe version) ---
    try:
        await message.react(random.choice(["🔥", "✨", "⚡", "❤️", "💎", "🌟"]))
    except:
        pass

    # --- EFFECT: Typing Action ---
    try:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
    except:
        pass

    if len(message.text.split()) > 1:
        name = message.text.split(None, 1)[1]
        if name[0:4] == "help":
            keyboard = InlineKeyboardMarkup(
                paginate_modules(0, HELPABLE, "help", close=True)
            )
            return await message.reply_photo(
                photo=START_IMG_URL,
                caption=_["help_1"],
                reply_markup=keyboard,
            )
            
        if name[0:3] == "sud":
            await sudoers_list(client=client, message=message, _=_)
            return

        if name[0:3] == "inf":
            m = await message.reply_text("🔎 ғᴇᴛᴄʜɪɴɢ ɪɴғᴏ!")
            query = f"https://www.youtube.com/watch?v={(str(name)).replace('info_', '', 1)}"
            results = VideosSearch(query, limit=1)
            res = (await results.next())["result"][0]
            searched_text = f"🔍 **ᴠɪᴅᴇᴏ ᴛʀᴀᴄᴋ ɪɴғᴏ**\n\n❇️ **ᴛɪᴛʟᴇ:** {res['title']}\n⏳ **ᴅᴜʀᴀᴛɪᴏɴ:** {res['duration']} Mins\n👀 **ᴠɪᴇᴡs:** `{res['viewCount']['short']}`\n🎥 **ᴄʜᴀɴɴᴇʟ:** {res['channel']['name']}"
            await m.delete()
            return await app.send_photo(
                chat_id, 
                photo=res["thumbnails"][0]["url"], 
                caption=searched_text, 
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🎥 ᴡᴀᴛᴄʜ", url=res['link']), InlineKeyboardButton("🔄 ᴄʟᴏsᴇ", callback_data="close")]])
            )

    else:
        # यहाँ से message_effect_id हटा दिया गया है ताकि TypeError न आए
        out = private_panel(_)
        await message.reply_photo(
            photo=config.START_IMG_URL,
            caption=_["start_2"].format(message.from_user.mention, app.mention),
            reply_markup=InlineKeyboardMarkup(out)
        )
        
        if await is_on_off(config.LOG):
            try:
                await app.send_message(
                    config.LOG_GROUP_ID, 
                    f"{message.from_user.mention} ʜᴀs sᴛᴀʀᴛᴇᴅ ᴛʜᴇ ʙᴏᴛ."
                )
            except: pass


@app.on_message(filters.command(["start"]) & filters.group & ~BANNED_USERS)
@LanguageStart
async def testbot(client, message: Message, _):
    try:
        await message.react("🚀")
    except:
        pass
        
    out = alive_panel(_)
    uptime = get_readable_time(int(time.time() - _boot_))
    await message.reply_photo(
        photo=config.START_IMG_URL,
        caption=_["start_7"].format(app.mention, uptime),
        reply_markup=InlineKeyboardMarkup(out),
    )
    await add_served_chat(message.chat.id)


@app.on_message(filters.new_chat_members, group=-1)
async def welcome(client, message: Message):
    chat_id = message.chat.id
    if config.PRIVATE_BOT_MODE == str(True):
        if not await is_served_private_chat(chat_id):
            await message.reply_text("ᴛʜɪs ʙᴏᴛ ɪs ɪɴ ᴘʀɪᴠᴀᴛᴇ ᴍᴏᴅᴇ. ᴄᴏɴᴛᴀᴄᴛ ᴏᴡɴᴇʀ.")
            return await app.leave_chat(chat_id)
    
    await add_served_chat(chat_id)
    for member in message.new_chat_members:
        try:
            language = await get_lang(chat_id)
            _ = get_string(language)
            if member.id == app.id:
                if message.chat.type != ChatType.SUPERGROUP:
                    await message.reply_text(_["start_5"])
                    return await app.leave_chat(chat_id)
                
                userbot = await get_assistant(chat_id)
                await message.reply_text(
                    _["start_2"].format(app.mention, userbot.username, userbot.id), 
                    reply_markup=InlineKeyboardMarkup(start_pannel(_))
                )
            
            elif member.id in config.OWNER_ID:
                await message.reply_text(_["start_3"].format(app.mention, member.mention))
            elif member.id in SUDOERS:
                await message.reply_text(_["start_4"].format(app.mention, member.mention))
        except:
            continue

__MODULE__ = "Boᴛ"
__HELP__ = """
<b>★ /stats</b> - Get Global Stats.
<b>★ /lyrics</b> - Search Lyrics.
<b>★ /song</b> - Download Music.
<b>★ /sudolist</b> - Check Admins.
"""
