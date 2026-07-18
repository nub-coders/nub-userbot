

# Common imports used across plugins
import requests
import re
import os
import sys
import time
import random
import asyncio
import math
import shlex
import datetime
import subprocess
import base64
import logging
from io import BytesIO, StringIO
from urllib.parse import parse_qs, urlparse
from typing import Tuple, List, Dict, Any, Optional
from functools import wraps

# PIL imports
from PIL import Image, ImageDraw, ImageFont

# Pyrogram imports
from pyrogram import Client, filters, enums
from pyrogram.types import Message, ChatPrivileges
from pyrogram.errors import FloodWait, ChatForwardsRestricted, FileReferenceExpired, MessageIdInvalid
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.types import InputPeerChannel, InputPeerChat

# Media processing imports
from pymediainfo import MediaInfo
import cv2
import imageio
import magic

# MongoDB and other database imports
import pymongo
import certifi

# Initialize magic for file type detection
mime = magic.Magic(mime=True)

from config import apps, clients, user_sessions, admin_file, SUDO, HARDCODED_PREFIXES, ggg

# Simple TTL cache for user session data
import threading

class _SessionCache:
    """In-memory cache for user_sessions.find_one() results with a TTL."""
    def __init__(self, ttl=30):
        self._cache = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def get(self, user_id):
        with self._lock:
            entry = self._cache.get(user_id)
            if entry and (time.time() - entry[1]) < self._ttl:
                return entry[0]
            return None

    def set(self, user_id, data):
        with self._lock:
            self._cache[user_id] = (data, time.time())

    def invalidate(self, user_id=None):
        with self._lock:
            if user_id:
                self._cache.pop(user_id, None)
            else:
                self._cache.clear()

_session_cache = _SessionCache(ttl=30)


def _get_bot_client():
    """Get the bot client (apps['app']). Returns None if not started yet."""
    return apps.get("app")


def _get_userbot_client():
    """Get the userbot client from clients dict. Returns None if not started yet."""
    if clients:
        return list(clients.values())[0]
    return None


class _BotProxy:
    """Proxy that forwards attribute access to apps['app'], the bot client.
    Allows plugins to use `bot.send_message(...)` without importing apps directly.
    Also provides Telethon-style `bot.edit_message(msg, text)` compatibility."""

    def __getattr__(self, name):
        client = _get_bot_client()
        if client is None:
            client = _get_userbot_client()
            if client is None:
                raise RuntimeError("No Telegram client started yet")
        if name == "edit_message":
            return self._edit_message
        return getattr(client, name)

    async def _edit_message(self, message, text, **kwargs):
        """Telethon-compatible edit_message(msg, text) -> Pyrogram msg.edit_text(text)"""
        if hasattr(message, 'edit_text'):
            return await message.edit_text(text, **kwargs)
        return await message.edit(text, **kwargs)


bot = _BotProxy()
app = _BotProxy()


def is_admin(user_id):
    """Check if a user_id is the bot owner (exists in clients dict)."""
    return user_id in clients


def is_admin_user(user_id):
    """Check if a user_id is an owner. Same as is_admin."""
    return is_admin(user_id)


def cached_get_user_data(user_id):
    """Get user session data with caching to avoid repeated DB queries."""
    data = _session_cache.get(user_id)
    if data is not None:
        return data
    data = user_sessions.find_one({"user_id": user_id})
    if data is None:
        data = {}
    _session_cache.set(user_id, data)
    return data


def invalidate_session_cache(user_id=None):
    """Invalidate cache after writes. Call after any user_sessions.update_one/insert_one."""
    _session_cache.invalidate(user_id)


def sudoers_filter():
    """Filter that matches messages from sudo users."""
    def func(_, client, message):
        if not message.from_user:
            return False
        sudoers = SUDO.get(client.me.id, [])
        return message.from_user.id in sudoers
    return filters.create(func)


async def edit_or_reply(message, text, **kwargs):
    """Edit message if sent by self, otherwise reply."""
    if message.from_user and message.from_user.is_self:
        return await message.edit_text(text, **kwargs)
    return await message.reply(text, **kwargs)


def styled_error(text):
    """Format an error message."""
    return f"❌ **Error**\n\n⚠️ {text}"


def styled_success(text):
    """Format a success message."""
    return f"✅ {text}"


def can_grant_privilege(promoter_privileges, privilege_name):
    """Check if the promoter has a specific privilege they can grant."""
    return getattr(promoter_privileges, privilege_name, False)


def styled_help_categories(categories_dict, prefix):
    """Format help categories overview."""
    lines = ["📖 **Command Categories**\n"]
    for cat, cmds in categories_dict.items():
        if cmds:
            cmd_list = ", ".join(f"`{prefix}{c}`" for c in cmds[:5])
            extra = f" +{len(cmds)-5} more" if len(cmds) > 5 else ""
            lines.append(f"**{cat}**\n┃ {cmd_list}{extra}")
        else:
            lines.append(f"**{cat}**")
    lines.append(f"\n💡 Use `{prefix}help <command>` for details")
    return "\n".join(lines)


def styled_help_card(cmd, desc, usage, example="", note="", flags="", warning=""):
    """Format a single command help card."""
    card = f"📖 **{cmd}**\n\n{desc}\n"
    if usage:
        card += f"\n**Usage:** `{usage}`"
    if example:
        card += f"\n**Example:** `{example}`"
    if flags:
        card += f"\n**Flags:** {flags}"
    if note:
        card += f"\n💡 {note}"
    if warning:
        card += f"\n⚠️ {warning}"
    return card


def update_message_and_entities(text, entities, words_to_remove=None):
    """Remove command words/flags from text and adjust entity offsets."""
    if not words_to_remove:
        return text, entities

    for word in words_to_remove:
        idx = text.find(word)
        if idx != -1:
            text = text[:idx] + text[idx + len(word):]
            removed_len = len(word)
            entities = [
                e for e in entities
                if not (e.offset >= idx and e.offset < idx + removed_len)
            ]
            for e in entities:
                if e.offset > idx:
                    e.offset -= removed_len

    text = " ".join(text.split()).strip()
    parts = text.split(None, 1)
    if parts:
        text = parts[1] if len(parts) > 1 else ""
    return text, entities


def sanitize_path(base_dir, filename):
    """Sanitize a filename to prevent path traversal attacks."""
    safe_name = os.path.basename(filename)
    safe_name = re.sub(r'[^\w\s\-.]', '_', safe_name)
    if not safe_name or safe_name.startswith('.'):
        safe_name = 'file_' + safe_name
    full_path = os.path.normpath(os.path.join(base_dir, safe_name))
    if not full_path.startswith(os.path.normpath(base_dir)):
        raise ValueError("Path traversal detected")
    return full_path


# Global help registries
commands = {}
categories = {}
games = {}

def get_user(message, text) -> [int, str, None]:
    """Get User From Message"""
    if text is None:
        asplit = None
    else:
        asplit = text.split(" ", 1)
    user_s = None
    reason_ = None
    if message.reply_to_message:
        user_s = message.reply_to_message.from_user.id
        reason_ = text if text else None
    elif asplit is None:
        return None, None
    elif len(asplit[0]) > 0:
        if message.entities:
            if len(message.entities) == 1:
                required_entity = message.entities[0]
                if required_entity.type == "text_mention":
                    user_s = int(required_entity.user.id)
                else:
                    user_s = int(asplit[0]) if asplit[0].isdigit() else asplit[0]
        else:
            user_s = int(asplit[0]) if asplit[0].isdigit() else asplit[0]
        if len(asplit) == 2:
            reason_ = asplit[1]
    return user_s, reason_


def get_text(message: Message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = message.text
    if message.text is None:
        return None
    if " " in text_to_return:
        try:
            return message.text.split(None, 1)[1]
        except IndexError:
            return None
    else:
        return None

async def extract_userid(message, text: str):
    def is_int(text: str):
        try:
            int(text)
        except ValueError:
            return False
        return True

    text = text.strip()

    if is_int(text):
        return int(text)

    entities = message.entities
    app = message._client
    if len(entities) < 2:
        return (await app.get_users(text)).id
    entity = entities[1]
    if entity.type == "mention":
        return (await app.get_users(text)).id
    if entity.type == "text_mention":
        return entity.user.id
    return None


async def extract_user_and_reason(message, sender_chat=False):
    args = message.text.strip().split()
    text = message.text
    user = None
    reason = None
    if message.reply_to_message:
        reply = message.reply_to_message
        if not reply.from_user:
            if (
                reply.sender_chat
                and reply.sender_chat != message.chat.id
                and sender_chat
            ):
                id_ = reply.sender_chat.id
            else:
                return None, None
        else:
            id_ = reply.from_user.id

        if len(args) < 2:
            reason = None
        else:
            reason = text.split(None, 1)[1]
        return id_, reason

    if len(args) == 2:
        user = text.split(None, 1)[1]
        return await extract_userid(message, user), None

    if len(args) > 2:
        user, reason = text.split(None, 2)[1:]
        return await extract_userid(message, user), reason

    return user, reason


async def extract_user(message):
    return (await extract_user_and_reason(message))[0]

async def download_file(
    url: str,
    filename: str,
    callback=None,
) -> str | bool:
    """
    Download a file from a URL to a specified location.

    Args:
        url (str): The URL of the file to download.
        filename (str): The location to save the file to.
        callback (function, optional): A function that will be called
            with progress updates during the download. The function should
            accept three arguments: the number of bytes downloaded so far,
            the total size of the file, and a status message.

    Returns:
        str: The filename of the downloaded file, or False if the download
            failed.

    Raises:
        requests.exceptions.HTTPError: If the server returns an error.
        OSError: If there is an error opening or writing to the file.
    """
    response = requests.get(url, stream=True)
    response.raise_for_status()
    xx=0
    with open(filename, "wb") as file:
        for chunk in response.iter_content(chunk_size=1024):
                file.write(chunk)
                xx+=1
                if callback and xx % 100==0:
                    downloaded_size = file.tell()
                    total_size = int(response.headers.get("content-length", 0))
                    await callback(downloaded_size, total_size, "Downloading")
    return filename



async def get_readable_time(seconds: int) -> str:
    count = 0
    up_time = ""
    time_list = []
    time_suffix_list = ["s", "m", "h", "days"]

    while count < 4:
        count += 1
        remainder, result = divmod(seconds, 60) if count < 3 else divmod(seconds, 24)
        if seconds == 0 and remainder == 0:
            break
        time_list.append(int(result))
        seconds = int(remainder)

    for x in range(len(time_list)):
        time_list[x] = str(time_list[x]) + time_suffix_list[x]
    if len(time_list) == 4:
        up_time += time_list.pop() + ", "

    time_list.reverse()
    up_time += ":".join(time_list)

    return up_time

# Common retry decorator used in many plugins
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

# File and media utilities
def rename_file(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        new_file_path = os.path.abspath(new_name)
        print(f'File renamed from {old_name} to {new_name}')
        return new_file_path
    except FileNotFoundError:
        print(f'The file {old_name} does not exist.')
    except FileExistsError:
        print(f'The file {new_name} already exists.')
    except Exception as e:
        print(f'An error occurred: {e}')

def generate_thumbnail(video_path, thumb_path):
    reader = imageio.get_reader(video_path)
    frame = reader.get_data(0)
    image = Image.fromarray(frame)
    image.thumbnail((320, 320))
    image.save(thumb_path, format="JPEG")

def with_opencv(filename):
    video = cv2.VideoCapture(filename)
    fps = video.get(cv2.CAP_PROP_FPS)
    frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
    duration = frame_count / fps if fps else 0
    video.release()
    print(int(duration))
    return int(duration)

# Progress bar timer class
class Timer:
    def __init__(self, time_between=2):
        self.start_time = time.time()
        self.time_between = time_between

    def can_send(self):
        if time.time() > (self.start_time + self.time_between):
            self.start_time = time.time()
            return True
        return False

# Admin check utility

def creator_only(func):
    """Decorator to restrict commands to creators/admins only"""
    @wraps(func)
    async def wrapper(client, message, *args, **kwargs):
        if not is_admin(message.from_user.id):
            return await message.reply("**⚠️ Access Denied**\n\nThis command is only for creators due to privacy and unauthorized repository/content access")
        return await func(client, message, *args, **kwargs)
    return wrapper

# Database utilities
def getuser_data(user_id):
    return cached_get_user_data(user_id)

def get_user_data(user_id, key):
    user_data = cached_get_user_data(user_id)
    if user_data and key in user_data:
        return user_data[key]
    return None

def gvarstatus(user_id, key):
    return get_user_data(user_id, key)

def set_gvar(user_id, key, value):
    user_sessions.update_one(
        {"user_id": user_id},
        {"$set": {key: value}},
        upsert=True
    )
    invalidate_session_cache(user_id)

# Message formatting utilities
async def format_welcome_message(client, text, chat_id, user_or_chat_name):
    """Helper function to format welcome message with real data"""
    try:
        formatted_text = text.replace("{name}", user_or_chat_name)
        formatted_text = formatted_text.replace("{id}", str(chat_id))
        formatted_text = formatted_text.replace("{yourname}", f"{client.me.first_name}")
        return formatted_text
    except Exception as e:
        logging.error(f"Error formatting welcome message: {str(e)}")
        return text

# Font formatting utility
def bold_cool(text):
    from fonts import bold_cool as font_bold_cool
    return font_bold_cool(text)

# Common filter utilities
def create_channel_custom_filter():
    def filter_func(_, client, message):
        user_id = client.me.id
        user_data = getuser_data(user_id)
        channels = user_data.get("channel", [])
        if not channels:
            return False
        return message.chat.id in channels
    return filters.create(filter_func)

def crcustom_filter():
    def filte_func(_, client, message):
         user_data = cached_get_user_data(client.me.id)
         spam_control = user_data.get('Spam_control', 'True')
         if spam_control == 'False':
            return False
         white_listed = user_data.get('white_listed', [])
         if not message.from_user:
           return False
         sender_id = message.from_user.id
         if sender_id in white_listed:
            return False
         return True
    return filters.create(filte_func)

# File upload utilities
async def big_file(msg, sender, zip_filename):
    import requests
    edit = 0
    url = "https://api.gofile.io/getServer"
    response = requests.get(url)
    data = response.json()
    server = data["data"]["server"]

    if not server:
        return await bot.edit_message(msg, "No storage available in gofile.io please try again later:")

    file_size = os.path.getsize(zip_filename)
    print(server)

    await bot.edit_message(msg, 'File size is greater than 2GB\nUploading file to gofile.io server...')

    transfer_url = f"https://{server}.gofile.io/uploadFile"
    try:
        command = ["curl", "-F", f"file=@{zip_filename}", transfer_url]
        start_time = time.time()
        print(command)
        output = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

        for line in output.stdout:
            type_of = "Uploading\nProgress:"
            line = line.strip()
            if line:
                output_text = line
                print(line)

                if edit % 5 == 0:
                    parts = line.split()

                    if len(parts) > 10:
                        print(parts[1])
                        total_size = parts[1]
                        total = re.sub("[^0-9]", "", total_size)
                        current_size = parts[5]
                        current = re.sub("[^0-9]", "", current_size)

                        if total.isdigit() and current.isdigit():
                            total = int(total)
                            current = int(current)

                            if current != 0 and total != 0:
                                progress_percent = current * 100 / total
                                progress_message = f"Downloading {zip_filename}: {progress_percent:.2f}%\n\n"

                                elapsed_time = time.time() - start_time
                                speed = current / (elapsed_time * 10)
                                progress_message += f"Speed: {speed:.2f} MB/s\n"

                                time_left = (total - current) / (speed * 10)
                                progress_message += f"Time left: {time_left:.2f} seconds"
                                progress_message += f"Size: {current / (1):.2f} MB / {total / (1):.2f} MB"

                                progress_bar_length = int(progress_percent / 5)
                                progress_bar_text = "█" * progress_bar_length + "░" * (20 - progress_bar_length)
                                progress_message += f"\n[{progress_bar_text}]"

                                message_text = f"{progress_message}"

                                try:
                                    if random.choices([True, False], weights=[1, 99])[0]:
                                        await bot.edit_message(msg, message_text, parse_mode='html')
                                except Exception as e:
                                    print(e)

                edit += 1

        text = line
        start_index = text.find("https://gofile.io")
        end_index = text.find('"', start_index)
        link = text[start_index:end_index]

        try:
            await bot.send_message(sender, f"Not able to upload files more than 500MB here\n So I provided this download link:", buttons=Button.url("Download File", link))
        except Exception as e:
            print(f"Error sending link: {link}, Error: {e}")
    except subprocess.CalledProcessError as e:
        print(e)


def get_text(message: Message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = message.text
    if message.text is None:
        return None
    if " " in text_to_return:
        try:
            return message.text.split(None, 1)[1]
        except IndexError:
            return None
    else:
        return None


def get_arg(message: Message):
    msg = message.text
    msg = msg.replace(" ", "", 1) if msg[1] == " " else msg
    split = msg[1:].replace("\n", " \n").split(" ")
    if " ".join(split[1:]).strip() == "":
        return ""
    return " ".join(split[1:])


def get_args(message: Message):
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


def get_args_from_caret(message):
    """Extract arguments from prefixed commands (supports all HARDCODED_PREFIXES)"""
    if not message.text:
        return []
    first_char = message.text[0]
    if first_char not in HARDCODED_PREFIXES:
        return []
    text = message.text[1:]
    parts = text.split()
    if len(parts) <= 1:
        return []
    return parts[1:]


def get_command_from_caret(message):
    """Extract command name from prefixed commands."""
    if not message.text:
        return ""
    first_char = message.text[0]
    if first_char not in HARDCODED_PREFIXES:
        return ""
    text = message.text[1:]
    parts = text.split()
    if not parts:
        return ""
    return parts[0]


async def run_cmd(cmd: str) -> Tuple[str, str, int, int]:
    """Run Commands"""
    args = shlex.split(cmd)
    process = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )
    stdout, stderr = await process.communicate()
    return (
        stdout.decode("utf-8", "replace").strip(),
        stderr.decode("utf-8", "replace").strip(),
        process.returncode,
        process.pid,
    )


async def convert_to_image(message, client) -> [None, str]:
    """Convert Most Media Formats To Raw Image"""
    if not message:
        return None
    if not message.reply_to_message:
        return None
    final_path = None
    if not (
        message.reply_to_message.video
        or message.reply_to_message.photo
        or message.reply_to_message.sticker
        or message.reply_to_message.media
        or message.reply_to_message.animation
        or message.reply_to_message.audio
    ):
        return None
    if message.reply_to_message.photo:
        final_path = await message.reply_to_message.download()
    elif message.reply_to_message.sticker:
        if message.reply_to_message.sticker.mime_type == "image/webp":
            final_path = "webp_to_png_s_proton.png"
            path_s = await message.reply_to_message.download()
            im = Image.open(path_s)
            im.save(final_path, "PNG")
        else:
            path_s = await client.download_media(message.reply_to_message)
            final_path = "lottie_proton.png"
            cmd = (
                f"lottie_convert.py --frame 0 -if lottie -of png {path_s} {final_path}"
            )
            await run_cmd(cmd)
    elif message.reply_to_message.audio:
        thumb = message.reply_to_message.audio.thumbs[0].file_id
        final_path = await client.download_media(thumb)
    elif message.reply_to_message.video or message.reply_to_message.animation:
        final_path = "fetched_thumb.png"
        vid_path = await client.download_media(message.reply_to_message)
        await run_cmd(f"ffmpeg -i {vid_path} -filter:v scale=500:500 -an {final_path}")
    return final_path


def get_full_name(user):
    if not user:
        return "Unknown"
    name = user.first_name or ""
    if user.last_name:
        name += f" {user.last_name}"
    return name or "Unknown"


def get_reply_text(reply: Message) -> str:
    if reply.photo:
        return "📷 Photo" + (f"\n{reply.caption}" if reply.caption else "")
    if reply.poll:
        q = reply.poll.question if reply.poll else ""
        return f"📊 Poll: {q}"
    if reply.location or reply.venue:
        return "📍 Location"
    if reply.contact:
        return "👤 Contact"
    if reply.animation:
        return "🖼 GIF"
    if reply.audio:
        title = reply.audio.title or "Unknown"
        performer = reply.audio.performer or ""
        return f"🎧 Music — {performer} - {title}" if performer else f"🎧 Music — {title}"
    if reply.video:
        return "📹 Video"
    if reply.video_note:
        return "📹 Videomessage"
    if reply.voice:
        return "🎵 Voice"
    if reply.sticker:
        emoji = reply.sticker.emoji + " " if reply.sticker.emoji else ""
        return f"{emoji}Sticker"
    if reply.document:
        return f"💾 File {reply.document.file_name}"
    if reply.game:
        return "🎮 Game"
    if reply.game_high_score:
        return "🎮 set new record"
    if reply.dice:
        return f"{reply.dice.emoji} - {reply.dice.value}"
    if reply.new_chat_members:
        member = reply.new_chat_members[0]
        if member.id == reply.from_user.id:
            return "👤 joined the group"
        return f"👤 invited {get_full_name(member)} to the group"
    if reply.left_chat_member:
        if reply.left_chat_member.id == reply.from_user.id:
            return "👤 left the group"
        return f"👤 removed {get_full_name(reply.left_chat_member)}"
    if reply.new_chat_title:
        return f"✏ changed group name to {reply.new_chat_title}"
    if reply.new_chat_photo:
        return "🖼 changed group photo"
    if reply.delete_chat_photo:
        return "🖼 removed group photo"
    if reply.pinned_message:
        return "📍 pinned message"
    if reply.video_chat_started:
        return "🎤 started a new video chat"
    if reply.video_chat_ended:
        return "🎤 ended the video chat"
    if reply.video_chat_members_invited:
        return "🎤 invited participants to the video chat"
    if reply.group_chat_created or reply.supergroup_chat_created:
        return "👥 created the group"
    if reply.channel_chat_created:
        return "👥 created the channel"
    return reply.text or "unsupported message"



def resize_image(image):
    im = Image.open(image)
    maxsize = (512, 512)
    if (im.width and im.height) < 512:
        size1 = im.width
        size2 = im.height
        if im.width > im.height:
            scale = 512 / size1
            size1new = 512
            size2new = size2 * scale
        else:
            scale = 512 / size2
            size1new = size1 * scale
            size2new = 512
        size1new = math.floor(size1new)
        size2new = math.floor(size2new)
        sizenew = (size1new, size2new)
        im = im.resize(sizenew)
    else:
        im.thumbnail(maxsize)
    file_name = "Sticker.png"
    im.save(file_name, "PNG")
    if os.path.exists(image):
        os.remove(image)
    return file_name


class Media_Info:
    def data(media: str) -> dict:
        "Get downloaded media's information"
        found = False
        media_info = MediaInfo.parse(media)
        for track in media_info.tracks:
            if track.track_type == "Video":
                found = True
                type_ = track.track_type
                format_ = track.format
                duration_1 = track.duration
                other_duration_ = track.other_duration
                duration_2 = (
                    f"{other_duration_[0]} - ({other_duration_[3]})"
                    if other_duration_
                    else None
                )
                pixel_ratio_ = [track.width, track.height]
                aspect_ratio_1 = track.display_aspect_ratio
                other_aspect_ratio_ = track.other_display_aspect_ratio
                aspect_ratio_2 = other_aspect_ratio_[0] if other_aspect_ratio_ else None
                fps_ = track.frame_rate
                fc_ = track.frame_count
                media_size_1 = track.stream_size
                other_media_size_ = track.other_stream_size
                media_size_2 = (
                    [
                        other_media_size_[1],
                        other_media_size_[2],
                        other_media_size_[3],
                        other_media_size_[4],
                    ]
                    if other_media_size_
                    else None
                )

        dict_ = (
            {
                "media_type": type_,
                "format": format_,
                "duration_in_ms": duration_1,
                "duration": duration_2,
                "pixel_sizes": pixel_ratio_,
                "aspect_ratio_in_fraction": aspect_ratio_1,
                "aspect_ratio": aspect_ratio_2,
                "frame_rate": fps_,
                "frame_count": fc_,
                "file_size_in_bytes": media_size_1,
                "file_size": media_size_2,
            }
            if found
            else None
        )
        return dict_


async def resize_media(media: str, video: bool, fast_forward: bool) -> str:
    if video:
        info_ = Media_Info.data(media)
        width = info_["pixel_sizes"][0]
        height = info_["pixel_sizes"][1]
        sec = info_["duration_in_ms"]
        s = round(float(sec)) / 1000

        if height == width:
            height, width = 512, 512
        elif height > width:
            height, width = 512, -1
        elif width > height:
            height, width = -1, 512

        resized_video = f"{media}.webm"
        if fast_forward:
            if s > 3:
                fract_ = 3 / s
                ff_f = round(fract_, 2)
                set_pts_ = ff_f - 0.01 if ff_f > fract_ else ff_f
                cmd_f = f"-filter:v 'setpts={set_pts_}*PTS',scale={width}:{height}"
            else:
                cmd_f = f"-filter:v scale={width}:{height}"
        else:
            cmd_f = f"-filter:v scale={width}:{height}"
        fps_ = float(info_["frame_rate"])
        fps_cmd = "-r 30 " if fps_ > 30 else ""
        cmd = f"ffmpeg -i {media} {cmd_f} -ss 00:00:00 -to 00:00:03 -an -c:v libvpx-vp9 {fps_cmd}-fs 256K {resized_video}"
        _, error, __, ___ = await run_cmd(cmd)
        os.remove(media)
        return resized_video

    image = Image.open(media)
    maxsize = 512
    scale = maxsize / max(image.width, image.height)
    new_size = (int(image.width * scale), int(image.height * scale))

    image = image.resize(new_size, Image.LANCZOS)
    resized_photo = "sticker.png"
    image.save(resized_photo)
    os.remove(media)
    return resized_photo


RAID = [
    "𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗚𝗛𝗨𝗧𝗞𝗔 𝗞𝗛𝗔𝗔𝗞𝗘 𝗧𝗛𝗢𝗢𝗞 𝗗𝗨𝗡𝗚𝗔 🤣🤣",
    "𝗧𝗘𝗥𝗘 𝗕𝗘́𝗛𝗘𝗡 𝗞 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗖𝗛𝗔𝗞𝗨 𝗗𝗔𝗔𝗟 𝗞𝗔𝗥 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗔 𝗞𝗛𝗢𝗢𝗡 𝗞𝗔𝗥 𝗗𝗨𝗚𝗔",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗡𝗛𝗜 𝗛𝗔𝗜 𝗞𝗬𝗔? 9 𝗠𝗔𝗛𝗜𝗡𝗘 𝗥𝗨𝗞 𝗦𝗔𝗚𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗗𝗘𝗧𝗔 𝗛𝗨 🤣🤣🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘 𝗔𝗘𝗥𝗢𝗣𝗟𝗔𝗡𝗘𝗣𝗔𝗥𝗞 𝗞𝗔𝗥𝗞𝗘 𝗨𝗗𝗔𝗔𝗡 𝗕𝗛𝗔𝗥 𝗗𝗨𝗚𝗔 ✈️🛫",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗦𝗨𝗧𝗟𝗜 𝗕𝗢𝗠𝗕 𝗙𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗝𝗛𝗔𝗔𝗧𝗘 𝗝𝗔𝗟 𝗞𝗘 𝗞𝗛𝗔𝗔𝗞 𝗛𝗢 𝗝𝗔𝗬𝗘𝗚𝗜💣",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗦𝗖𝗢𝗢𝗧𝗘𝗥 𝗗𝗔𝗔𝗟 𝗗𝗨𝗚𝗔👅",
    "𝗧𝗘𝗥𝗘 𝗕𝗘́𝗛𝗘𝗡 𝗞 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗖𝗛𝗔𝗞𝗨 𝗗𝗔𝗔𝗟 𝗞𝗔𝗥 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗔 𝗞𝗛𝗢𝗢𝗡 𝗞𝗔𝗥 𝗗𝗨𝗚𝗔",
    "𝗧𝗘𝗥𝗘 𝗕𝗘́𝗛𝗘𝗡 𝗞 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗖𝗛𝗔𝗞𝗨 𝗗𝗔𝗔𝗟 𝗞𝗔𝗥 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗔 𝗞𝗛𝗢𝗢𝗡 𝗞𝗔𝗥 𝗗𝗨𝗚𝗔",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗔𝗞𝗧𝗘 🤱 𝗚𝗔𝗟𝗜 𝗞𝗘 𝗞𝗨𝗧𝗧𝗢 🦮 𝗠𝗘 𝗕𝗔𝗔𝗧 𝗗𝗨𝗡𝗚𝗔 𝗣𝗛𝗜𝗥 🍞 𝗕𝗥𝗘𝗔𝗗 𝗞𝗜 𝗧𝗔𝗥𝗛 𝗞𝗛𝗔𝗬𝗘𝗡𝗚𝗘 𝗪𝗢 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧",
    "𝗗𝗨𝗗𝗛 𝗛𝗜𝗟𝗔𝗔𝗨𝗡𝗚𝗔 𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗘 𝗨𝗣𝗥 𝗡𝗜𝗖𝗛𝗘 🆙🆒😙",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 ✋ 𝗛𝗔𝗧𝗧𝗛 𝗗𝗔𝗟𝗞𝗘 👶 𝗕𝗔𝗖𝗖𝗛𝗘 𝗡𝗜𝗞𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 😍",
    "𝗧𝗘𝗥𝗜 𝗕𝗘𝗛𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗞𝗘𝗟𝗘 𝗞𝗘 𝗖𝗛𝗜𝗟𝗞𝗘 🍌🍌😍",
    "𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗨𝗦𝗘𝗥𝗕𝗢𝗧 𝗟𝗔𝗚𝗔𝗔𝗨𝗡𝗚𝗔 𝗦𝗔𝗦𝗧𝗘 𝗦𝗣𝗔𝗠 𝗞𝗘 𝗖𝗛𝗢𝗗𝗘",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗗𝗛𝗔𝗡𝗗𝗛𝗘 𝗩𝗔𝗔𝗟𝗜 😋😛",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘 𝗔𝗖 𝗟𝗔𝗚𝗔 𝗗𝗨𝗡𝗚𝗔 𝗦𝗔𝗔𝗥𝗜 𝗚𝗔𝗥𝗠𝗜 𝗡𝗜𝗞𝗔𝗟 𝗝𝗔𝗔𝗬𝗘𝗚𝗜",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗢 𝗛𝗢𝗥𝗟𝗜𝗖𝗞𝗦 𝗣𝗘𝗘𝗟𝗔𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗😚",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘 𝗦𝗔𝗥𝗜𝗬𝗔 𝗗𝗔𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 𝗨𝗦𝗜 𝗦𝗔𝗥𝗜𝗬𝗘 𝗣𝗥 𝗧𝗔𝗡𝗚 𝗞𝗘 𝗕𝗔𝗖𝗛𝗘 𝗣𝗔𝗜𝗗𝗔 𝗛𝗢𝗡𝗚𝗘 😱😱",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗢 𝗞𝗢𝗟𝗞𝗔𝗧𝗔 𝗩𝗔𝗔𝗟𝗘 𝗝𝗜𝗧𝗨 𝗕𝗛𝗔𝗜𝗬𝗔 𝗞𝗔 𝗟𝗨𝗡𝗗 𝗠𝗨𝗕𝗔𝗥𝗔𝗞 🤩🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗞𝗜 𝗙𝗔𝗡𝗧𝗔𝗦𝗬 𝗛𝗨 𝗟𝗔𝗪𝗗𝗘, 𝗧𝗨 𝗔𝗣𝗡𝗜 𝗕𝗛𝗘𝗡 𝗞𝗢 𝗦𝗠𝗕𝗛𝗔𝗔𝗟 😈😈",
    "𝗧𝗘𝗥𝗔 𝗣𝗘𝗛𝗟𝗔 𝗕𝗔𝗔𝗣 𝗛𝗨 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 ",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘 𝗫𝗩𝗜𝗗𝗘𝗢𝗦.𝗖𝗢𝗠 𝗖𝗛𝗔𝗟𝗔 𝗞𝗘 𝗠𝗨𝗧𝗛 𝗠𝗔́𝗔̀𝗥𝗨𝗡𝗚𝗔 🤡😹",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗔 𝗚𝗥𝗢𝗨𝗣 𝗩𝗔𝗔𝗟𝗢𝗡 𝗦𝗔𝗔𝗧𝗛 𝗠𝗜𝗟𝗞𝗘 𝗚𝗔𝗡𝗚 𝗕𝗔𝗡𝗚 𝗞𝗥𝗨𝗡𝗚𝗔🙌🏻☠️ ",
    "𝗧𝗘𝗥𝗜 𝗜𝗧𝗘𝗠 𝗞𝗜 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘 𝗟𝗨𝗡𝗗 𝗗𝗔𝗔𝗟𝗞𝗘,𝗧𝗘𝗥𝗘 𝗝𝗔𝗜𝗦𝗔 𝗘𝗞 𝗢𝗥 𝗡𝗜𝗞𝗔𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗🤘🏻🙌🏻☠️ ",
    "𝗔𝗨𝗞𝗔𝗔𝗧 𝗠𝗘 𝗥𝗘𝗛 𝗩𝗥𝗡𝗔 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘 𝗗𝗔𝗡𝗗𝗔 𝗗𝗔𝗔𝗟 𝗞𝗘 𝗠𝗨𝗛 𝗦𝗘 𝗡𝗜𝗞𝗔𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 𝗦𝗛𝗔𝗥𝗜𝗥 𝗕𝗛𝗜 𝗗𝗔𝗡𝗗𝗘 𝗝𝗘𝗦𝗔 𝗗𝗜𝗞𝗛𝗘𝗚𝗔 🙄🤭🤭",
    "𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗞𝗘 𝗦𝗔𝗔𝗧𝗛 𝗟𝗨𝗗𝗢 𝗞𝗛𝗘𝗟𝗧𝗘 𝗞𝗛𝗘𝗟𝗧𝗘 𝗨𝗦𝗞𝗘 𝗠𝗨𝗛 𝗠𝗘 𝗔𝗣𝗡𝗔 𝗟𝗢𝗗𝗔 𝗗𝗘 𝗗𝗨𝗡𝗚𝗔☝🏻☝🏻😬",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗢 𝗔𝗣𝗡𝗘 𝗟𝗨𝗡𝗗 𝗣𝗥 𝗜𝗧𝗡𝗔 𝗝𝗛𝗨𝗟𝗔𝗔𝗨𝗡𝗚𝗔 𝗞𝗜 𝗝𝗛𝗨𝗟𝗧𝗘 𝗝𝗛𝗨𝗟𝗧𝗘 𝗛𝗜 𝗕𝗔𝗖𝗛𝗔 𝗣𝗔𝗜𝗗𝗔 𝗞𝗥 𝗗𝗘𝗚𝗜👀👯 ",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗕𝗔𝗧𝗧𝗘𝗥𝗬 𝗟𝗔𝗚𝗔 𝗞𝗘 𝗣𝗢𝗪𝗘𝗥𝗕𝗔𝗡𝗞 𝗕𝗔𝗡𝗔 𝗗𝗨𝗡𝗚𝗔 🔋 🔥🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗖++ 𝗦𝗧𝗥𝗜𝗡𝗚 𝗘𝗡𝗖𝗥𝗬𝗣𝗧𝗜𝗢𝗡 𝗟𝗔𝗚𝗔 𝗗𝗨𝗡𝗚𝗔 𝗕𝗔𝗛𝗧𝗜 𝗛𝗨𝗬𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗥𝗨𝗞 𝗝𝗔𝗬𝗘𝗚𝗜𝗜𝗜𝗜😈🔥😍",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘𝗜 𝗝𝗛𝗔𝗔𝗗𝗨 𝗗𝗔𝗟 𝗞𝗘 𝗠𝗢𝗥 🦚 𝗕𝗔𝗡𝗔 𝗗𝗨𝗡𝗚𝗔𝗔 🤩🥵😱",
    "𝗧𝗘𝗥𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗦𝗛𝗢𝗨𝗟𝗗𝗘𝗥𝗜𝗡𝗚 𝗞𝗔𝗥 𝗗𝗨𝗡𝗚𝗔𝗔 𝗛𝗜𝗟𝗔𝗧𝗘 𝗛𝗨𝗬𝗘 𝗕𝗛𝗜 𝗗𝗔𝗥𝗗 𝗛𝗢𝗚𝗔𝗔𝗔😱🤮👺",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗢 𝗥𝗘𝗗𝗜 𝗣𝗘 𝗕𝗔𝗜𝗧𝗛𝗔𝗟 𝗞𝗘 𝗨𝗦𝗦𝗘 𝗨𝗦𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗕𝗜𝗟𝗪𝗔𝗨𝗡𝗚𝗔𝗔 💰 😵🤩",
    "𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 4 𝗛𝗢𝗟𝗘 𝗛𝗔𝗜 𝗨𝗡𝗠𝗘 𝗠𝗦𝗘𝗔𝗟 𝗟𝗔𝗚𝗔 𝗕𝗔𝗛𝗨𝗧 𝗕𝗔𝗛𝗘𝗧𝗜 𝗛𝗔𝗜 𝗕𝗛𝗢𝗙𝗗𝗜𝗞𝗘👊🤮🤢🤢",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗕𝗔𝗥𝗚𝗔𝗗 𝗞𝗔 𝗣𝗘𝗗 𝗨𝗚𝗔 𝗗𝗨𝗡𝗚𝗔𝗔 𝗖𝗢𝗥𝗢𝗡𝗔 𝗠𝗘𝗜 𝗦𝗔𝗕 𝗢𝗫𝗬𝗚𝗘𝗡 𝗟𝗘𝗞𝗔𝗥 𝗝𝗔𝗬𝗘𝗡𝗚𝗘🤢🤩🥳",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗦𝗨𝗗𝗢 𝗟𝗔𝗚𝗔 𝗞𝗘 𝗕𝗜𝗚𝗦𝗣𝗔𝗠 𝗟𝗔𝗚𝗔 𝗞𝗘 9999 𝗙𝗨𝗖𝗞 𝗟𝗔𝗚𝗔𝗔 𝗗𝗨 🤩🥳🔥",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗡 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘 𝗠𝗘𝗜 𝗕𝗘𝗦𝗔𝗡 𝗞𝗘 𝗟𝗔𝗗𝗗𝗨 𝗕𝗛𝗔𝗥 𝗗𝗨𝗡𝗚𝗔🤩🥳🔥😈",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗛𝗢𝗗 𝗞𝗘 𝗨𝗦𝗠𝗘 𝗖𝗬𝗟𝗜𝗡𝗗𝗘𝗥 ⛽️ 𝗙𝗜𝗧 𝗞𝗔𝗥𝗞𝗘 𝗨𝗦𝗠𝗘𝗘 𝗗𝗔𝗟 𝗠𝗔𝗞𝗛𝗔𝗡𝗜 𝗕𝗔𝗡𝗔𝗨𝗡𝗚𝗔𝗔𝗔🤩👊🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗦𝗛𝗘𝗘𝗦𝗛𝗔 𝗗𝗔𝗟 𝗗𝗨𝗡𝗚𝗔𝗔𝗔 𝗔𝗨𝗥 𝗖𝗛𝗔𝗨𝗥𝗔𝗛𝗘 𝗣𝗘 𝗧𝗔𝗔𝗡𝗚 𝗗𝗨𝗡𝗚𝗔 𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘😈😱🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗖𝗥𝗘𝗗𝗜𝗧 𝗖𝗔𝗥𝗗 𝗗𝗔𝗟 𝗞𝗘 𝗔𝗚𝗘 𝗦𝗘 500 𝗞𝗘 𝗞𝗔𝗔𝗥𝗘 𝗞𝗔𝗔𝗥𝗘 𝗡𝗢𝗧𝗘 𝗡𝗜𝗞𝗔𝗟𝗨𝗡𝗚𝗔𝗔 𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘💰💰🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗦𝗔𝗧𝗛 𝗦𝗨𝗔𝗥 𝗞𝗔 𝗦𝗘𝗫 𝗞𝗔𝗥𝗪𝗔 𝗗𝗨𝗡𝗚𝗔𝗔 𝗘𝗞 𝗦𝗔𝗧𝗛 6-6 𝗕𝗔𝗖𝗛𝗘 𝗗𝗘𝗚𝗜💰🔥😱",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗔𝗣𝗣𝗟𝗘 𝗞𝗔 18𝗪 𝗪𝗔𝗟𝗔 𝗖𝗛𝗔𝗥𝗚𝗘𝗥 🔥🤩",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘𝗜 𝗢𝗡𝗘𝗣𝗟𝗨𝗦 𝗞𝗔 𝗪𝗥𝗔𝗣 𝗖𝗛𝗔𝗥𝗚𝗘𝗥 30𝗪 𝗛𝗜𝗚𝗛 𝗣𝗢𝗪𝗘𝗥 💥😂😎",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗢 𝗔𝗠𝗔𝗭𝗢𝗡 𝗦𝗘 𝗢𝗥𝗗𝗘𝗥 𝗞𝗔𝗥𝗨𝗡𝗚𝗔 10 𝗿𝘀 𝗠𝗘𝗜 𝗔𝗨𝗥 𝗙𝗟𝗜𝗣𝗞𝗔𝗥𝗧 𝗣𝗘 20 𝗥𝗦 𝗠𝗘𝗜 𝗕𝗘𝗖𝗛 𝗗𝗨𝗡𝗚𝗔🤮👿😈🤖",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗕𝗔𝗗𝗜 𝗕𝗛𝗨𝗡𝗗 𝗠𝗘 𝗭𝗢𝗠𝗔𝗧𝗢 𝗗𝗔𝗟 𝗞𝗘 𝗦𝗨𝗕𝗪𝗔𝗬 𝗞𝗔 𝗕𝗙𝗙 𝗩𝗘𝗚 𝗦𝗨𝗕 𝗖𝗢𝗠𝗕𝗢 [15𝗰𝗺 , 16 𝗶𝗻𝗰𝗵𝗲𝘀 ] 𝗢𝗥𝗗𝗘𝗥 𝗖𝗢𝗗 𝗞𝗥𝗩𝗔𝗨𝗡𝗚𝗔 𝗢𝗥 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗝𝗔𝗕 𝗗𝗜𝗟𝗜𝗩𝗘𝗥𝗬 𝗗𝗘𝗡𝗘 𝗔𝗬𝗘𝗚𝗜 𝗧𝗔𝗕 𝗨𝗦𝗣𝗘 𝗝𝗔𝗔𝗗𝗨 𝗞𝗥𝗨𝗡𝗚𝗔 𝗢𝗥 𝗙𝗜𝗥 9 𝗠𝗢𝗡𝗧𝗛 𝗕𝗔𝗔𝗗 𝗩𝗢 𝗘𝗞 𝗢𝗥 𝗙𝗥𝗘𝗘 𝗗𝗜𝗟𝗜𝗩𝗘𝗥𝗬 𝗗𝗘𝗚𝗜🙀👍🥳🔥",
    "𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗔𝗔𝗟𝗜🙁🤣💥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗖𝗛𝗔𝗡𝗚𝗘𝗦 𝗖𝗢𝗠𝗠𝗜𝗧 𝗞𝗥𝗨𝗚𝗔 𝗙𝗜𝗥 𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗔𝗨𝗧𝗢𝗠𝗔𝗧𝗜𝗖𝗔𝗟𝗟𝗬 𝗨𝗣𝗗𝗔𝗧𝗘 𝗛𝗢𝗝𝗔𝗔𝗬𝗘𝗚𝗜🤖🙏🤔",
    "𝗧𝗘𝗥𝗜 𝗠𝗔𝗨𝗦𝗜 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗜𝗡𝗗𝗜𝗔𝗡 𝗥𝗔𝗜𝗟𝗪𝗔𝗬 🚂💥😂",
    "𝗧𝗨 𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗧𝗘𝗥𝗔 𝗞𝗛𝗔𝗡𝗗𝗔𝗡 𝗦𝗔𝗕 𝗕𝗔𝗛𝗘𝗡 𝗞𝗘 𝗟𝗔𝗪𝗗𝗘 𝗥Æ𝗡𝗗𝗜 𝗛𝗔𝗜 𝗥Æ𝗡𝗗𝗜 🤢✅🔥",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗜𝗢𝗡𝗜𝗖 𝗕𝗢𝗡𝗗 𝗕𝗔𝗡𝗔 𝗞𝗘 𝗩𝗜𝗥𝗚𝗜𝗡𝗜𝗧𝗬 𝗟𝗢𝗢𝗦𝗘 𝗞𝗔𝗥𝗪𝗔 𝗗𝗨𝗡𝗚𝗔 𝗨𝗦𝗞𝗜 📚 😎🤩",
    "𝗧𝗘𝗥𝗜 𝗥Æ𝗡𝗗𝗜 𝗠𝗔́𝗔̀ 𝗦𝗘 𝗣𝗨𝗖𝗛𝗡𝗔 𝗕𝗔𝗔𝗣 𝗞𝗔 𝗡𝗔𝗔𝗠 𝗕𝗔𝗛𝗘𝗡 𝗞𝗘 𝗟𝗢𝗗𝗘𝗘𝗘𝗘𝗘 🤩🥳😳",
    "𝗧𝗨 𝗔𝗨𝗥 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗗𝗢𝗡𝗢 𝗞𝗜 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗠𝗘𝗧𝗥𝗢 𝗖𝗛𝗔𝗟𝗪𝗔 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔𝗗𝗔𝗥𝗫𝗛𝗢𝗗 🚇🤩😱🥶",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗢 𝗜𝗧𝗡𝗔 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 𝗧𝗘𝗥𝗔 𝗕𝗔𝗔𝗣 𝗕𝗛𝗜 𝗨𝗦𝗞𝗢 𝗣𝗔𝗛𝗖𝗛𝗔𝗡𝗔𝗡𝗘 𝗦𝗘 𝗠𝗔𝗡𝗔 𝗞𝗔𝗥 𝗗𝗘𝗚𝗔😂👿🤩",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗛𝗔𝗜𝗥 𝗗𝗥𝗬𝗘𝗥 𝗖𝗛𝗔𝗟𝗔 𝗗𝗨𝗡𝗚𝗔𝗔💥🔥🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗧𝗘𝗟𝗘𝗚𝗥𝗔𝗠 𝗞𝗜 𝗦𝗔𝗥𝗜 𝗥Æ𝗡𝗗𝗜𝗬𝗢𝗡 𝗞𝗔 𝗥Æ𝗡𝗗𝗜 𝗞𝗛𝗔𝗡𝗔 𝗞𝗛𝗢𝗟 𝗗𝗨𝗡𝗚𝗔𝗔👿🤮😎",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗔𝗟𝗘𝗫𝗔 𝗗𝗔𝗟 𝗞𝗘𝗘 𝗗𝗝 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔𝗔𝗔 🎶 ⬆️🤩💥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗚𝗜𝗧𝗛𝗨𝗕 𝗗𝗔𝗟 𝗞𝗘 𝗔𝗣𝗡𝗔 𝗕𝗢𝗧 𝗛𝗢𝗦𝗧 𝗞𝗔𝗥𝗨𝗡𝗚𝗔𝗔 🤩👊👤😍",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗔 𝗩𝗣𝗦 𝗕𝗔𝗡𝗔 𝗞𝗘 24*7 𝗕𝗔𝗦𝗛 𝗖𝗛𝗨𝗗𝗔𝗜 𝗖𝗢𝗠𝗠𝗔𝗡𝗗 𝗗𝗘 𝗗𝗨𝗡𝗚𝗔𝗔 🤩💥🔥🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗧𝗘𝗥𝗘 𝗟𝗔𝗡𝗗 𝗞𝗢 𝗗𝗔𝗟 𝗞𝗘 𝗞𝗔𝗔𝗧 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 🔪😂🔥",
    "𝗦𝗨𝗡 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 𝗔𝗨𝗥 𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗔 𝗕𝗛𝗜 𝗕𝗛𝗢𝗦𝗗𝗔 👿😎👊",
    "𝗧𝗨𝗝𝗛𝗘 𝗗𝗘𝗞𝗛 𝗞𝗘 𝗧𝗘𝗥𝗜 𝗥Æ𝗡𝗗𝗜 𝗕𝗔𝗛𝗘𝗡 𝗣𝗘 𝗧𝗔𝗥𝗔𝗦 𝗔𝗧𝗔 𝗛𝗔𝗜 𝗠𝗨𝗝𝗛𝗘 𝗕𝗔𝗛𝗘𝗡 𝗞𝗘 𝗟𝗢𝗗𝗘𝗘𝗘𝗘 👿💥🤩🔥",
    "𝗦𝗨𝗡 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 𝗝𝗬𝗔𝗗𝗔 𝗡𝗔 𝗨𝗖𝗛𝗔𝗟 𝗠𝗔́𝗔̀ 𝗖𝗛𝗢𝗗 𝗗𝗘𝗡𝗚𝗘 𝗘𝗞 𝗠𝗜𝗡 𝗠𝗘𝗜 ✅🤣🔥🤩",
    "𝗔𝗣𝗡𝗜 𝗔𝗠𝗠𝗔 𝗦𝗘 𝗣𝗨𝗖𝗛𝗡𝗔 𝗨𝗦𝗞𝗢 𝗨𝗦 𝗞𝗔𝗔𝗟𝗜 𝗥𝗔𝗔𝗧 𝗠𝗘𝗜 𝗞𝗔𝗨𝗡 𝗖𝗛𝗢𝗗𝗡𝗘𝗘 𝗔𝗬𝗔 𝗧𝗛𝗔𝗔𝗔! 𝗧𝗘𝗥𝗘 𝗜𝗦 𝗣𝗔𝗣𝗔 𝗞𝗔 𝗡𝗔𝗔𝗠 𝗟𝗘𝗚𝗜 😂👿😳",
    "𝗧𝗢𝗛𝗔𝗥 𝗕𝗔𝗛𝗜𝗡 𝗖𝗛𝗢𝗗𝗨 𝗕𝗕𝗔𝗛𝗘𝗡 𝗞𝗘 𝗟𝗔𝗪𝗗𝗘 𝗨𝗦𝗠𝗘 𝗠𝗜𝗧𝗧𝗜 𝗗𝗔𝗟 𝗞𝗘 𝗖𝗘𝗠𝗘𝗡𝗧 𝗦𝗘 𝗕𝗛𝗔𝗥 𝗗𝗨 🏠🤢🤩💥",
    "𝗧𝗨𝗝𝗛𝗘 𝗔𝗕 𝗧𝗔𝗞 𝗡𝗔𝗛𝗜 𝗦𝗠𝗝𝗛 𝗔𝗬𝗔 𝗞𝗜 𝗠𝗔𝗜 𝗛𝗜 𝗛𝗨 𝗧𝗨𝗝𝗛𝗘 𝗣𝗔𝗜𝗗𝗔 𝗞𝗔𝗥𝗡𝗘 𝗪𝗔𝗟𝗔 𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘𝗘 𝗔𝗣𝗡𝗜 𝗠𝗔́𝗔̀ 𝗦𝗘 𝗣𝗨𝗖𝗛 𝗥Æ𝗡𝗗𝗜 𝗞𝗘 𝗕𝗔𝗖𝗛𝗘𝗘𝗘𝗘 🤩👊👤😍",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘𝗜 𝗦𝗣𝗢𝗧𝗜𝗙𝗬 𝗗𝗔𝗟 𝗞𝗘 𝗟𝗢𝗙𝗜 𝗕𝗔𝗝𝗔𝗨𝗡𝗚𝗔 𝗗𝗜𝗡 𝗕𝗛𝗔𝗥 😍🎶🎶💥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗔 𝗡𝗔𝗬𝗔 𝗥Æ𝗡𝗗𝗜 𝗞𝗛𝗔𝗡𝗔 𝗞𝗛𝗢𝗟𝗨𝗡𝗚𝗔 𝗖𝗛𝗜𝗡𝗧𝗔 𝗠𝗔𝗧 𝗞𝗔𝗥 👊🤣🤣😳",
    "𝗧𝗘𝗥𝗔 𝗕𝗔𝗔𝗣 𝗛𝗨 𝗕𝗛𝗢𝗦𝗗𝗜𝗞𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔𝗔 𝗞𝗢 𝗥Æ𝗡𝗗𝗜 𝗞𝗛𝗔𝗡𝗘 𝗣𝗘 𝗖𝗛𝗨𝗗𝗪𝗔 𝗞𝗘 𝗨𝗦 𝗣𝗔𝗜𝗦𝗘 𝗞𝗜 𝗗𝗔𝗔𝗥𝗨 𝗣𝗘𝗘𝗧𝗔 𝗛𝗨 🍷🤩🔥",
    "𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗧 𝗠𝗘𝗜 𝗔𝗣𝗡𝗔 𝗕𝗔𝗗𝗔 𝗦𝗔 𝗟𝗢𝗗𝗔 𝗚𝗛𝗨𝗦𝗦𝗔 𝗗𝗨𝗡𝗚𝗔𝗔 𝗞𝗔𝗟𝗟𝗔𝗔𝗣 𝗞𝗘 𝗠𝗔𝗥 𝗝𝗔𝗬𝗘𝗚𝗜 🤩😳😳🔥",
    "𝗧𝗢𝗛𝗔𝗥 𝗠𝗨𝗠𝗠𝗬 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘𝗜 𝗣𝗨𝗥𝗜 𝗞𝗜 𝗣𝗨𝗥𝗜 𝗞𝗜𝗡𝗚𝗙𝗜𝗦𝗛𝗘𝗥 𝗞𝗜 𝗕𝗢𝗧𝗧𝗟𝗘 𝗗𝗔𝗟 𝗞𝗘 𝗧𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗔𝗡𝗗𝗘𝗥 𝗛𝗜 😱😂🤩",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗢 𝗜𝗧𝗡𝗔 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 𝗞𝗜 𝗦𝗔𝗣𝗡𝗘 𝗠𝗘𝗜 𝗕𝗛𝗜 𝗠𝗘𝗥𝗜 𝗖𝗛𝗨𝗗𝗔𝗜 𝗬𝗔𝗔𝗗 𝗞𝗔𝗥𝗘𝗚𝗜 𝗥Æ𝗡𝗗𝗜 🥳😍👊💥",
    "𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗔𝗨𝗥 𝗕𝗔𝗛𝗘𝗡 𝗞𝗢 𝗗𝗔𝗨𝗗𝗔 𝗗𝗔𝗨𝗗𝗔 𝗡𝗘 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 𝗨𝗡𝗞𝗘 𝗡𝗢 𝗕𝗢𝗟𝗡𝗘 𝗣𝗘 𝗕𝗛𝗜 𝗟𝗔𝗡𝗗 𝗚𝗛𝗨𝗦𝗔 𝗗𝗨𝗡𝗚𝗔 𝗔𝗡𝗗𝗘𝗥 𝗧𝗔𝗞 😎😎🤣🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗞𝗢 𝗢𝗡𝗟𝗜𝗡𝗘 𝗢𝗟𝗫 𝗣𝗘 𝗕𝗘𝗖𝗛𝗨𝗡𝗚𝗔 𝗔𝗨𝗥 𝗣𝗔𝗜𝗦𝗘 𝗦𝗘 𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗔 𝗞𝗢𝗧𝗛𝗔 𝗞𝗛𝗢𝗟 𝗗𝗨𝗡𝗚𝗔 😎🤩😝😍",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗔 𝗜𝗧𝗡𝗔 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 𝗞𝗜 𝗧𝗨 𝗖𝗔𝗛 𝗞𝗘 𝗕𝗛𝗜 𝗪𝗢 𝗠𝗔𝗦𝗧 𝗖𝗛𝗨𝗗𝗔𝗜 𝗦𝗘 𝗗𝗨𝗥 𝗡𝗛𝗜 𝗝𝗔 𝗣𝗔𝗬𝗘𝗚𝗔𝗔 😏😏🤩😍",
    "𝗦𝗨𝗡 𝗕𝗘 𝗥Æ𝗡𝗗𝗜 𝗞𝗜 𝗔𝗨𝗟𝗔𝗔𝗗 𝗧𝗨 𝗔𝗣𝗡𝗜 𝗕𝗔𝗛𝗘𝗡 𝗦𝗘 𝗦𝗘𝗘𝗞𝗛 𝗞𝗨𝗖𝗛 𝗞𝗔𝗜𝗦𝗘 𝗚𝗔𝗔𝗡𝗗 𝗠𝗔𝗥𝗪𝗔𝗧𝗘 𝗛𝗔𝗜😏🤬🔥💥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗔 𝗬𝗔𝗔𝗥 𝗛𝗨 𝗠𝗘𝗜 𝗔𝗨𝗥 𝗧𝗘𝗥𝗜 𝗕𝗔𝗛𝗘𝗡 𝗞𝗔 𝗣𝗬𝗔𝗔𝗥 𝗛𝗨 𝗠𝗘𝗜 𝗔𝗝𝗔 𝗠𝗘𝗥𝗔 𝗟𝗔𝗡𝗗 𝗖𝗛𝗢𝗢𝗦 𝗟𝗘 🤩🤣💥",
    "𝗧𝗘𝗥𝗜 𝗕𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗨𝗦𝗘𝗥𝗕𝗢𝗧 𝗟𝗔𝗚𝗔𝗔𝗨𝗡𝗚𝗔 𝗦𝗔𝗦𝗧𝗘 𝗦𝗣𝗔𝗠 𝗞𝗘 𝗖𝗛𝗢𝗗𝗘",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘 𝗦𝗔𝗥𝗜𝗬𝗔 𝗗𝗔𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 𝗨𝗦𝗜 𝗦𝗔𝗥𝗜𝗬𝗘 𝗣𝗥 𝗧𝗔𝗡𝗚 𝗞𝗘 𝗕𝗔𝗖𝗛𝗘 𝗣𝗔𝗜𝗗𝗔 𝗛𝗢𝗡𝗚𝗘 😱😱",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 ✋ 𝗛𝗔𝗧𝗧𝗛 𝗗𝗔𝗟𝗞𝗘 👶 𝗕𝗔𝗖𝗖𝗛𝗘 𝗡𝗜𝗞𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 😍",
    "𝗧𝗘𝗥𝗜 𝗕𝗘𝗛𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗞𝗘𝗟𝗘 𝗞𝗘 𝗖𝗛𝗜𝗟𝗞𝗘 🤤🤤",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧 𝗠𝗘 𝗦𝗨𝗧𝗟𝗜 𝗕𝗢𝗠𝗕 𝗙𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗞𝗜 𝗝𝗛𝗔𝗔𝗧𝗘 𝗝𝗔𝗟 𝗞𝗘 𝗞𝗛𝗔𝗔𝗞 𝗛𝗢 𝗝𝗔𝗬𝗘𝗚𝗜💣💋",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗢 𝗛𝗢𝗥𝗟𝗜𝗖𝗞𝗦 𝗣𝗘𝗘𝗟𝗔𝗞𝗘 𝗖𝗛𝗢𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗😚",
    "𝗧𝗘𝗥𝗜 𝗜𝗧𝗘𝗠 𝗞𝗜 𝗚𝗔𝗔𝗡𝗗 𝗠𝗘 𝗟𝗨𝗡𝗗 𝗗𝗔𝗔𝗟𝗞𝗘,𝗧𝗘𝗥𝗘 𝗝𝗔𝗜𝗦𝗔 𝗘𝗞 𝗢𝗥 𝗡𝗜𝗞𝗔𝗔𝗟 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗😆🤤💋",
    "𝗧𝗘𝗥𝗜 𝗩𝗔𝗛𝗘𝗘𝗡 𝗞𝗢 𝗔𝗣𝗡𝗘 𝗟𝗨𝗡𝗗 𝗣𝗥 𝗜𝗧𝗡𝗔 𝗝𝗛𝗨𝗟𝗔𝗔𝗨𝗡𝗚𝗔 𝗞𝗜 𝗝𝗛𝗨𝗟𝗧𝗘 𝗝𝗛𝗨𝗟𝗧𝗘 𝗛𝗜 𝗕𝗔𝗖𝗛𝗔 𝗣𝗔𝗜𝗗𝗔 𝗞𝗥 𝗗𝗘𝗚𝗜 💦💋",
    "𝗦𝗨𝗔𝗥 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗦𝗔𝗗𝗔𝗞 𝗣𝗥 𝗟𝗜𝗧𝗔𝗞𝗘 𝗖𝗛𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 😂😆🤤",
    "𝗔𝗕𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 𝗠𝗔𝗗𝗘𝗥𝗖𝗛𝗢𝗢𝗗 𝗞𝗥 𝗣𝗜𝗟𝗟𝗘 𝗣𝗔𝗣𝗔 𝗦𝗘 𝗟𝗔𝗗𝗘𝗚𝗔 𝗧𝗨 😼😂🤤",
    "𝗚𝗔𝗟𝗜 𝗚𝗔𝗟𝗜 𝗡𝗘 𝗦𝗛𝗢𝗥 𝗛𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀ 𝗥Æ𝗡𝗗𝗜 𝗖𝗛𝗢𝗥 𝗛𝗘 💋💋💦",
    "𝗔𝗕𝗘 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢 𝗖𝗛𝗢𝗗𝗨 𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 𝗞𝗨𝗧𝗧𝗘 𝗞𝗘 𝗖𝗛𝗢𝗗𝗘 😂👻🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗔𝗜𝗦𝗘 𝗖𝗛𝗢𝗗𝗔 𝗔𝗜𝗦𝗘 𝗖𝗛𝗢𝗗𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔 𝗕𝗘𝗗 𝗣𝗘𝗛𝗜 𝗠𝗨𝗧𝗛 𝗗𝗜𝗔 💦💦💦💦",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗘 𝗕𝗛𝗢𝗦𝗗𝗘 𝗠𝗘 𝗔𝗔𝗔𝗚 𝗟𝗔𝗚𝗔𝗗𝗜𝗔 𝗠𝗘𝗥𝗔 𝗠𝗢𝗧𝗔 𝗟𝗨𝗡𝗗 𝗗𝗔𝗟𝗞𝗘 🔥🔥💦😆😆",
    "𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗕𝗔𝗖𝗛𝗛𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗖𝗛𝗢𝗗𝗨 𝗖𝗛𝗔𝗟 𝗡𝗜𝗞𝗔𝗟",
    "𝗞𝗜𝗧𝗡𝗔 𝗖𝗛𝗢𝗗𝗨 𝗧𝗘𝗥𝗜 𝗥Æ𝗡𝗗𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗔𝗕𝗕 𝗔𝗣𝗡𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢 𝗕𝗛𝗘𝗝 😆👻🤤",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢𝗧𝗢 𝗖𝗛𝗢𝗗 𝗖𝗛𝗢𝗗𝗞𝗘 𝗣𝗨𝗥𝗔 𝗙𝗔𝗔𝗗 𝗗𝗜𝗔 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗔𝗕𝗕 𝗧𝗘𝗥𝗜 𝗚𝗙 𝗞𝗢 𝗕𝗛𝗘𝗝 😆💦🤤",
    "𝗧𝗘𝗥𝗜 𝗚𝗙 𝗞𝗢 𝗘𝗧𝗡𝗔 𝗖𝗛𝗢𝗗𝗔 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗘 𝗟𝗢𝗗𝗘 𝗧𝗘𝗥𝗜 𝗚𝗙 𝗧𝗢 𝗠𝗘𝗥𝗜 𝗥Æ𝗡𝗗𝗜 𝗕𝗔𝗡𝗚𝗔𝗬𝗜 𝗔𝗕𝗕 𝗖𝗛𝗔𝗟 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗖𝗛𝗢𝗗𝗧𝗔 𝗙𝗜𝗥𝗦𝗘 ♥️💦😆😆😆😆",
    "𝗛𝗔𝗥𝗜 𝗛𝗔𝗥𝗜 𝗚𝗛𝗔𝗔𝗦 𝗠𝗘 𝗝𝗛𝗢𝗣𝗗𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 🤣🤣💋💦",
    "𝗖𝗛𝗔𝗟 𝗧𝗘𝗥𝗘 𝗕𝗔𝗔𝗣 𝗞𝗢 𝗕𝗛𝗘𝗝 𝗧𝗘𝗥𝗔 𝗕𝗔𝗦𝗞𝗔 𝗡𝗛𝗜 𝗛𝗘 𝗣𝗔𝗣𝗔 𝗦𝗘 𝗟𝗔𝗗𝗘𝗚𝗔 𝗧𝗨",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗠𝗘 𝗕𝗢𝗠𝗕 𝗗𝗔𝗟𝗞𝗘 𝗨𝗗𝗔 𝗗𝗨𝗡𝗚𝗔 𝗠𝗔́𝗔̀𝗞𝗘 𝗟𝗔𝗪𝗗𝗘",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗧𝗥𝗔𝗜𝗡 𝗠𝗘 𝗟𝗘𝗝𝗔𝗞𝗘 𝗧𝗢𝗣 𝗕𝗘𝗗 𝗣𝗘 𝗟𝗜𝗧𝗔𝗞𝗘 𝗖𝗛𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗦𝗨𝗔𝗥 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 🤣🤣💋💋",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔𝗞𝗘 𝗡𝗨𝗗𝗘𝗦 𝗚𝗢𝗢𝗚𝗟𝗘 𝗣𝗘 𝗨𝗣𝗟𝗢𝗔𝗗 𝗞𝗔𝗥𝗗𝗨𝗡𝗚𝗔 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗘 𝗟𝗔𝗘𝗪𝗗𝗘 👻🔥",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔𝗞𝗘 𝗡𝗨𝗗𝗘𝗦 𝗚𝗢𝗢𝗚𝗟𝗘 𝗣𝗘 𝗨𝗣𝗟𝗢𝗔𝗗 𝗞𝗔𝗥𝗗𝗨𝗡𝗚𝗔 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗘 𝗟𝗔𝗘𝗪𝗗𝗘 👻🔥",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢 𝗖𝗛𝗢𝗗 𝗖𝗛𝗢𝗗𝗞𝗘 𝗩𝗜𝗗𝗘𝗢 𝗕𝗔𝗡𝗔𝗞𝗘 𝗫𝗡𝗫𝗫.𝗖𝗢𝗠 𝗣𝗘 𝗡𝗘𝗘𝗟𝗔𝗠 𝗞𝗔𝗥𝗗𝗨𝗡𝗚𝗔 𝗞𝗨𝗧𝗧𝗘 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 💦💋",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔𝗞𝗜 𝗖𝗛𝗨𝗗𝗔𝗜 𝗞𝗢 𝗣𝗢𝗥𝗡𝗛𝗨𝗕.𝗖𝗢𝗠 𝗣𝗘 𝗨𝗣𝗟𝗢𝗔𝗗 𝗞𝗔𝗥𝗗𝗨𝗡𝗚𝗔 𝗦𝗨𝗔𝗥 𝗞𝗘 𝗖𝗛𝗢𝗗𝗘 🤣💋💦",
    "𝗔𝗕𝗘 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢 𝗖𝗛𝗢𝗗𝗨 𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗕𝗔𝗖𝗛𝗛𝗘 𝗧𝗘𝗥𝗘𝗞𝗢 𝗖𝗛𝗔𝗞𝗞𝗢 𝗦𝗘 𝗣𝗜𝗟𝗪𝗔𝗩𝗨𝗡𝗚𝗔 𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗕𝗔𝗖𝗛𝗛𝗘 🤣🤣",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗙𝗔𝗔𝗗𝗞𝗘 𝗥𝗔𝗞𝗗𝗜𝗔 𝗠𝗔́𝗔̀𝗞𝗘 𝗟𝗢𝗗𝗘 𝗝𝗔𝗔 𝗔𝗕𝗕 𝗦𝗜𝗟𝗪𝗔𝗟𝗘 👄👄",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗠𝗘 𝗠𝗘𝗥𝗔 𝗟𝗨𝗡𝗗 𝗞𝗔𝗔𝗟𝗔",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗟𝗘𝗧𝗜 𝗠𝗘𝗥𝗜 𝗟𝗨𝗡𝗗 𝗕𝗔𝗗𝗘 𝗠𝗔𝗦𝗧𝗜 𝗦𝗘 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗢 𝗠𝗘𝗡𝗘 𝗖𝗛𝗢𝗗 𝗗𝗔𝗟𝗔 𝗕𝗢𝗛𝗢𝗧 𝗦𝗔𝗦𝗧𝗘 𝗦𝗘",
    "𝗕𝗘𝗧𝗘 𝗧𝗨 𝗕𝗔𝗔𝗣 𝗦𝗘 𝗟𝗘𝗚𝗔 𝗣𝗔𝗡𝗚𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔 𝗞𝗢 𝗖𝗛𝗢𝗗 𝗗𝗨𝗡𝗚𝗔 𝗞𝗔𝗥𝗞𝗘 𝗡𝗔𝗡𝗚𝗔 💦💋",
    "𝗛𝗔𝗛𝗔𝗛𝗔𝗛 𝗠𝗘𝗥𝗘 𝗕𝗘𝗧𝗘 𝗔𝗚𝗟𝗜 𝗕𝗔𝗔𝗥 𝗔𝗣𝗡𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗟𝗘𝗞𝗘 𝗔𝗔𝗬𝗔 𝗠𝗔𝗧𝗛 𝗞𝗔𝗧 𝗢𝗥 𝗠𝗘𝗥𝗘 𝗠𝗢𝗧𝗘 𝗟𝗨𝗡𝗗 𝗦𝗘 𝗖𝗛𝗨𝗗𝗪𝗔𝗬𝗔 𝗠𝗔𝗧𝗛 𝗞𝗔𝗥",
    "𝗖𝗛𝗔𝗟 𝗕𝗘𝗧𝗔 𝗧𝗨𝗝𝗛𝗘 𝗠𝗔́𝗔̀𝗙 𝗞𝗜𝗔 🤣 𝗔𝗕𝗕 𝗔𝗣𝗡𝗜 𝗚𝗙 𝗞𝗢 𝗕𝗛𝗘𝗝",
    "𝗦𝗛𝗔𝗥𝗔𝗠 𝗞𝗔𝗥 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 𝗞𝗜𝗧𝗡𝗔 𝗚𝗔𝗔𝗟𝗜𝗔 𝗦𝗨𝗡𝗪𝗔𝗬𝗘𝗚𝗔 𝗔𝗣𝗡𝗜 𝗠𝗔́𝗔̀𝗔 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗘 𝗨𝗣𝗘𝗥",
    "𝗔𝗕𝗘 𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗕𝗔𝗖𝗛𝗛𝗘 𝗔𝗨𝗞𝗔𝗧 𝗡𝗛𝗜 𝗛𝗘𝗧𝗢 𝗔𝗣𝗡𝗜 𝗥Æ𝗡𝗗𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗟𝗘𝗞𝗘 𝗔𝗔𝗬𝗔 𝗠𝗔𝗧𝗛 𝗞𝗔𝗥 𝗛𝗔𝗛𝗔𝗛𝗔𝗛𝗔",
    "𝗞𝗜𝗗𝗭 𝗠𝗔̂𝗔̂𝗗𝗔𝗥𝗖𝗛Ø𝗗 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗖𝗛𝗢𝗗 𝗖𝗛𝗢𝗗𝗞𝗘 𝗧𝗘𝗥𝗥 𝗟𝗜𝗬𝗘 𝗕𝗛𝗔𝗜 𝗗𝗘𝗗𝗜𝗬𝗔",
    "𝗝𝗨𝗡𝗚𝗟𝗘 𝗠𝗘 𝗡𝗔𝗖𝗛𝗧𝗔 𝗛𝗘 𝗠𝗢𝗥𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗗𝗔𝗜 𝗗𝗘𝗞𝗞𝗘 𝗦𝗔𝗕 𝗕𝗢𝗟𝗧𝗘 𝗢𝗡𝗖𝗘 𝗠𝗢𝗥𝗘 𝗢𝗡𝗖𝗘 𝗠𝗢𝗥𝗘 🤣🤣💦💋",
    "𝗚𝗔𝗟𝗜 𝗚𝗔𝗟𝗜 𝗠𝗘 𝗥𝗘𝗛𝗧𝗔 𝗛𝗘 𝗦𝗔𝗡𝗗 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗖𝗛𝗢𝗗 𝗗𝗔𝗟𝗔 𝗢𝗥 𝗕𝗔𝗡𝗔 𝗗𝗜𝗔 𝗥𝗔𝗡𝗗 🤤🤣",
    "𝗦𝗔𝗕 𝗕𝗢𝗟𝗧𝗘 𝗠𝗨𝗝𝗛𝗞𝗢 𝗣𝗔𝗣𝗔 𝗞𝗬𝗢𝗨𝗡𝗞𝗜 𝗠𝗘𝗡𝗘 𝗕𝗔𝗡𝗔𝗗𝗜𝗔 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗣𝗥𝗘𝗚𝗡𝗘𝗡𝗧 🤣🤣",
    "𝗦𝗨𝗔𝗥 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗠𝗘 𝗦𝗨𝗔𝗥 𝗞𝗔 𝗟𝗢𝗨𝗗𝗔 𝗢𝗥 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗠𝗘 𝗠𝗘𝗥𝗔 𝗟𝗢𝗗𝗔",
    "𝗖𝗛𝗔𝗟 𝗖𝗛𝗔𝗟 𝗔𝗣𝗡𝗜 𝗠𝗔́𝗔̀𝗞𝗜 𝗖𝗛𝗨𝗖𝗛𝗜𝗬𝗔 𝗗𝗜𝗞𝗔",
    "𝗛𝗔𝗛𝗔𝗛𝗔𝗛𝗔 𝗕𝗔𝗖𝗛𝗛𝗘 𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗔𝗞𝗢 𝗖𝗛𝗢𝗗 𝗗𝗜𝗔 𝗡𝗔𝗡𝗚𝗔 𝗞𝗔𝗥𝗞𝗘",
    "𝗧𝗘𝗥𝗜 𝗚𝗙 𝗛𝗘 𝗕𝗔𝗗𝗜 𝗦𝗘𝗫𝗬 𝗨𝗦𝗞𝗢 𝗣𝗜𝗟𝗔𝗞𝗘 𝗖𝗛𝗢𝗢𝗗𝗘𝗡𝗚𝗘 𝗣𝗘𝗣𝗦𝗜",
    "2 𝗥𝗨𝗣𝗔𝗬 𝗞𝗜 𝗣𝗘𝗣𝗦𝗜 𝗧𝗘𝗥𝗜 𝗠𝗨𝗠𝗠𝗬 𝗦𝗔𝗕𝗦𝗘 𝗦𝗘𝗫𝗬 💋💦",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗖𝗛𝗘𝗘𝗠𝗦 𝗦𝗘 𝗖𝗛𝗨𝗗𝗪𝗔𝗩𝗨𝗡𝗚𝗔 𝗠𝗔𝗗𝗘𝗥𝗖𝗛𝗢𝗢𝗗 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 💦🤣",
    "𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗜 𝗖𝗛𝗨𝗨́𝗧𝗛 𝗠𝗘 𝗠𝗨𝗧𝗛𝗞𝗘 𝗙𝗔𝗥𝗔𝗥 𝗛𝗢𝗝𝗔𝗩𝗨𝗡𝗚𝗔 𝗛𝗨𝗜 𝗛𝗨𝗜 𝗛𝗨𝗜",
    "𝗦𝗣𝗘𝗘𝗗 𝗟𝗔𝗔𝗔 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗖𝗛𝗢𝗗𝗨 𝗥Æ𝗡𝗗𝗜𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 💋💦🤣",
    "𝗔𝗥𝗘 𝗥𝗘 𝗠𝗘𝗥𝗘 𝗕𝗘𝗧𝗘 𝗞𝗬𝗢𝗨𝗡 𝗦𝗣𝗘𝗘𝗗 𝗣𝗔𝗞𝗔𝗗 𝗡𝗔 𝗣𝗔𝗔𝗔 𝗥𝗔𝗛𝗔 𝗔𝗣𝗡𝗘 𝗕𝗔𝗔𝗣 𝗞𝗔 𝗛𝗔𝗛𝗔𝗛🤣🤣",
    "𝗦𝗨𝗡 𝗦𝗨𝗡 𝗦𝗨𝗔𝗥 𝗞𝗘 𝗣𝗜𝗟𝗟𝗘 𝗝𝗛𝗔𝗡𝗧𝗢 𝗞𝗘 𝗦𝗢𝗨𝗗𝗔𝗚𝗔𝗥 𝗔𝗣𝗡𝗜 𝗠𝗨𝗠𝗠𝗬 𝗞𝗜 𝗡𝗨𝗗𝗘𝗦 𝗕𝗛𝗘𝗝",
    "𝗔𝗕𝗘 𝗦𝗨𝗡 𝗟𝗢𝗗𝗘 𝗧𝗘𝗥𝗜 𝗕𝗘́𝗛𝗘𝗡 𝗞𝗔 𝗕𝗛𝗢𝗦𝗗𝗔 𝗙𝗔𝗔𝗗 𝗗𝗨𝗡𝗚𝗔",
    "𝗧𝗘𝗥𝗜 𝗠𝗔́𝗔̀𝗞𝗢 𝗞𝗛𝗨𝗟𝗘 𝗕𝗔𝗝𝗔𝗥 𝗠𝗘 𝗖𝗛𝗢𝗗 𝗗𝗔𝗟𝗔 🤣🤣💋",
    "𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐆𝐇𝐔𝐓𝐊𝐀 𝐊𝐇𝐀𝐀𝐊𝐄 𝐓𝐇𝐎𝐎𝐊 𝐃𝐔𝐍𝐆𝐀 🤣🤣",
    "𝐓𝐄𝐑𝐄 𝐁𝐄𝐇𝐄𝐍 𝐊 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐂𝐇𝐀𝐊𝐔 𝐃𝐀𝐀𝐋 𝐊𝐀𝐑 𝐂𝐇𝐔𝐓 𝐊𝐀 𝐊𝐇𝐎𝐎𝐍 𝐊𝐀𝐑 𝐃𝐔𝐆𝐀", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐍𝐇𝐈 𝐇𝐀𝐈 𝐊𝐘𝐀? 𝟗 𝐌𝐀𝐇𝐈𝐍𝐄 𝐑𝐔𝐊 𝐒𝐀𝐆𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐃𝐄𝐓𝐀 𝐇𝐔 🤣🤣🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄 𝐀𝐄𝐑𝐎𝐏𝐋𝐀𝐍𝐄𝐏𝐀𝐑𝐊 𝐊𝐀𝐑𝐊𝐄 𝐔𝐃𝐀𝐀𝐍 𝐁𝐇𝐀𝐑 𝐃𝐔𝐆𝐀 ✈️🛫", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐒𝐔𝐓𝐋𝐈 𝐁𝐎𝐌𝐁 𝐅𝐎𝐃 𝐃𝐔𝐍𝐆𝐀 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐉𝐇𝐀𝐀𝐓𝐄 𝐉𝐀𝐋 𝐊𝐄 𝐊𝐇𝐀𝐀𝐊 𝐇𝐎 𝐉𝐀𝐘𝐄𝐆𝐈💣", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐒𝐂𝐎𝐎𝐓𝐄𝐑 𝐃𝐀𝐀𝐋 𝐃𝐔𝐆𝐀👅", 
    "𝐓𝐄𝐑𝐄 𝐁𝐄𝐇𝐄𝐍 𝐊 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐂𝐇𝐀𝐊𝐔 𝐃𝐀𝐀𝐋 𝐊𝐀𝐑 𝐂𝐇𝐔𝐓 𝐊𝐀 𝐊𝐇𝐎𝐎𝐍 𝐊𝐀𝐑 𝐃𝐔𝐆𝐀", 
    "𝐓𝐄𝐑𝐄 𝐁𝐄𝐇𝐄𝐍 𝐊 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐂𝐇𝐀𝐊𝐔 𝐃𝐀𝐀𝐋 𝐊𝐀𝐑 𝐂𝐇𝐔𝐓 𝐊𝐀 𝐊𝐇𝐎𝐎𝐍 𝐊𝐀𝐑 𝐃𝐔𝐆𝐀", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐊𝐀𝐊𝐓𝐄 🤱 𝐆𝐀𝐋𝐈 𝐊𝐄 𝐊𝐔𝐓𝐓𝐎 🦮 𝐌𝐄 𝐁𝐀𝐀𝐓 𝐃𝐔𝐍𝐆𝐀 𝐏𝐇𝐈𝐑 🍞 𝐁𝐑𝐄𝐀𝐃 𝐊𝐈 𝐓𝐀𝐑𝐇 𝐊𝐇𝐀𝐘𝐄𝐍𝐆𝐄 𝐖𝐎 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓", 
    "𝐃𝐔𝐃𝐇 𝐇𝐈𝐋𝐀𝐀𝐔𝐍𝐆𝐀 𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐊𝐄 𝐔𝐏𝐑 𝐍𝐈𝐂𝐇𝐄 🆙🆒😙", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 ✋ 𝐇𝐀𝐓𝐓𝐇 𝐃𝐀𝐋𝐊𝐄 👶 𝐁𝐀𝐂𝐂𝐇𝐄 𝐍𝐈𝐊𝐀𝐋 𝐃𝐔𝐍𝐆𝐀 😍", 
    "𝐓𝐄𝐑𝐈 𝐁𝐄𝐇𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐊𝐄𝐋𝐄 𝐊𝐄 𝐂𝐇𝐈𝐋𝐊𝐄 🍌🍌😍", 
    "𝐓𝐄𝐑𝐈 𝐁𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐔𝐒𝐄𝐑𝐁𝐎𝐓 𝐋𝐀𝐆𝐀𝐀𝐔𝐍𝐆𝐀 𝐒𝐀𝐒𝐓𝐄 𝐒𝐏𝐀𝐌 𝐊𝐄 𝐂𝐇𝐎𝐃𝐄", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐃𝐇𝐀𝐍𝐃𝐇𝐄 𝐕𝐀𝐀𝐋𝐈 😋😛", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄 𝐀𝐂 𝐋𝐀𝐆𝐀 𝐃𝐔𝐍𝐆𝐀 𝐒𝐀𝐀𝐑𝐈 𝐆𝐀𝐑𝐌𝐈 𝐍𝐈𝐊𝐀𝐋 𝐉𝐀𝐀𝐘𝐄𝐆𝐈", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐊𝐎 𝐇𝐎𝐑𝐋𝐈𝐂𝐊𝐒 𝐏𝐄𝐄𝐋𝐀𝐔𝐍𝐆𝐀 𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃😚", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐆𝐀𝐀𝐍𝐃 𝐌𝐄 𝐒𝐀𝐑𝐈𝐘𝐀 𝐃𝐀𝐀𝐋 𝐃𝐔𝐍𝐆𝐀 𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃 𝐔𝐒𝐈 𝐒𝐀𝐑𝐈𝐘𝐄 𝐏𝐑 𝐓𝐀𝐍𝐆 𝐊𝐄 𝐁𝐀𝐂𝐇𝐄 𝐏𝐀𝐈𝐃𝐀 𝐇𝐎𝐍𝐆𝐄 😱😱", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐎 𝐊𝐎𝐋𝐊𝐀𝐓𝐀 𝐕𝐀𝐀𝐋𝐄 𝐉𝐈𝐓𝐔 𝐁𝐇𝐀𝐈𝐘𝐀 𝐊𝐀 𝐋𝐔𝐍𝐃 𝐌𝐔𝐁𝐀𝐑𝐀𝐊 🤩🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐔𝐌𝐌𝐘 𝐊𝐈 𝐅𝐀𝐍𝐓𝐀𝐒𝐘 𝐇𝐔 𝐋𝐀𝐖𝐃𝐄, 𝐓𝐔 𝐀𝐏𝐍𝐈 𝐁𝐇𝐄𝐍 𝐊𝐎 𝐒𝐌𝐁𝐇𝐀𝐀𝐋 😈😈", 
    "𝐓𝐄𝐑𝐀 𝐏𝐄𝐇𝐋𝐀 𝐁𝐀𝐀𝐏 𝐇𝐔 𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃 ", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄 𝐗𝐕𝐈𝐃𝐄𝐎𝐒.𝐂𝐎𝐌 𝐂𝐇𝐀𝐋𝐀 𝐊𝐄 𝐌𝐔𝐓𝐇 𝐌𝐀𝐀𝐑𝐔𝐍𝐆𝐀 🤡😹", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐀 𝐆𝐑𝐎𝐔𝐏 𝐕𝐀𝐀𝐋𝐎𝐍 𝐒𝐀𝐀𝐓𝐇 𝐌𝐈𝐋𝐊𝐄 𝐆𝐀𝐍𝐆 𝐁𝐀𝐍𝐆 𝐊𝐑𝐔𝐍𝐆𝐀🙌🏻☠️ ", 
    "𝐓𝐄𝐑𝐈 𝐈𝐓𝐄𝐌 𝐊𝐈 𝐆𝐀𝐀𝐍𝐃 𝐌𝐄 𝐋𝐔𝐍𝐃 𝐃𝐀𝐀𝐋𝐊𝐄,𝐓𝐄𝐑𝐄 𝐉𝐀𝐈𝐒𝐀 𝐄𝐊 𝐎𝐑 𝐍𝐈𝐊𝐀𝐀𝐋 𝐃𝐔𝐍𝐆𝐀 𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃🤘🏻🙌🏻☠️ ", 
    "𝐀𝐔𝐊𝐀𝐀𝐓 𝐌𝐄 𝐑𝐄𝐇 𝐕𝐑𝐍𝐀 𝐆𝐀𝐀𝐍𝐃 𝐌𝐄 𝐃𝐀𝐍𝐃𝐀 𝐃𝐀𝐀𝐋 𝐊𝐄 𝐌𝐔𝐇 𝐒𝐄 𝐍𝐈𝐊𝐀𝐀𝐋 𝐃𝐔𝐍𝐆𝐀 𝐒𝐇𝐀𝐑𝐈𝐑 𝐁𝐇𝐈 𝐃𝐀𝐍𝐃𝐄 𝐉𝐄𝐒𝐀 𝐃𝐈𝐊𝐇𝐄𝐆𝐀 🙄🤭🤭", 
    "𝐓𝐄𝐑𝐈 𝐌𝐔𝐌𝐌𝐘 𝐊𝐄 𝐒𝐀𝐀𝐓𝐇 𝐋𝐔𝐃𝐎 𝐊𝐇𝐄𝐋𝐓𝐄 𝐊𝐇𝐄𝐋𝐓𝐄 𝐔𝐒𝐊𝐄 𝐌𝐔𝐇 𝐌𝐄 𝐀𝐏𝐍𝐀 𝐋𝐎𝐃𝐀 𝐃𝐄 𝐃𝐔𝐍𝐆𝐀☝🏻☝🏻😬", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐄𝐍 𝐊𝐎 𝐀𝐏𝐍𝐄 𝐋𝐔𝐍𝐃 𝐏𝐑 𝐈𝐓𝐍𝐀 𝐉𝐇𝐔𝐋𝐀𝐀𝐔𝐍𝐆𝐀 𝐊𝐈 𝐉𝐇𝐔𝐋𝐓𝐄 𝐉𝐇𝐔𝐋𝐓𝐄 𝐇𝐈 𝐁𝐀𝐂𝐇𝐀 𝐏𝐀𝐈𝐃𝐀 𝐊𝐑 𝐃𝐄𝐆𝐈👀👯 ", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐁𝐀𝐓𝐓𝐄𝐑𝐘 𝐋𝐀𝐆𝐀 𝐊𝐄 𝐏𝐎𝐖𝐄𝐑𝐁𝐀𝐍𝐊 𝐁𝐀𝐍𝐀 𝐃𝐔𝐍𝐆𝐀 🔋 🔥🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐂++ 𝐒𝐓𝐑𝐈𝐍𝐆 𝐄𝐍𝐂𝐑𝐘𝐏𝐓𝐈𝐎𝐍 𝐋𝐀𝐆𝐀 𝐃𝐔𝐍𝐆𝐀 𝐁𝐀𝐇𝐓𝐈 𝐇𝐔𝐘𝐈 𝐂𝐇𝐔𝐓 𝐑𝐔𝐊 𝐉𝐀𝐘𝐄𝐆𝐈𝐈𝐈𝐈😈🔥😍", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐆𝐀𝐀𝐍𝐃 𝐌𝐄𝐈 𝐉𝐇𝐀𝐀𝐃𝐔 𝐃𝐀𝐋 𝐊𝐄 𝐌𝐎𝐑 🦚 𝐁𝐀𝐍𝐀 𝐃𝐔𝐍𝐆𝐀𝐀 🤩🥵😱", 
    "𝐓𝐄𝐑𝐈 𝐂𝐇𝐔𝐓 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐒𝐇𝐎𝐔𝐋𝐃𝐄𝐑𝐈𝐍𝐆 𝐊𝐀𝐑 𝐃𝐔𝐍𝐆𝐀𝐀 𝐇𝐈𝐋𝐀𝐓𝐄 𝐇𝐔𝐘𝐄 𝐁𝐇𝐈 𝐃𝐀𝐑𝐃 𝐇𝐎𝐆𝐀𝐀𝐀😱🤮👺", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐎 𝐑𝐄𝐃𝐈 𝐏𝐄 𝐁𝐀𝐈𝐓𝐇𝐀𝐋 𝐊𝐄 𝐔𝐒𝐒𝐄 𝐔𝐒𝐊𝐈 𝐂𝐇𝐔𝐓 𝐁𝐈𝐋𝐖𝐀𝐔𝐍𝐆𝐀𝐀 💰 😵🤩", 
    "𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝟒 𝐇𝐎𝐋𝐄 𝐇𝐀𝐈 𝐔𝐍𝐌𝐄 𝐌𝐒𝐄𝐀𝐋 𝐋𝐀𝐆𝐀 𝐁𝐀𝐇𝐔𝐓 𝐁𝐀𝐇𝐄𝐓𝐈 𝐇𝐀𝐈 𝐁𝐇𝐎𝐅𝐃𝐈𝐊𝐄👊🤮🤢🤢", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐁𝐀𝐑𝐆𝐀𝐃 𝐊𝐀 𝐏𝐄𝐃 𝐔𝐆𝐀 𝐃𝐔𝐍𝐆𝐀𝐀 𝐂𝐎𝐑𝐎𝐍𝐀 𝐌𝐄𝐈 𝐒𝐀𝐁 𝐎𝐗𝐘𝐆𝐄𝐍 𝐋𝐄𝐊𝐀𝐑 𝐉𝐀𝐘𝐄𝐍𝐆𝐄🤢🤩🥳", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐒𝐔𝐃𝐎 𝐋𝐀𝐆𝐀 𝐊𝐄 𝐁𝐈𝐆𝐒𝐏𝐀𝐌 𝐋𝐀𝐆𝐀 𝐊𝐄 𝟗𝟗𝟗𝟗 𝐅𝐔𝐂𝐊 𝐋𝐀𝐆𝐀𝐀 𝐃𝐔 🤩🥳🔥", 
    "𝐓𝐄𝐑𝐈 𝐕𝐀𝐇𝐄𝐍 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄 𝐌𝐄𝐈 𝐁𝐄𝐒𝐀𝐍 𝐊𝐄 𝐋𝐀𝐃𝐃𝐔 𝐁𝐇𝐀𝐑 𝐃𝐔𝐍𝐆𝐀🤩🥳🔥😈", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐊𝐇𝐎𝐃 𝐊𝐄 𝐔𝐒𝐌𝐄 𝐂𝐘𝐋𝐈𝐍𝐃𝐄𝐑 ⛽️ 𝐅𝐈𝐓 𝐊𝐀𝐑𝐊𝐄 𝐔𝐒𝐌𝐄𝐄 𝐃𝐀𝐋 𝐌𝐀𝐊𝐇𝐀𝐍𝐈 𝐁𝐀𝐍𝐀𝐔𝐍𝐆𝐀𝐀𝐀🤩👊🔥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐒𝐇𝐄𝐄𝐒𝐇𝐀 𝐃𝐀𝐋 𝐃𝐔𝐍𝐆𝐀𝐀𝐀 𝐀𝐔𝐑 𝐂𝐇𝐀𝐔𝐑𝐀𝐇𝐄 𝐏𝐄 𝐓𝐀𝐀𝐍𝐆 𝐃𝐔𝐍𝐆𝐀 𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄😈😱🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐂𝐑𝐄𝐃𝐈𝐓 𝐂𝐀𝐑𝐃 𝐃𝐀𝐋 𝐊𝐄 𝐀𝐆𝐄 𝐒𝐄 𝟓𝟎𝟎 𝐊𝐄 𝐊𝐀𝐀𝐑𝐄 𝐊𝐀𝐀𝐑𝐄 𝐍𝐎𝐓𝐄 𝐍𝐈𝐊𝐀𝐋𝐔𝐍𝐆𝐀𝐀 𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄💰💰🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐒𝐀𝐓𝐇 𝐒𝐔𝐀𝐑 𝐊𝐀 𝐒𝐄𝐗 𝐊𝐀𝐑𝐖𝐀 𝐃𝐔𝐍𝐆𝐀𝐀 𝐄𝐊 𝐒𝐀𝐓𝐇 𝟔-𝟔 𝐁𝐀𝐂𝐇𝐄 𝐃𝐄𝐆𝐈💰🔥😱", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐀𝐏𝐏𝐋𝐄 𝐊𝐀 𝟏𝟖𝐖 𝐖𝐀𝐋𝐀 𝐂𝐇𝐀𝐑𝐆𝐄𝐑 🔥🤩", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐆𝐀𝐀𝐍𝐃 𝐌𝐄𝐈 𝐎𝐍𝐄𝐏𝐋𝐔𝐒 𝐊𝐀 𝐖𝐑𝐀𝐏 𝐂𝐇𝐀𝐑𝐆𝐄𝐑 𝟑𝟎𝐖 𝐇𝐈𝐆𝐇 𝐏𝐎𝐖𝐄𝐑 💥😂😎", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐊𝐎 𝐀𝐌𝐀𝐙𝐎𝐍 𝐒𝐄 𝐎𝐑𝐃𝐄𝐑 𝐊𝐀𝐑𝐔𝐍𝐆𝐀 𝟏𝟎 𝐫𝐬 𝐌𝐄𝐈 𝐀𝐔𝐑 𝐅𝐋𝐈𝐏𝐊𝐀𝐑𝐓 𝐏𝐄 𝟐𝟎 𝐑𝐒 𝐌𝐄𝐈 𝐁𝐄𝐂𝐇 𝐃𝐔𝐍𝐆𝐀🤮👿😈🤖", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐁𝐀𝐃𝐈 𝐁𝐇𝐔𝐍𝐃 𝐌𝐄 𝐙𝐎𝐌𝐀𝐓𝐎 𝐃𝐀𝐋 𝐊𝐄 𝐒𝐔𝐁𝐖𝐀𝐘 𝐊𝐀 𝐁𝐅𝐅 𝐕𝐄𝐆 𝐒𝐔𝐁 𝐂𝐎𝐌𝐁𝐎 [𝟏𝟓𝐜𝐦 , 𝟏𝟔 𝐢𝐧𝐜𝐡𝐞𝐬 ] 𝐎𝐑𝐃𝐄𝐑 𝐂𝐎𝐃 𝐊𝐑𝐕𝐀𝐔𝐍𝐆𝐀 𝐎𝐑 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐉𝐀𝐁 𝐃𝐈𝐋𝐈𝐕𝐄𝐑𝐘 𝐃𝐄𝐍𝐄 𝐀𝐘𝐄𝐆𝐈 𝐓𝐀𝐁 𝐔𝐒𝐏𝐄 𝐉𝐀𝐀𝐃𝐔 𝐊𝐑𝐔𝐍𝐆𝐀 𝐎𝐑 𝐅𝐈𝐑 𝟗 𝐌𝐎𝐍𝐓𝐇 𝐁𝐀𝐀𝐃 𝐕𝐎 𝐄𝐊 𝐎𝐑 𝐅𝐑𝐄𝐄 𝐃𝐈𝐋𝐈𝐕𝐄𝐑𝐘 𝐃𝐄𝐆𝐈🙀👍🥳🔥", 
    "𝐓𝐄𝐑𝐈 𝐁𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐊𝐀𝐀𝐋𝐈🙁🤣💥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄 𝐂𝐇𝐀𝐍𝐆𝐄𝐒 𝐂𝐎𝐌𝐌𝐈𝐓 𝐊𝐑𝐔𝐆𝐀 𝐅𝐈𝐑 𝐓𝐄𝐑𝐈 𝐁𝐇𝐄𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐀𝐔𝐓𝐎𝐌𝐀𝐓𝐈𝐂𝐀𝐋𝐋𝐘 𝐔𝐏𝐃𝐀𝐓𝐄 𝐇𝐎𝐉𝐀𝐀𝐘𝐄𝐆𝐈🤖🙏🤔", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐔𝐒𝐈 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄𝐈 𝐈𝐍𝐃𝐈𝐀𝐍 𝐑𝐀𝐈𝐋𝐖𝐀𝐘 🚂💥😂", 
    "𝐓𝐔 𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐓𝐄𝐑𝐀 𝐊𝐇𝐀𝐍𝐃𝐀𝐍 𝐒𝐀𝐁 𝐁𝐀𝐇𝐄𝐍 𝐊𝐄 𝐋𝐀𝐖𝐃𝐄 𝐑𝐀𝐍𝐃𝐈 𝐇𝐀𝐈 𝐑𝐀𝐍𝐃𝐈 🤢✅🔥", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐈𝐎𝐍𝐈𝐂 𝐁𝐎𝐍𝐃 𝐁𝐀𝐍𝐀 𝐊𝐄 𝐕𝐈𝐑𝐆𝐈𝐍𝐈𝐓𝐘 𝐋𝐎𝐎𝐒𝐄 𝐊𝐀𝐑𝐖𝐀 𝐃𝐔𝐍𝐆𝐀 𝐔𝐒𝐊𝐈 📚 😎🤩", 
    "𝐓𝐄𝐑𝐈 𝐑𝐀𝐍𝐃𝐈 𝐌𝐀𝐀 𝐒𝐄 𝐏𝐔𝐂𝐇𝐍𝐀 𝐁𝐀𝐀𝐏 𝐊𝐀 𝐍𝐀𝐀𝐌 𝐁𝐀𝐇𝐄𝐍 𝐊𝐄 𝐋𝐎𝐃𝐄𝐄𝐄𝐄𝐄 🤩🥳😳", 
    "𝐓𝐔 𝐀𝐔𝐑 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐃𝐎𝐍𝐎 𝐊𝐈 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄𝐈 𝐌𝐄𝐓𝐑𝐎 𝐂𝐇𝐀𝐋𝐖𝐀 𝐃𝐔𝐍𝐆𝐀 𝐌𝐀𝐃𝐀𝐑𝐗𝐇𝐎𝐃 🚇🤩😱🥶", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐎 𝐈𝐓𝐍𝐀 𝐂𝐇𝐎𝐃𝐔𝐍𝐆𝐀 𝐓𝐄𝐑𝐀 𝐁𝐀𝐀𝐏 𝐁𝐇𝐈 𝐔𝐒𝐊𝐎 𝐏𝐀𝐇𝐂𝐇𝐀𝐍𝐀𝐍𝐄 𝐒𝐄 𝐌𝐀𝐍𝐀 𝐊𝐀𝐑 𝐃𝐄𝐆𝐀😂👿🤩", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄𝐈 𝐇𝐀𝐈𝐑 𝐃𝐑𝐘𝐄𝐑 𝐂𝐇𝐀𝐋𝐀 𝐃𝐔𝐍𝐆𝐀𝐀💥🔥🔥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐓𝐄𝐋𝐄𝐆𝐑𝐀𝐌 𝐊𝐈 𝐒𝐀𝐑𝐈 𝐑𝐀𝐍𝐃𝐈𝐘𝐎𝐍 𝐊𝐀 𝐑𝐀𝐍𝐃𝐈 𝐊𝐇𝐀𝐍𝐀 𝐊𝐇𝐎𝐋 𝐃𝐔𝐍𝐆𝐀𝐀👿🤮😎", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐀𝐋𝐄𝐗𝐀 𝐃𝐀𝐋 𝐊𝐄𝐄 𝐃𝐉 𝐁𝐀𝐉𝐀𝐔𝐍𝐆𝐀𝐀𝐀 🎶 ⬆️🤩💥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄𝐈 𝐆𝐈𝐓𝐇𝐔𝐁 𝐃𝐀𝐋 𝐊𝐄 𝐀𝐏𝐍𝐀 𝐁𝐎𝐓 𝐇𝐎𝐒𝐓 𝐊𝐀𝐑𝐔𝐍𝐆𝐀𝐀 🤩👊👤😍", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐀 𝐕𝐏𝐒 𝐁𝐀𝐍𝐀 𝐊𝐄 𝟐𝟒*𝟕 𝐁𝐀𝐒𝐇 𝐂𝐇𝐔𝐃𝐀𝐈 𝐂𝐎𝐌𝐌𝐀𝐍𝐃 𝐃𝐄 𝐃𝐔𝐍𝐆𝐀𝐀 🤩💥🔥🔥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐔𝐌𝐌𝐘 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐓𝐄𝐑𝐄 𝐋𝐀𝐍𝐃 𝐊𝐎 𝐃𝐀𝐋 𝐊𝐄 𝐊𝐀𝐀𝐓 𝐃𝐔𝐍𝐆𝐀 𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃 🔪😂🔥", 
    "𝐒𝐔𝐍 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐀 𝐁𝐇𝐎𝐒𝐃𝐀 𝐀𝐔𝐑 𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐀 𝐁𝐇𝐈 𝐁𝐇𝐎𝐒𝐃𝐀 👿😎👊", 
    "𝐓𝐔𝐉𝐇𝐄 𝐃𝐄𝐊𝐇 𝐊𝐄 𝐓𝐄𝐑𝐈 𝐑Æ𝐍𝐃𝐈 𝐁𝐀𝐇𝐄𝐍 𝐏𝐄 𝐓𝐀𝐑𝐀𝐒 𝐀𝐓𝐀 𝐇𝐀𝐈 𝐌𝐔𝐉𝐇𝐄 𝐁𝐀𝐇𝐄𝐍 𝐊𝐄 𝐋𝐎𝐃𝐄𝐄𝐄𝐄 👿💥🤩🔥", 
    "𝐒𝐔𝐍 𝐌𝐀𝐃𝐀𝐑𝐂𝐇Ø𝐃 𝐉𝐘𝐀𝐃𝐀 𝐍𝐀 𝐔𝐂𝐇𝐀𝐋 𝐌𝐀𝐀 𝐂𝐇𝐎𝐃 𝐃𝐄𝐍𝐆𝐄 𝐄𝐊 𝐌𝐈𝐍 𝐌𝐄𝐈 ✅🤣🔥🤩", 
    "𝐀𝐏𝐍𝐈 𝐀𝐌𝐌𝐀 𝐒𝐄 𝐏𝐔𝐂𝐇𝐍𝐀 𝐔𝐒𝐊𝐎 𝐔𝐒 𝐊𝐀𝐀𝐋𝐈 𝐑𝐀𝐀𝐓 𝐌𝐄𝐈 𝐊𝐀𝐔𝐍 𝐂𝐇𝐎𝐃𝐍𝐄𝐄 𝐀𝐘𝐀 𝐓𝐇𝐀𝐀𝐀! 𝐓𝐄𝐑𝐄 𝐈𝐒 𝐏𝐀𝐏𝐀 𝐊𝐀 𝐍𝐀𝐀𝐌 𝐋𝐄𝐆𝐈 😂👿😳", 
    "𝐓𝐎𝐇𝐀𝐑 𝐁𝐀𝐇𝐈𝐍 𝐂𝐇𝐎𝐃𝐔 𝐁𝐁𝐀𝐇𝐄𝐍 𝐊𝐄 𝐋𝐀𝐖𝐃𝐄 𝐔𝐒𝐌𝐄 𝐌𝐈𝐓𝐓𝐈 𝐃𝐀𝐋 𝐊𝐄 𝐂𝐄𝐌𝐄𝐍𝐓 𝐒𝐄 𝐁𝐇𝐀𝐑 𝐃𝐔 🏠🤢🤩💥", 
    "𝐓𝐔𝐉𝐇𝐄 𝐀𝐁 𝐓𝐀𝐊 𝐍𝐀𝐇𝐈 𝐒𝐌𝐉𝐇 𝐀𝐘𝐀 𝐊𝐈 𝐌𝐀𝐈 𝐇𝐈 𝐇𝐔 𝐓𝐔𝐉𝐇𝐄 𝐏𝐀𝐈𝐃𝐀 𝐊𝐀𝐑𝐍𝐄 𝐖𝐀𝐋𝐀 𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄𝐄 𝐀𝐏𝐍𝐈 𝐌𝐀𝐀 𝐒𝐄 𝐏𝐔𝐂𝐇 𝐑Æ𝐍𝐃𝐈 𝐊𝐄 𝐁𝐀𝐂𝐇𝐄𝐄𝐄𝐄 🤩👊👤😍", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐄 𝐌𝐄𝐈 𝐒𝐏𝐎𝐓𝐈𝐅𝐘 𝐃𝐀𝐋 𝐊𝐄 𝐋𝐎𝐅𝐈 𝐁𝐀𝐉𝐀𝐔𝐍𝐆𝐀 𝐃𝐈𝐍 𝐁𝐇𝐀𝐑 😍🎶🎶💥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐀 𝐍𝐀𝐘𝐀 𝐑Æ𝐍𝐃𝐈 𝐊𝐇𝐀𝐍𝐀 𝐊𝐇𝐎𝐋𝐔𝐍𝐆𝐀 𝐂𝐇𝐈𝐍𝐓𝐀 𝐌𝐀𝐓 𝐊𝐀𝐑 👊🤣🤣😳", 
    "𝐓𝐄𝐑𝐀 𝐁𝐀𝐀𝐏 𝐇𝐔 𝐁𝐇𝐎𝐒𝐃𝐈𝐊𝐄 𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐎 𝐑Æ𝐍𝐃𝐈 𝐊𝐇𝐀𝐍𝐄 𝐏𝐄 𝐂𝐇𝐔𝐃𝐖𝐀 𝐊𝐄 𝐔𝐒 𝐏𝐀𝐈𝐒𝐄 𝐊𝐈 𝐃𝐀𝐀𝐑𝐔 𝐏𝐄𝐄𝐓𝐀 𝐇𝐔 🍷🤩🔥", 
    "𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐌𝐄𝐈 𝐀𝐏𝐍𝐀 𝐁𝐀𝐃𝐀 𝐒𝐀 𝐋𝐎𝐃𝐀 𝐆𝐇𝐔𝐒𝐒𝐀 𝐃𝐔𝐍𝐆𝐀𝐀 𝐊𝐀𝐋𝐋𝐀𝐀𝐏 𝐊𝐄 𝐌𝐀𝐑 𝐉𝐀𝐘𝐄𝐆𝐈 🤩😳😳🔥", 
    "𝐓𝐎𝐇𝐀𝐑 𝐌𝐔𝐌𝐌𝐘 𝐊𝐈 𝐂𝐇𝐔𝐔́𝐓 𝐌𝐄𝐈 𝐏𝐔𝐑𝐈 𝐊𝐈 𝐏𝐔𝐑𝐈 𝐊𝐈𝐍𝐆𝐅𝐈𝐒𝐇𝐄𝐑 𝐊𝐈 𝐁𝐎𝐓𝐓𝐋𝐄 𝐃𝐀𝐋 𝐊𝐄 𝐓𝐎𝐃 𝐃𝐔𝐍𝐆𝐀 𝐀𝐍𝐃𝐄𝐑 𝐇𝐈 😱😂🤩", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐎 𝐈𝐓𝐍𝐀 𝐂𝐇𝐎𝐃𝐔𝐍𝐆𝐀 𝐊𝐈 𝐒𝐀𝐏𝐍𝐄 𝐌𝐄𝐈 𝐁𝐇𝐈 𝐌𝐄𝐑𝐈 𝐂𝐇𝐔𝐃𝐀𝐈 𝐘𝐀𝐀𝐃 𝐊𝐀𝐑𝐄𝐆𝐈 𝐑Æ𝐍𝐃𝐈 🥳😍👊💥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐔𝐌𝐌𝐘 𝐀𝐔𝐑 𝐁𝐀𝐇𝐄𝐍 𝐊𝐎 𝐃𝐀𝐔𝐃𝐀 𝐃𝐀𝐔𝐃𝐀 𝐍𝐄 𝐂𝐇𝐎𝐃𝐔𝐍𝐆𝐀 𝐔𝐍𝐊𝐄 𝐍𝐎 𝐁𝐎𝐋𝐍𝐄 𝐏𝐄 𝐁𝐇𝐈 𝐋𝐀𝐍𝐃 𝐆𝐇𝐔𝐒𝐀 𝐃𝐔𝐍𝐆𝐀 𝐀𝐍𝐃𝐄𝐑 𝐓𝐀𝐊 😎😎🤣🔥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐔𝐌𝐌𝐘 𝐊𝐈 𝐂𝐇𝐔𝐓 𝐊𝐎 𝐎𝐍𝐋𝐈𝐍𝐄 𝐎𝐋𝐗 𝐏𝐄 𝐁𝐄𝐂𝐇𝐔𝐍𝐆𝐀 𝐀𝐔𝐑 𝐏𝐀𝐈𝐒𝐄 𝐒𝐄 𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐀 𝐊𝐎𝐓𝐇𝐀 𝐊𝐇𝐎𝐋 𝐃𝐔𝐍𝐆𝐀 😎🤩😝😍", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐄 𝐁𝐇𝐎𝐒𝐃𝐀 𝐈𝐓𝐍𝐀 𝐂𝐇𝐎𝐃𝐔𝐍𝐆𝐀 𝐊𝐈 𝐓𝐔 𝐂𝐀𝐇 𝐊𝐄 𝐁𝐇𝐈 𝐖𝐎 𝐌𝐀𝐒𝐓 𝐂𝐇𝐔𝐃𝐀𝐈 𝐒𝐄 𝐃𝐔𝐑 𝐍𝐇𝐈 𝐉𝐀 𝐏𝐀𝐘𝐄𝐆𝐀𝐀 😏😏🤩😍", 
    "𝐒𝐔𝐍 𝐁𝐄 𝐑Æ𝐍𝐃𝐈 𝐊𝐈 𝐀𝐔𝐋𝐀𝐀𝐃 𝐓𝐔 𝐀𝐏𝐍𝐈 𝐁𝐀𝐇𝐄𝐍 𝐒𝐄 𝐒𝐄𝐄𝐊𝐇 𝐊𝐔𝐂𝐇 𝐊𝐀𝐈𝐒𝐄 𝐆𝐀𝐀𝐍𝐃 𝐌𝐀𝐑𝐖𝐀𝐓𝐄 𝐇𝐀𝐈😏🤬🔥💥", 
    "𝐓𝐄𝐑𝐈 𝐌𝐀𝐀 𝐊𝐀 𝐘𝐀𝐀𝐑 𝐇𝐔 𝐌𝐄𝐈 𝐀𝐔𝐑 𝐓𝐄𝐑𝐈 𝐁𝐀𝐇𝐄𝐍 𝐊𝐀 𝐏𝐘𝐀𝐀𝐑 𝐇𝐔 𝐌𝐄𝐈 𝐀𝐉𝐀 𝐌𝐄𝐑𝐀 𝐋𝐀𝐍𝐃 𝐂𝐇𝐎𝐎𝐒 𝐋𝐄 🤩🤣💥",
    "𝐌𝐀𝐃𝐀𝐑𝐂𝐇𝐎𝐃",
    "BHOSDIKE",
    "LAAAWEEE KE BAAAAAL",
    "MAAAAR KI JHAAAAT KE BBBBBAAAAALLLLL",
    "MADRCHOD..",
    "TERI MA KI CHUT..",
    "LWDE KE BAAALLL.",
    "MACHAR KI JHAAT KE BAAALLLL",
    "TERI MA KI CHUT M DU TAPA TAP?",
    "TERI MA KA BHOSDAA",
    "TERI BHN SBSBE BDI RANDI.",
    "TERI MA OSSE BADI RANDDDDD",
    "TERA BAAP CHKAAAA",
    "KITNI CHODU TERI MA AB OR..",
    "TERI MA CHOD DI HM NE",
    "TERI MA KE STH REELS BNEGA ROAD PEE",
    "TERI MA KI CHUT EK DAM TOP SEXY",
    "MALUM NA PHR KESE LETA HU M TERI MA KI CHUT TAPA TAPPPPP",
    "LUND KE CHODE TU KEREGA TYPIN",
    "SPEED PKD LWDEEEE",
    "BAAP KI SPEED MTCH KRRR",
    "LWDEEE",
    "PAPA KI SPEED MTCH NHI HO RHI KYA",
    "ALE ALE MELA BCHAAAA",
    "CHUD GYA PAPA SEEE",
    "KISAN KO KHODNA OR",
    "SALE RAPEKL KRDKA TERA",
    "HAHAHAAAAA",
    "KIDSSSS",
    "TERI MA CHUD GYI AB FRAR MT HONA",
    "YE LDNGE BAPP SE",
    "KIDSSS FRAR HAHAHH",
    "BHEN KE LWDE SHRM KR",
    "KITNI GLIYA PDWEGA APNI MA KO",
    "NALLEE",
    "SHRM KR",
    "MERE LUND KE BAAAAALLLLL",
    "KITNI GLIYA PDWYGA APNI MA BHEN KO",
    "RNDI KE LDKEEEEEEEEE",
    "KIDSSSSSSSSSSSS",
    "Apni gaand mein muthi daal",
    "Apni lund choos",
    "Apni ma ko ja choos",
    "Bhen ke laude",
    "Bhen ke takke",
    "Abla TERA KHAN DAN CHODNE KI BARIII",
    "BETE TERI MA SBSE BDI RAND",
    "LUND KE BAAAL JHAT KE PISSSUUUUUUU",
    "LUND PE LTKIT MAAALLLL KI BOND H TUUU",
    "KASH OS DIN MUTH MRKE SOJTA M TUN PAIDA NA HOTAA",
    "GLTI KRDI TUJW PAIDA KRKE",
    "SPEED PKDDD",
    "Gaand main LWDA DAL LE APNI MERAAA",
    "Gaand mein bambu DEDUNGAAAAAA",
    "GAND FTI KE BALKKK",
    "Gote kitne bhi bade ho, lund ke niche hi rehte hai",
    "Hazaar lund teri gaand main",
    "Jhaant ke pissu-",
    "TERI MA KI KALI CHUT",
    "Khotey ki aulda",
    "Kutte ka awlat",
    "Kutte ki jat",
    "Kutte ke tatte",
    "TETI MA KI.CHUT , tERI MA RNDIIIIIIIIIIIIIIIIIIII",
    "Lavde ke bal",
    "muh mei lele",
    "Lund Ke Pasine",
    "MERE LWDE KE BAAAAALLL",
    "HAHAHAAAAAA",
    "CHUD GYAAAAA",
    "Randi khanE KI ULADDD",
    "Sadi hui gaand",
    "Teri gaand main kute ka lund",
    "Teri maa ka bhosda",
    "Teri maa ki chut",
    "Tere gaand mein keede paday",
    "Ullu ke pathe",
    "SUNN MADERCHOD",
    "TERI MAA KA BHOSDA",
    "BEHEN K LUND",
    "TERI MAA KA CHUT KI CHTNIIII",
    "MERA LAWDA LELE TU AGAR CHAIYE TOH",
    "GAANDU",
    "CHUTIYA",
    "TERI MAA KI CHUT PE JCB CHADHAA DUNGA",
    "SAMJHAA LAWDE",
    "YA DU TERE GAAND ME TAPAA TAP",
    "TERI BEHEN MERA ROZ LETI HAI",
    "TERI GF K SAATH MMS BANAA CHUKA HU不不",
    "TU CHUTIYA TERA KHANDAAN CHUTIYA",
    "AUR KITNA BOLU BEY MANN BHAR GAYA MERA不",
    "TERIIIIII MAAAA KI CHUTTT ME ABCD LIKH DUNGA MAA KE LODE",
    "TERI MAA KO LEKAR MAI FARAR",
    "RANIDIII",
    "BACHEE",
    "CHODU",
    "RANDI",
    "RANDI KE PILLE",
    "TERIIIII MAAA KO BHEJJJ",
    "TERAA BAAAAP HU",
    "teri MAA KI CHUT ME HAAT DAALLKE BHAAG JAANUGA",
    "Teri maa KO SARAK PE LETAA DUNGA",
    "TERI MAA KO GB ROAD PE LEJAKE BECH DUNGA",
    "Teri maa KI CHUT MÉ KAALI MITCH",
    "TERI MAA SASTI RANDI HAI",
    "TERI MAA KI CHUT ME KABUTAR DAAL KE SOUP BANAUNGA MADARCHOD",
    "TERI MAAA RANDI HAI",
    "TERI MAAA KI CHUT ME DETOL DAAL DUNGA MADARCHOD",
    "TERI MAA KAAA BHOSDAA",
    "TERI MAA KI CHUT ME LAPTOP",
    "Teri maa RANDI HAI",
    "TERI MAA KO BISTAR PE LETAAKE CHODUNGA",
    "TERI MAA KO AMERICA GHUMAAUNGA MADARCHOD",
    "TERI MAA KI CHUT ME NAARIYAL PHOR DUNGA",
    "TERI MAA KE GAND ME DETOL DAAL DUNGA",
    "TERI MAAA KO HORLICKS PILAUNGA MADARCHOD",
    "TERI MAA KO SARAK PE LETAAA DUNGAAA",
    "TERI MAA KAA BHOSDA",
    "MERAAA LUND PAKAD LE MADARCHOD",
    "CHUP TERI MAA AKAA BHOSDAA",
    "TERIII MAA CHUF GEYII KYAAA LAWDEEE",
    "TERIII MAA KAA BJSODAAA",
    "MADARXHODDD",
    "TERIUUI MAAA KAA BHSODAAA",
    "TERIIIIII BEHENNNN KO CHODDDUUUU MADARXHODDDD",
    "NIKAL MADARCHOD",
    "RANDI KE BACHE",
    "TERA MAA MERI FAN",
    "TERI SEXY BAHEN KI CHUT OP",
]
