# ---------------------------------------------------------------------------------
#                                 👑 VIP MUSIC 👑
# ---------------------------------------------------------------------------------
# Copyright (C) 2025 VIP MUSIC Team
# English Version - Premium Brand Box Layout
# ---------------------------------------------------------------------------------

from pyrogram.types import InlineKeyboardButton
import config
from config import SUPPORT_GROUP, SUPPORT_CHANNEL, OWNER_ID
from VIPMUSIC import app

# ==========================================
# 1. PRIVATE PANEL (DM - Help at the Bottom)
# ==========================================
def private_panel(_):
    buttons = [
        [
            # Row 1: Invite (Full Box)
            InlineKeyboardButton(
                text="✨ INVITE ME NOW ✨",
                url=f"https://t.me/{app.username}?startgroup=true",
            )
        ],
        [
            # Row 2: Group & Updates (Side-by-Side Boxes)
            InlineKeyboardButton(text="💠 GROUP", url=config.SUPPORT_GROUP),
            InlineKeyboardButton(text="🪐 UPDATES", url=config.SUPPORT_CHANNEL),
        ],
        [
            # Row 3: Owner & Source (Side-by-Side Boxes)
            InlineKeyboardButton(text="🍷 OWNER", url=f"tg://openmessage?user_id={config.OWNER_ID}"),
            InlineKeyboardButton(text="🎋 SOURCE", url=config.UPSTREAM_REPO),
        ],
        [
            # Row 4: Help & Commands (Moved to Bottom - Full Box)
            InlineKeyboardButton(
                text="📜 HELP & COMMANDS 📜", callback_data="settings_back_helper"
            )
        ],
    ]
    return buttons


# ==========================================
# 2. START PANEL (Group Start Layout)
# ==========================================
def start_pannel(_):
    buttons = [
        [
            # Full Width Box
            InlineKeyboardButton(
                text="〆 ADD ME TO YOUR CHAT 〆",
                url=f"https://t.me/{app.username}?startgroup=true",
            ),
        ],
        [
            # Paired Boxes
            InlineKeyboardButton(text="⛩️ HELP", callback_data="settings_back_helper"),
            InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="settings_helper"),
        ],
        [
            # Paired Boxes
            InlineKeyboardButton(text="🎐 SUPPORT", url=config.SUPPORT_GROUP),
            InlineKeyboardButton(text="📜 UPDATES", url=config.SUPPORT_CHANNEL),
        ],
    ]
    return buttons


# ==========================================
# 3. ALIVE PANEL (Clean Style)
# ==========================================
def alive_panel(_):
    buttons = [
        [
            # Paired Boxes
            InlineKeyboardButton(text="❄️ ADD ME ❄️", url=f"https://t.me/{app.username}?startgroup=true"),
            InlineKeyboardButton(text="❄️ SUPPORT ❄️", url=config.SUPPORT_GROUP),
        ],
        [
            # Full Width Box
            InlineKeyboardButton(text="ッ OWNER ッ", url=f"tg://openmessage?user_id={config.OWNER_ID}"),
        ]
    ]
    return buttons

# ---------------------------------------------------------------------------------
# ❤️ Powered by VIP MUSIC Team
# ---------------------------------------------------------------------------------
