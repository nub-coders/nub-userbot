
from pyrogram.enums import MessageEntityType
import json
from convopyro import Conversation
from convopyro import listen_message
import logging
from config import *
from tools import *
from pyrogram import Client

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

# Create a logger object
logger = logging.getLogger("userbot")
import os
import shlex
from random import randint
from pyrogram import filters, enums
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import CreateGroupCall, DiscardGroupCall
from pyrogram.raw.types import InputGroupCall, InputPeerChannel, InputPeerChat

ggg=os.getcwd()
current_dir = f"{ggg}"








def get_arg(message):
    msg = message.text
    msg = msg.replace(" ", "", 1) if msg[1] == " " else msg
    split = msg[1:].replace("\n", " \n").split(" ")
    if " ".join(split[1:]).strip() == "":
        return ""
    return " ".join(split[1:])

def get_args(message):
    try:
        message = message.text
    except AttributeError:
        pass
    if not message:
        return False
    message = message.split(maxsplit=1)
    if len(message) <= 1:
        return []
    message = message[1]
    try:
        split = shlex.split(message)
    except ValueError:
        return message
    return list(filter(lambda x: len(x) > 0, split))

@Client.on_message(filters.command("vc1", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def opengc(client, message):
    flags = " ".join(message.command[1:])
    vctitle = get_arg(message)
    if flags == enums.ChatType.CHANNEL:
        chat_id = message.chat.title
    else:
        chat_id = message.chat.id
    args = f"**Started Group Call"
    try:
        if not vctitle:
            await client.invoke(
CreateGroupCall(
                    peer=(await client.resolve_peer(chat_id)),
                    random_id=randint(10000, 999999999),
            )
)
        else:
            args += f"\n • **Title:** `{vctitle}`"
            await client.invoke(
                CreateGroupCall(
                    peer=(await client.resolve_peer(chat_id)),
                    random_id=randint(10000, 999999999),
                    title=vctitle,
                )
            )
        await message.edit(args)
    except Exception as e:
        await message.edit(f"Failed to start group call")


@Client.on_message(filters.command("vc0", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def end_group_call(client, message):
    """End the active group call in the chat."""
    try:
        chat_peer = await client.resolve_peer(message.chat.id)

        if isinstance(chat_peer, (InputPeerChannel, InputPeerChat)):
            if isinstance(chat_peer, InputPeerChannel):
                full_chat = (await client.invoke(GetFullChannel(channel=chat_peer))).full_chat
            elif isinstance(chat_peer, InputPeerChat):
                full_chat = (await client.invoke(GetFullChat(chat_id=chat_peer.chat_id))).full_chat

            if full_chat is not None:
                group_call = full_chat.call
                if group_call is not None:
                    await client.invoke(
                        DiscardGroupCall(call=InputGroupCall(id=group_call.id, access_hash=group_call.access_hash))
                    )
                    await message.edit_text("Ended group call")
                    return
        await message.edit_text("No active group call found")
    except Exception as e:
        await message.edit_text(f"An error occurred: {e}")




