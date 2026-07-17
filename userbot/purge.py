
import asyncio
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from config import *
from tools import *

@Client.on_message(filters.command("purge", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def purge(client, message):
    chunk = []
    async for msg in client.get_chat_history(
        chat_id=message.chat.id,
        limit=message.id - message.reply_to_message.id + 1,
    ):
        if msg.id < message.reply_to_message.id:
            break
        chunk.append(msg.id)
        if len(chunk) >= 100:
            await client.delete_messages(message.chat.id, chunk)
            chunk.clear()
            await asyncio.sleep(1)

    if len(chunk) > 0:
        await client.delete_messages(message.chat.id, chunk)

@Client.on_message(filters.command("delall", prefixes=HARDCODED_PREFIXES) & filters.me & filters.reply)
@retry()
async def delete_all_messages(client: Client, message: Message):
    try:
        await message.delete()
    except:
        pass
    target_user = message.reply_to_message.from_user
    if not target_user:
        return

    try:
        message_ids = []
        async for msg in client.search_messages(
            chat_id=message.chat.id,
            from_user=target_user.id
        ):
            message_ids.append(msg.id)
            if len(message_ids) >= 100:
                try:
                    await client.delete_messages(message.chat.id, message_ids)
                    message_ids = []
                    await asyncio.sleep(0.5)
                except FloodWait as e:
                    await asyncio.sleep(e.value)
        
        if message_ids:
            await client.delete_messages(message.chat.id, message_ids)
            
    except Exception:
        pass

@Client.on_message(filters.command("del", prefixes=HARDCODED_PREFIXES) & filters.me & filters.reply)
@retry()
async def delete_message(client: Client, message: Message):
    if message.reply_to_message:
        try:
            await client.delete_messages(
                message.chat.id, 
                [message.reply_to_message.id, message.id]
            )
        except Exception:
            pass
