from pyrogram import Client, filters, types
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
import config
from config import BANNED_USERS, START_IMG_URL
from strings import get_command, get_string, helpers
from VIPMUSIC import HELPABLE, app
from VIPMUSIC.utils.database import get_lang
from VIPMUSIC.utils.decorators.language import languageCB

# --- Luxury Aesthetic Elements ---
BN_INVITE = "✧ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ᴄʜᴀᴛ ✧"
BN_BACK = "⇠ ɢᴏ ʙᴀᴄᴋ"
BN_CLOSE = "▢ ᴄʟᴏsᴇ"
SEPARATOR = "⏤⏤⏤⏤⏤⏤⏤⏤⏤⏤⏤⏤⏤"

# --- Optimized Help Mapping ---
HELP_MAP = {
    "music": {
        "hb1": helpers.HELP_1, "hb2": helpers.HELP_2, "hb3": helpers.HELP_3,
        "hb4": helpers.HELP_4, "hb5": helpers.HELP_5, "hb11": helpers.HELP_11,
        "hb14": helpers.HELP_14, "hb15": helpers.HELP_15,
    },
    "mng": {
        "hb1": helpers.MHELP_1, "hb2": helpers.MHELP_2, "hb3": helpers.MHELP_3,
        "hb5": helpers.MHELP_5, "hb6": helpers.MHELP_6, "extra": helpers.EXTRA_1,
    }
}

# 1. Main Dashboard (Feature Menu)
@app.on_callback_query(filters.regex("feature"))
async def feature_callback(client, query):
    buttons = [
        [InlineKeyboardButton(text=BN_INVITE, url=f"https://t.me/{app.username}?startgroup=true")],
        [
            InlineKeyboardButton(text="• ᴍᴜsɪᴄ •", callback_data="music_main"),
            InlineKeyboardButton(text="• ᴍᴀɴᴀɢᴇ •", callback_data="mng_main"),
        ],
        [
            InlineKeyboardButton(text="• ᴛᴏᴏʟs •", callback_data="tools_main"),
            InlineKeyboardButton(text="• sᴇᴛᴛɪɴɢs •", callback_data="settings_back_helper"),
        ],
        [InlineKeyboardButton(text=BN_CLOSE, callback_data="close")]
    ]
    
    caption = f"""
**— ᴍᴀɪɴ ᴄᴏɴᴛʀᴏʟ ᴘᴀɴᴇʟ —**
{SEPARATOR}
**sᴛᴀᴛᴜs:** ᴏᴘᴇʀᴀᴛɪᴏɴᴀʟ
**ᴠᴇʀsɪᴏɴ:** 𝟻.𝟶 (ᴘʀᴇᴍɪᴜᴍ)

ᴇxᴘʟᴏʀᴇ ᴛʜᴇ ᴍᴏᴅᴜʟᴇs ʙᴇʟᴏᴡ ᴛᴏ ᴄᴏɴғɪɢᴜʀᴇ ʏᴏᴜʀ ᴄʜᴀᴛ ᴇxᴘᴇʀɪᴇɴᴄᴇ.
{SEPARATOR}"""

    await query.message.edit_text(caption, reply_markup=InlineKeyboardMarkup(buttons))

# 2. Music Panel (Clean 2-Column)
@app.on_callback_query(filters.regex("music_main"))
async def music_panel(client, query):
    buttons = [
        [
            InlineKeyboardButton(text="ᴀᴅᴍɪɴ ᴛᴏᴏʟs", callback_data="m_cb hb1"),
            InlineKeyboardButton(text="ᴀᴜᴛʜ ᴜsᴇʀs", callback_data="m_cb hb2"),
        ],
        [
            InlineKeyboardButton(text="ᴘʟᴀʏʟɪsᴛs", callback_data="m_cb hb11"),
            InlineKeyboardButton(text="sᴇᴀʀᴄʜᴇʀ", callback_data="m_cb hb14"),
        ],
        [InlineKeyboardButton(text=BN_BACK, callback_data="feature")]
    ]
    await query.message.edit(f"**— ᴍᴜsɪᴄ sʏsᴛᴇᴍ —**\n{SEPARATOR}\nᴄᴏɴғɪɢᴜʀᴇ ʏᴏᴜʀ ᴀᴜᴅɪᴏ sᴇᴛᴛɪɴɢs:", reply_markup=InlineKeyboardMarkup(buttons))

# 3. Management Panel
@app.on_callback_query(filters.regex("mng_main"))
async def mng_panel(client, query):
    buttons = [
        [
            InlineKeyboardButton(text="ʀᴇsᴛʀɪᴄᴛ", callback_data="g_cb hb1"),
            InlineKeyboardButton(text="ᴄʟᴇᴀɴᴇʀ", callback_data="g_cb hb2"),
        ],
        [
            InlineKeyboardButton(text="sᴇᴛᴜᴘ ᴡɪᴢᴀʀᴅ", callback_data="g_cb hb6"),
            InlineKeyboardButton(text="ᴇxᴛʀᴀ", callback_data="g_cb extra"),
        ],
        [InlineKeyboardButton(text=BN_BACK, callback_data="feature")]
    ]
    await query.message.edit(f"**— ɢʀᴏᴜᴘ ᴍᴀɴᴀɢᴇᴍᴇɴᴛ —**\n{SEPARATOR}\nᴘʀᴏᴛᴇᴄᴛ ᴀɴᴅ ᴏᴘᴛɪᴍɪᴢᴇ ʏᴏᴜʀ ᴄʜᴀᴛ:", reply_markup=InlineKeyboardMarkup(buttons))

# 4. Unified Handler (The Logic)
@app.on_callback_query(filters.regex(r"^(m_cb|g_cb)") & ~BANNED_USERS)
@languageCB
async def helper_logic(client, query, _):
    cb_data = query.data.split()
    cat = "music" if cb_data[0] == "m_cb" else "mng"
    key = cb_data[1]
    
    if key in HELP_MAP[cat]:
        kb = [[InlineKeyboardButton(text=BN_BACK, callback_data=f"{cat}_main")]]
        await query.edit_message_text(
            f"{SEPARATOR}\n{HELP_MAP[cat][key]}\n{SEPARATOR}",
            reply_markup=InlineKeyboardMarkup(kb)
        )

# 5. Developer Section (Luxury Card Style)
@app.on_callback_query(filters.regex("developer"))
async def dev_section(client, query):
    buttons = [
        [
            InlineKeyboardButton(text="ᴏᴡɴᴇʀ", user_id=config.OWNER_ID[0]),
            InlineKeyboardButton(text="ɴᴇᴛᴡᴏʀᴋ", url=config.SUPPORT_CHANNEL),
        ],
        [InlineKeyboardButton(text=BN_BACK, callback_data="feature")]
    ]
    dev_text = f"**— ᴀʀᴄʜɪᴛᴇᴄᴛ ɪɴғᴏ —**\n{SEPARATOR}\n**ᴅᴇᴠᴇʟᴏᴘᴇʀ:** @YourUser\n**ʟɪʙʀᴀʀʏ:** ᴘʏʀᴏɢʀᴀᴍ\n\nᴛʜᴀɴᴋ ʏᴏᴜ ғᴏʀ ᴜsɪɴɢ ᴏᴜʀ sᴇʀᴠɪᴄᴇs."
    await query.message.edit_text(dev_text, reply_markup=InlineKeyboardMarkup(buttons))
