import pyrogram
from pyrogram import Client
from pyrogram.errors import PeerIdInvalid, ChatWriteForbidden, FloodWait
from typing import Callable, Optional
import asyncio
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
        assistant_list = [
            (config.STRING1, self.one, 1),
            (config.STRING2, self.two, 2),
            (config.STRING3, self.three, 3),
            (config.STRING4, self.four, 4),
            (config.STRING5, self.five, 5),
        ]

        for string, client, num in assistant_list:
            if string:
                await client.start()
                
                # सपोर्ट चैट्स जॉइन करना
                try:
                    await client.join_chat("VnioxTechApi")
                    await client.join_chat("HEROKU_CLUB")
                    await client.join_chat("Nobita_Support")
                    await client.join_chat("ll_DEADLY_VENOM_ll")
                except Exception:
                    pass

                assistants.append(num)
                clients.append(client)

                # --- मैसेज भेजने का सुधारा हुआ तरीका ---
                if config.LOG_GROUP_ID:
                    try:
                        # पहले ग्रुप को 'Resolve' करना जरूरी है
                        await client.get_chat(config.LOG_GROUP_ID)
                        await client.send_message(config.LOG_GROUP_ID, f"✅ **Assistant {num} Started!**")
                    except (PeerIdInvalid, ChatWriteForbidden):
                        LOGGER(__name__).error(f"❌ Assistant {num} failed: Add Assistant to Log Group and make it Admin!")
                    except FloodWait as e:
                        await asyncio.sleep(e.value)
                    except Exception as e:
                        LOGGER(__name__).error(f"Assistant {num} Error: {e}")

                get_me = await client.get_me()
                client.username = get_me.username
                client.id = get_me.id
                client.mention = get_me.mention
                client.name = f"{get_me.first_name} {get_me.last_name or ''}".strip()
                
                assistantids.append(get_me.id)
                LOGGER(__name__).info(f"Assistant {num} Started as {client.name}")

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
