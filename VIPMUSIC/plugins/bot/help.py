#
# Copyright (C) 2026 by THE-VIP-BOY-OP@Github, < https://github.com/THE-VIP-BOY-OP >.
#
# This file is part of < https://github.com/THE-VIP-BOY-OP/VIP-MUSIC > project,
# and is released under the MIT License.
#
# All rights reserved.
# MODERN 2026 REDESIGN - CLEANER, FASTER, BETTER UI.
#

import re
from math import ceil
from typing import Union

from pyrogram import Client, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery

import config
from config import BANNED_USERS, START_IMG_URL
from strings import get_command, get_string, helpers
from VIPMUSIC import HELPABLE, app
from VIPMUSIC.utils.database import get_lang, is_commanddelete_on
from VIPMUSIC.utils.decorators.language import LanguageStart, languageCB
from VIPMUSIC.utils.inline.help import private_help_panel
from VIPMUSIC.utils.inline.start import start_pannel # Home button ke liye zaroori hai

### Configurations
HELP_COMMAND = get_command("HELP_COMMAND")
COLUMN_SIZE = 4
NUM_COLUMNS = 3
DONATE_LINK = "https://envs.sh/AeS.jpg"

class EqInlineKeyboardButton(InlineKeyboardButton):
    def __eq__(self, other): return self.text == other.text
    def __lt__(self, other): return self.text < other.text
    def __gt__(self, other): return self.text > other.text

def paginate_modules(page_n, module_dict, prefix, chat=None, close: bool = False):
    if not chat:
        modules = sorted([
            EqInlineKeyboardButton(
                x.__MODULE__,
                callback_data=f"{prefix}_module({x.__MODULE__.lower()},{page_n})",
            ) for x in module_dict.values()
        ])
    else:
        modules = sorted([
            EqInlineKeyboardButton(
                x.__MODULE__,
                callback_data=f"{prefix}_module({chat},{x.__MODULE__.lower()},{page_n})",
            ) for x in module_dict.values()
        ])

    pairs = [modules[i : i + NUM_COLUMNS] for i in range(0, len(modules), NUM_COLUMNS)]
    max_num_pages = ceil(len(pairs) / COLUMN_SIZE) if len(pairs) > 0 else 1
    modulo_page = page_n % max_num_pages

    if len(pairs) > COLUMN_SIZE:
        pairs = pairs[modulo_page * COLUMN_SIZE : COLUMN_SIZE * (modulo_page + 1)] + [
            (
                EqInlineKeyboardButton("❮", callback_data=f"{prefix}_prev({modulo_page - 1 if modulo_page > 0 else max_num_pages - 1})"),
                EqInlineKeyboardButton("🗑️ ᴄʟᴏsᴇ" if close else "🔙 ʙᴀᴄᴋ", callback_data="close" if close else "feature"),
                EqInlineKeyboardButton("❯", callback_data=f"{prefix}_next({modulo_page + 1})"),
            )
        ]
    else:
        pairs.append([EqInlineKeyboardButton("🗑️ ᴄʟᴏsᴇ" if close else "🔙 ʙᴀᴄᴋ", callback_data="close" if close else "feature")])
    return pairs

@app.on_message(filters.command(HELP_COMMAND) & filters.private & ~BANNED_USERS)
@app.on_callback_query(filters.regex("settings_back_helper") & ~BANNED_USERS)
async def helper_private(client: app, update: Union[types.Message, types.CallbackQuery]):
    is_callback = isinstance(update, types.CallbackQuery)
    chat_id = update.message.chat.id if is_callback else update.chat.id
    
    if is_callback:
        try: await update.answer()
        except: pass

    language = await get_lang(chat_id)
    _ = get_string(language)
    keyboard = InlineKeyboardMarkup(paginate_modules(0, HELPABLE, "help", close=not is_callback))

    if is_callback:
        await update.edit_message_text(_["help_1"], reply_markup=keyboard)
    else:
        if await is_commanddelete_on(chat_id):
            try: await update.delete()
            except: pass
        
        if START_IMG_URL:
            await update.reply_photo(photo=START_IMG_URL, caption=_["help_1"], reply_markup=keyboard)
        else:
            await update.reply_text(text=_["help_1"], reply_markup=keyboard)

@app.on_message(filters.command(HELP_COMMAND) & filters.group & ~BANNED_USERS)
@LanguageStart
async def help_com_group(client, message: Message, _):
    keyboard = private_help_panel(_)
    await message.reply_text(_["help_2"], reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex(r"help_(.*?)"))
async def help_button(client, query):
    mod_match = re.match(r"help_module\((.+?),(.+?)\)", query.data)
    prev_match = re.match(r"help_prev\((.+?)\)", query.data)
    next_match = re.match(r"help_next\((.+?)\)", query.data)
    back_match = re.match(r"help_back\((\d+)\)", query.data)
    
    language = await get_lang(query.message.chat.id)
    _ = get_string(language)
    top_text = _["help_1"]

    if mod_match:
        module, prev_page = mod_match.group(1), int(mod_match.group(2))
        text = f"**✨ ʜᴇʟᴘ ꜰᴏʀ: {HELPABLE[module].__MODULE__}**\n\n{HELPABLE[module].__HELP__}"
        key = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data=f"help_back({prev_page})"),
            InlineKeyboardButton("🗑️ ᴄʟᴏsᴇ", callback_data="close")
        ]])
        await query.message.edit(text=text, reply_markup=key, disable_web_page_preview=True)
    elif prev_match or next_match or back_match:
        page = int((prev_match or next_match or back_match).group(1))
        await query.message.edit(text=top_text, reply_markup=InlineKeyboardMarkup(paginate_modules(page, HELPABLE, "help")), disable_web_page_preview=True)
    await client.answer_callback_query(query.id)

# --- 2026 Dynamic Callback Handler for Sub-menus ---
@app.on_callback_query(filters.regex(r"^(music|management|tools)_callback") & ~BANNED_USERS)
@languageCB
async def dynamic_help_cb(client, cb: CallbackQuery, _):
    data = cb.data.split()
    category = data[0].split("_")[0] 
    sub_key = data[1] if len(data) > 1 else ""

    map_data = {
        "music": ("HELP_", "music"),
        "management": ("MHELP_", "management"),
        "tools": ("THELP_", "tools")
    }
    
    prefix, back_cmd = map_data.get(category)
    
    if sub_key == "ai": help_text = helpers.AI_1
    elif sub_key == "extra": help_text = helpers.EXTRA_1
    else:
        index = sub_key.replace("hb", "")
        help_text = getattr(helpers, f"{prefix}{index}", "Information not found.")

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(_["BACK_BUTTON"], callback_data=back_cmd)]])
    await cb.edit_message_text(help_text, reply_markup=keyboard)

@app.on_callback_query(filters.regex("feature"))
async def feature_callback(client: Client, cb: CallbackQuery):
    keyboard = [
        [InlineKeyboardButton("🚀 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ 🚀", url=f"https://t.me/{app.username}?startgroup=true")],
        [InlineKeyboardButton("🎵 ᴍᴜsɪᴄ", callback_data="music"), InlineKeyboardButton("🛡️ ɢᴜᴀʀᴅ", callback_data="management")],
        [InlineKeyboardButton("🛠️ ᴛᴏᴏʟs", callback_data="tools"), InlineKeyboardButton("🌌 ᴀʟʟ", callback_data="settings_back_helper")],
        [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="go_to_start")]
    ]
    text = f"**✨ ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ {app.mention} ʜᴇʟᴘ ᴄᴇɴᴛᴇʀ**\n\n**━━ ᴘᴏᴡᴇʀᴇᴅ ʙʏ 2026 ɴᴇᴜʀᴀʟ ᴇɴɢɪɴᴇ ━━**\n**⚡ ꜰᴀsᴛ | 🔒 sᴇᴄᴜʀᴇ | 🎧 ʜᴅ ᴀᴜᴅɪᴏ**\n\nᴄʟɪᴄᴋ ᴏɴ ᴛʜᴇ ʙᴜᴛᴛᴏɴs ʙᴇʟᴏᴡ ᴛᴏ sᴇᴇ ᴄᴏᴍᴍᴀɴᴅs."
    await cb.message.edit_text(text=text, reply_markup=InlineKeyboardMarkup(keyboard))

@app.on_callback_query(filters.regex("music"))
async def music_panel(client, cb):
    buttons = [
        ["Aᴅᴍɪɴ", "Aᴜᴛʜ", "B-ᴄᴀsᴛ"], ["Bʟ-ᴄʜᴀᴛ", "Bʟ-ᴜsᴇʀ", "ᴄ-ᴘʟᴀʏ"],
        ["ɢ-ʙᴀɴ", "ʟᴏᴏᴘ", "ᴍᴀɪɴᴛᴇɴ"], ["ᴘɪɴɢ", "ᴘʟᴀʏ", "sʜᴜꜰꜰʟᴇ"],
        ["sᴇᴇᴋ", "sᴏɴɢ", "sᴘᴇᴇᴅ"]
    ]
    kb = []
    for i, row in enumerate(buttons):
        kb.append([InlineKeyboardButton(text, callback_data=f"music_callback hb{i*3 + j + 1}") for j, text in enumerate(row)])
    kb.append([InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="feature")])
    await cb.message.edit("🎵 **ᴍᴜsɪᴄ ᴄᴏᴍᴍᴀɴᴅs ᴍᴇɴᴜ**", reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query(filters.regex("management"))
async def mgmt_panel(client, cb):
    kb = [
        [InlineKeyboardButton("🌟 ᴇxᴛʀᴀ", callback_data="management_callback extra")],
        [InlineKeyboardButton("🚫 ʙᴀɴ", callback_data="management_callback hb1"), InlineKeyboardButton("👞 ᴋɪᴄᴋ", callback_data="management_callback hb2"), InlineKeyboardButton("🔇 ᴍᴜᴛᴇ", callback_data="management_callback hb3")],
        [InlineKeyboardButton("📌 ᴘɪɴ", callback_data="management_callback hb4"), InlineKeyboardButton("👥 sᴛᴀꜰꜰ", callback_data="management_callback hb5"), InlineKeyboardButton("⚙️ sᴇᴛᴜᴘ", callback_data="management_callback hb6")],
        [InlineKeyboardButton("🧟 ᴢᴏᴍʙɪᴇ", callback_data="management_callback hb7"), InlineKeyboardButton("🎮 ɢᴀᴍᴇ", callback_data="management_callback hb8"), InlineKeyboardButton("🎭 ɪᴍᴘᴏsᴛᴇʀ", callback_data="management_callback hb9")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="feature")]
    ]
    await cb.message.edit("🛡️ **ᴍᴀɴᴀɢᴇᴍᴇɴᴛ ᴄᴏᴍᴍᴀɴᴅs ᴍᴇɴᴜ**", reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query(filters.regex("tools"))
async def tools_panel(client, cb):
    kb = [
        [InlineKeyboardButton("🤖 ᴄʜᴀᴛɢᴘᴛ", callback_data="tools_callback ai")],
        [InlineKeyboardButton("🔍 ɢᴏᴏɢʟᴇ", callback_data="tools_callback hb1"), InlineKeyboardButton("🎙️ ᴠᴏɪᴄᴇ", callback_data="tools_callback hb2"), InlineKeyboardButton("ℹ️ ɪɴꜰᴏ", callback_data="tools_callback hb3")],
        [InlineKeyboardButton("🎨 ꜰᴏɴᴛ", callback_data="tools_callback hb4"), InlineKeyboardButton("🔢 ᴍᴀᴛʜ", callback_data="tools_callback hb5"), InlineKeyboardButton("📣 ᴛᴀɢᴀʟʟ", callback_data="tools_callback hb6")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="feature")]
    ]
    await cb.message.edit("🛠️ **ᴜᴛɪʟɪᴛʏ & AI ᴛᴏᴏʟs ᴍᴇɴᴜ**", reply_markup=InlineKeyboardMarkup(kb))

@app.on_callback_query(filters.regex("about"))
async def about_callback(client: Client, cb: CallbackQuery):
    buttons = [
        [InlineKeyboardButton("👨‍💻 ᴅᴇᴠᴇʟᴏᴘᴇʀ", callback_data="developer"), InlineKeyboardButton("🚀 ꜰᴇᴀᴛᴜʀᴇs", callback_data="feature")],
        [InlineKeyboardButton("📘 ɢᴜɪᴅᴇ", callback_data="basic_guide"), InlineKeyboardButton("💎 ᴅᴏɴᴀᴛᴇ", callback_data="donate")],
        [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="go_to_start")]
    ]
    await cb.message.edit_text(
        f"**✨ {app.mention} ɪs ᴀ ᴘᴏᴡᴇʀꜰᴜʟ ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇʀ & ᴍᴜsɪᴄ ʙᴏᴛ.**\n\n● sᴘᴀᴍ protection\n● ᴜʟᴛʀᴀ HD ᴍᴜsɪᴄ\n● ᴀɪ powered tools\n● Custom Welcome & Rules",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

@app.on_callback_query(filters.regex("developer"))
async def dev_callback(client, cb):
    buttons = [
        [InlineKeyboardButton("🔰 ᴏᴡɴᴇʀ", user_id=config.OWNER_ID[0]), InlineKeyboardButton("📍 sᴜᴅᴏᴇʀs", url=f"https://t.me/{app.username}?start=sudo")],
        [InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="about")]
    ]
    await cb.message.edit_text("**👨‍💻 ᴅᴇᴠᴇʟᴏᴘᴇʀ ɪɴꜰᴏ**\n\nᴛʜɪs ʙᴏᴛ ɪs ᴄʀᴀꜰᴛᴇᴅ ᴡɪᴛʜ ❤️ ʙʏ THE-VIP-BOY.", reply_markup=InlineKeyboardMarkup(buttons))

@app.on_callback_query(filters.regex("donate"))
async def donate_callback(client, cb):
    await cb.answer()
    await cb.message.reply_photo(
        photo=DONATE_LINK,
        caption="**💎 sᴜᴘᴘᴏʀᴛ ᴏᴜʀ ᴊᴏᴜʀɴᴇʏ**\n\nʏᴏᴜʀ small contribution helps us keep the servers running.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🗑️ ᴄʟᴏsᴇ", callback_data="close")]])
    )

@app.on_callback_query(filters.regex("basic_guide"))
async def guide_callback(client, cb):
    await cb.message.edit_text(
        f"**📘 ǫᴜɪᴄᴋ sᴛᴀʀᴛ ɢᴜɪᴅᴇ**\n\n1. Add me to your group.\n2. Promote me as admin.\n3. Use /play <song name> to start music.\n4. Use /help for more commands.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 ʙᴀᴄᴋ", callback_data="about")]])
    )

@app.on_callback_query(filters.regex("support"))
async def support_callback(client, cb):
    kb = [
        [InlineKeyboardButton("⛅ ɢʀᴏᴜᴘ", url=config.SUPPORT_GROUP), InlineKeyboardButton("🎄 ᴄʜᴀɴɴᴇʟ", url=config.SUPPORT_CHANNEL)],
        [InlineKeyboardButton("🏠 ʜᴏᴍᴇ", callback_data="go_to_start")]
    ]
    await cb.message.edit_text("**💬 sᴜᴘᴘᴏʀᴛ ᴄᴇɴᴛᴇʀ**\n\nꜰᴀᴄɪɴɢ ɪssᴜᴇs? Join our support group.", reply_markup=InlineKeyboardMarkup(kb))

# ==========================================
# HOME BUTTON (go_to_start) HANDLER ADDED
# ==========================================
@app.on_callback_query(filters.regex("go_to_start") & ~BANNED_USERS)
@languageCB
async def go_to_start(client, cb: CallbackQuery, _):
    try:
        # Start panel buttons layout lekar aao
        out = start_pannel(_)
        # Check karo ki message photo hai ya text
        if cb.message.photo:
            await cb.message.edit_caption(
                caption=_["start_2"].format(cb.from_user.mention, app.mention),
                reply_markup=InlineKeyboardMarkup(out),
            )
        else:
            await cb.message.edit_text(
                text=_["start_2"].format(cb.from_user.mention, app.mention),
                reply_markup=InlineKeyboardMarkup(out),
            )
    except Exception as e:
        # Agar koi error aaye (Jaise message edit limit)
        await cb.answer("Returning Home...")
        # Optional: purana delete karke new start message bhej sakte ho
