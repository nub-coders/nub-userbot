

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
    if not text:
        return "", entities or []

    entities = list(entities) if entities else []

    if not words_to_remove:
        return text, entities

    for word in words_to_remove:
        while True:
            idx = text.find(word)
            if idx == -1:
                break
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
    return text, entities


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

