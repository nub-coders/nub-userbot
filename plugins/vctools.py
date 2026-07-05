
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
import requests
import time
import pytesseract
from moviepy.editor import VideoFileClip, AudioFileClip
from io import BytesIO
from PIL import Image

from pyrogram import enums
import shutil
import datetime
from pyrogram.raw.types import DataJSON
import asyncio
from pyrogram import Client
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.types import InputPeerChannel
from pyrogram.raw.functions.phone import GetCallConfig, JoinGroupCall
from pyrogram.raw.types import InputGroupCall
import pymongo
from pytgcalls.types import ChatUpdate
import certifi
import datetime
from pyrogram import enums
from pyrogram.errors import FloodWait
import asyncio
import random
import re
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.raw.types import MessageEntityTextUrl, MessageEntityMentionName
import datetime
from pytz import timezone
import yt_dlp
from pyrogram.types import Chat
import asyncio
import textwrap
import time
import math
import shlex
from typing import Tuple
from typing import Any, Dict
from typing import Optional
from PIL import Image, ImageDraw, ImageFont
from pymediainfo import MediaInfo
from pyrogram.handlers import MessageHandler
import queue
import subprocess
import certifi
import random
from random import randint
import asyncio
import time
import sys
import re
import pyrogram
from pyrogram import filters,enums
import os
import pymongo
from pyrogram import Client
from pyrogram.errors.exceptions.unauthorized_401 import SessionPasswordNeeded
from pyrogram.raw.functions.phone import CreateGroupCall
from pyrogram.errors.exceptions.bad_request_400 import PasswordHashInvalid
from pyrogram.errors.exceptions.bad_request_400 import PhoneCodeInvalid
from pyrogram.errors.exceptions import AuthKeyDuplicated, MessageIdInvalid
from pyrogram.errors.exceptions import AuthKeyUnregistered, PremiumAccountRequired
from pyrogram.errors.exceptions import SessionRevoked,ChatForwardsRestricted
from pyrogram.errors.exceptions import PeerFlood,UserRestricted,FileReferenceExpired
from pyrogram.errors.exceptions import UserDeactivatedBan
from pyrogram.errors.exceptions import PeerIdInvalid
from pyrogram.errors.exceptions import UserDeactivated
from pyrogram.enums import ParseMode
from pyrogram.errors import StickersetInvalid, YouBlockedUser
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.types import InputStickerSetShortName
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import CreateGroupCall, DiscardGroupCall
from pyrogram.raw.types import InputGroupCall, InputPeerChannel, InputPeerChat
from pyrogram.enums import ChatType, UserStatus
from pyrogram import __version__ as versipyro
from parser import mention_html, mention_markdown
import imageio
import imageio_ffmpeg as ffmpeg
from PIL import Image
from pyrogram.raw import functions

ggg=os.getcwd()
current_dir = f"{ggg}"




def get_user_id_by_client(user_id, client):
  for id in clients:
    if id == user_id:
      user_client = clients.get(user_id)
      if user_client.me.id == client.me.id:
          return True
  return False
async def is_active_chat(user_client,chat_id):
    if chat_id not in active[user_client.me.first_name]:
        return False
    else:
        return True


async def add_active_chat(user_client,chat_id):
    if chat_id not in active[user_client.me.first_name]:
        active[user_client.me.first_name].append(chat_id)


async def remove_active_chat(user_client, chat_id):
    if chat_id in active[user_client.me.first_name]:
        active[user_client.me.first_name].remove(chat_id)

from functools import wraps

def retry(max_retries=3, initial_delay=5, backoff=2, exceptions=(FloodWait, OSError)):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            retries = 0
            delay = initial_delay
            while retries < max_retries:
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    retries += 1
                    wait = e.value if isinstance(e, FloodWait) else delay
                    print(f"Retry {retries}/{max_retries} for {func.__name__} after {wait}s")
                    await asyncio.sleep(wait)
                    delay *= backoff
                except Exception as e:
                    print(f"Unexpected error in {func.__name__}: {str(e)}")
                    raise
            return await func(*args, **kwargs)
        return wrapper
    return decorator








from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.phone import InviteToGroupCall
from pyrogram.errors.exceptions import GroupcallForbidden, PeerIdInvalid, ChannelInvalid
from config import *  # Import API_ID and API_HASH from config.py

# Helper function to split users into chunks
def user_list(users, chunk_size):
    for i in range(0, len(users), chunk_size):
        yield users[i:i + chunk_size]

def user_dist(l, n):
    for i in range(0, len(l), n):
        yield l[i: i + n]

# Invite users to voice chat directly with the command handler
@Client.on_message(filters.command("invite2vc") & filters.me)
@retry()
async def invite_to_voice_chat(client, message):
    chat_id = message.chat.id
    users = []
    await message.edit("Starting to invite users to voice chat...")

    # Resolve the peer for the chat and get the call information
    try:
        input_channel = await client.resolve_peer(chat_id)
        full_channel = await client.invoke(GetFullChannel(channel=input_channel))
        call = full_channel.full_chat.call

        if not call:
            await message.edit("No active group call found.")
            return
    except ChannelInvalid:
        await message.edit("Invalid channel or group.")
        return
    except Exception as e:
        await message.edit(f"Error retrieving group call: {str(e)}")
        return

    # Collect user IDs (non-bot, non-deleted members)
    async for m in client.get_chat_members(chat_id):
        if m.user and not m.user.is_bot and not m.user.is_deleted:
            users.append(m.user.id)  # Add user ID to the list

    # Invite users in chunks
    z = 0
    hmm = list(user_dist(users, 6))
    for p in hmm:
        try:
            await client.invoke(
                InviteToGroupCall(
                    call=call,  # Pass the call object retrieved from messages.ChatFull
                    users = [await client.resolve_peer(user_id) for user_id in p]
                )
            )
            z += 6
        except GroupcallForbidden:
            # Edit the message to indicate that the user needs to join the group call
            await message.edit("Please join the group call before inviting users.")
            return  # Exit as the group call can't be invited to
        except PeerIdInvalid:
            print("Some users couldn't be invited.")
        except Exception as e:
            print(f"Error: {str(e)}")

        await asyncio.sleep(10)  # Wait for 10 seconds before inviting the next chunk

    await message.edit(f"Finished inviting users. Total invited: {z}")

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

@Client.on_message(filters.command("vc1") & filters.me & filters.group)
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


@Client.on_message(filters.command("vc0") & filters.me & filters.group)
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



import os
import re
import asyncio
import random
import subprocess
from urllib.parse import urlparse
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.raw.types import InputPeerChannel, InputPeerChat
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import GetGroupCall, CreateGroupCall, GetGroupCallStreamRtmpUrl




