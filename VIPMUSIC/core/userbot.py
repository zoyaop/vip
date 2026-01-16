#
# Copyright (C) 2024 by THE-VIP-BOY-OP@Github, < https://github.com/THE-VIP-BOY-OP >.
#
# This file is part of < https://github.com/THE-VIP-BOY-OP/VIP-MUSIC > project,
# and is released under the "GNU v3.0 License Agreement".
# Please see < https://github.com/THE-VIP-BOY-OP/VIP-MUSIC/blob/master/LICENSE >
#
# All rights reserved.
#

from typing import Callable, Optional
import pyrogram
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, ChatWriteForbidden
import config
from ..logging import LOGGER

assistants = []
assistantids = []
clients = []

class Userbot(Client):
    def __init__(self):
        self.one = Client("VIPString1", api_id=config.API_ID, api_hash=config.API_HASH, session_string=str(config.STRING1))
        self.two = Client("VIPString2", api_id=config.API_ID, api_hash=config.API_HASH, session_string=str(config.STRING2))
        self.three = Client("VIPString3", api_id=config.API_ID, api_hash=config.API_HASH, session_string=str(config.STRING3))
        self.four = Client("VIPString4", api_id=config.API_ID, api_hash=config.API_HASH, session_string=str(config.STRING4))
        self.five = Client("VIPString5", api_id=config.API_ID, api_hash=config.API_HASH, session_string=str(config.STRING5))

    async def start(self):
        LOGGER(__name__).info(f"Starting Assistant Clients...")
        
        # --- Assistant 1 ---
        if config.STRING1:
            await self.one.start()
            try:
                await self.one.join_chat("VnioxTechApi")
                await self.one.join_chat("ll_DEADLY_VENOM_ll")
            except: pass
            assistants.append(1)
            clients.append(self.one)
            
            # Log Group Message Fix
            if config.LOG_GROUP_ID:
                try:
                    await self.one.get_chat(config.LOG_GROUP_ID) # Resolve Peer
                    await self.one.send_message(config.LOG_GROUP_ID, "✅ Assistant 1 Started")
                except:
                    LOGGER(__name__).error("Assistant 1 failed to send message to Log Group.")

            get_me = await self.one.get_me()
            self.one.id, self.one.name, self.one.username = get_me.id, get_me.first_name, get_me.username
            assistantids.append(get_me.id)
            LOGGER(__name__).info(f"Assistant 1 Started as {self.one.name}")

        # --- Assistant 2 ---
        if config.STRING2:
            await self.two.start()
            try:
                await self.two.join_chat("VnioxTechApi")
            except: pass
            assistants.append(2)
            clients.append(self.two)
            if config.LOG_GROUP_ID:
                try:
                    await self.two.get_chat(config.LOG_GROUP_ID)
                    await self.two.send_message(config.LOG_GROUP_ID, "✅ Assistant 2 Started")
                except: pass
            get_me = await self.two.get_me()
            self.two.id, self.two.name = get_me.id, get_me.first_name
            assistantids.append(get_me.id)
            LOGGER(__name__).info(f"Assistant 2 Started as {self.two.name}")

        # --- Assistant 3 ---
        if config.STRING3:
            await self.three.start()
            assistants.append(3)
            clients.append(self.three)
            if config.LOG_GROUP_ID:
                try:
                    await self.three.get_chat(config.LOG_GROUP_ID)
                    await self.three.send_message(config.LOG_GROUP_ID, "✅ Assistant 3 Started")
                except: pass
            get_me = await self.three.get_me()
            self.three.id, self.three.name = get_me.id, get_me.first_name
            assistantids.append(get_me.id)

        # --- Assistant 4 ---
        if config.STRING4:
            await self.four.start()
            assistants.append(4)
            clients.append(self.four)
            if config.LOG_GROUP_ID:
                try:
                    await self.four.get_chat(config.LOG_GROUP_ID)
                    await self.four.send_message(config.LOG_GROUP_ID, "✅ Assistant 4 Started")
                except: pass
            get_me = await self.four.get_me()
            self.four.id, self.four.name = get_me.id, get_me.first_name
            assistantids.append(get_me.id)

        # --- Assistant 5 ---
        if config.STRING5:
            await self.five.start()
            assistants.append(5)
            clients.append(self.five)
            if config.LOG_GROUP_ID:
                try:
                    await self.five.get_chat(config.LOG_GROUP_ID)
                    await self.five.send_message(config.LOG_GROUP_ID, "✅ Assistant 5 Started")
                except: pass
            get_me = await self.five.get_me()
            self.five.id, self.five.name = get_me.id, get_me.first_name
            assistantids.append(get_me.id)

    async def stop(self):
        for client in clients:
            try: await client.stop()
            except: pass

def on_cmd(filters: Optional[pyrogram.filters.Filter] = None, group: int = 0) -> Callable:
    def decorator(func: Callable) -> Callable:
        for client in clients:
            client.add_handler(pyrogram.handlers.MessageHandler(func, filters), group)
        return func
    return decorator
