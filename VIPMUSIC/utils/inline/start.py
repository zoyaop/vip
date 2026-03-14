from pyrogram.types import InlineKeyboardButton
import config
from config import SUPPORT_GROUP, SUPPORT_CHANNEL
from VIPMUSIC import app

def start_pannel(_):
    """Group/Settings Start Panel - 2026 Edition"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🚀 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ᴄʟᴀɴ 🚀",
                url=f"https://t.me/{app.username}?startgroup=true",
            ),
        ],
        [
            InlineKeyboardButton(text="✨ ʜᴇʟᴘ", callback_data="settings_back_helper"),
            InlineKeyboardButton(text="⚙️ sᴇᴛᴛɪɴɢs", callback_data="settings_helper"),
        ],
        [
            InlineKeyboardButton(text="🛡️ sᴜᴘᴘᴏʀᴛ", url=config.SUPPORT_GROUP),
            InlineKeyboardButton(text="📢 ᴜᴘᴅᴀᴛᴇs", url=config.SUPPORT_CHANNEL),
        ],
    ]
    return buttons


def private_panel(_):
    """Private DM Start Panel - 2026 Edition"""
    buttons = [
        [
            InlineKeyboardButton(
                text="➕ ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ ➕",
                url=f"https://t.me/{app.username}?startgroup=true",
            )
        ],
        [
            InlineKeyboardButton(text="💬 sᴜᴘᴘᴏʀᴛ", url=config.SUPPORT_GROUP),
            InlineKeyboardButton(text="🚀 ᴜᴘᴅᴀᴛᴇs", url=config.SUPPORT_CHANNEL),
        ],
        [
            InlineKeyboardButton(
                text="🌌 ᴇxᴘʟᴏʀᴇ ꜰᴇᴀᴛᴜʀᴇs 🌌", callback_data="feature"
            )
        ],
    ]
    return buttons


def alive_panel(_):
    """Alive/Status Panel - 2026 Edition"""
    buttons = [
        [
            InlineKeyboardButton(
                text="✨ ɪɴᴠɪᴛᴇ ᴍᴇ", url=f"https://t.me/{app.username}?startgroup=true"
            ),
            InlineKeyboardButton(text="💬 sᴜᴘᴘᴏʀᴛ", url=f"{SUPPORT_GROUP}"),
        ],
    ]
    return buttons


def music_start_panel(_):
    """Music Specialized Start Panel - 2026 Edition"""
    buttons = [
        [
            InlineKeyboardButton(
                text="🎵 ᴀᴅᴅ ᴍᴇ ᴛᴏ ʏᴏᴜʀ ɢʀᴏᴜᴘ 🎵",
                url=f"https://t.me/{app.username}?startgroup=true",
            )
        ],
        [
            InlineKeyboardButton(text="ℹ️ ᴀʙᴏᴜᴛ", callback_data="about"),
            InlineKeyboardButton(text="🛡️ sᴜᴘᴘᴏʀᴛ", callback_data="support"),
        ],
        [
            InlineKeyboardButton(text="🛸 ɴᴇᴜʀᴀʟ ꜰᴇᴀᴛᴜʀᴇs", callback_data="feature")
        ],
    ]
    return buttons
