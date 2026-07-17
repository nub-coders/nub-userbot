import logging
import time
import datetime
import asyncio
import random
import re
import shlex
import queue
import subprocess
import os
import cv2
import base64
import json
import certifi
import imageio
import yt_dlp
from typing import Tuple, Any, Dict, Optional
from functools import wraps
from urllib.parse import urlparse

from PIL import Image
from mutagen import File, MutagenError
from yt_dlp import YoutubeDL

from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    Chat,
    InputMediaPhoto,
    InputMediaVideo,
    InputMediaAudio,
)
from pyrogram.enums import ChatType, ChatMemberStatus
from pyrogram.errors import FloodWait
from pyrogram.errors.exceptions import (
    AuthKeyDuplicated,
    MessageIdInvalid,
    AuthKeyUnregistered,
    PremiumAccountRequired,
    SessionRevoked,
    ChatForwardsRestricted,
    PeerFlood,
    UserRestricted,
    FileReferenceExpired,
    UserDeactivatedBan,
    PeerIdInvalid,
    UserDeactivated,
    GroupcallForbidden,
)
from pyrogram.raw.types import (
    DataJSON,
    InputPeerChannel,
    InputGroupCall,
    MessageEntityTextUrl,
    MessageEntityMentionName,
    InputStickerSetShortName,
    InputPeerChat,
    DocumentAttributeVideo,
    DocumentAttributeAudio,
)
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.phone import GetCallConfig, JoinGroupCall, CreateGroupCall, DiscardGroupCall
from pyrogram.raw.functions.messages import GetStickerSet, GetFullChat
from pyrogram.raw import functions
from youtube import handle_youtube, time_to_seconds
from pytgcalls import idle, PyTgCalls
from pytgcalls.types import ChatUpdate, AudioQuality, MediaStream, VideoQuality
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from tools import *
from utils.message import Msg
from config import *

# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

# Create a logger object
logger = logging.getLogger("userbot")

current_dir = f"{ggg}"

# Get the current date and time
current_time = datetime.datetime.now()
logger.info(f"[MUSIC] Plugin loaded at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

# Iterate over all sub-directories

def is_music_on():
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message):
            try:
                user_data = user_sessions.find_one({"user_id": client.me.id})
                raid_control = user_data.get('music', False) if user_data else False
                if raid_control:
                    # User is in raid list, proceed with command
                    return await func(client, message)
                else:
                    return  # Silent exit if not in raid list
            except Exception as e:
                logger.error(f"[MUSIC] is_music_on decorator error for user {client.me.id}: {e}")
                return
        return wrapper
    return decorator

async def is_active_chat(client, chat_id):
    if hasattr(client, 'me') and client.me.id in active:
        return chat_id in active[client.me.id]
    return False

async def add_active_chat(client, chat_id):
    if hasattr(client, 'me'):
        if client.me.id not in active:
            active[client.me.id] = []
        if chat_id not in active[client.me.id]:
            active[client.me.id].append(chat_id)


def format_duration(duration):
    """Format duration to HH:MM:SS, MM:SS, or SS format.

    Handles both integer seconds and ISO 8601 duration format.
    """
    # Check if duration is ISO 8601 format (from YouTube API)
    if isinstance(duration, str) and duration.startswith('PT'):
        match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration)
        hours = int(match.group(1)) if match.group(1) else 0
        minutes = int(match.group(2)) if match.group(2) else 0
        seconds = int(match.group(3)) if match.group(3) else 0
    else:
        # Handle integer seconds (from yt-dlp)
        try:
            duration = int(duration)
            hours = duration // 3600
            minutes = (duration % 3600) // 60
            seconds = duration % 60
        except (ValueError, TypeError):
            return "00:00"

    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    elif minutes > 0:
        return f"{minutes:02d}:{seconds:02d}"
    else:
        return f"{seconds:02d}"





def with_opencv(filename):
    # List of common audio file extensions
    audio_extensions = ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a', '.mp4', '.wma']
    file_ext = os.path.splitext(filename)[1].lower()

    # Handle audio files with mutagen
    if file_ext in audio_extensions:
        try:
            audio = File(filename)
            if audio is not None and hasattr(audio, 'info') and hasattr(audio.info, 'length'):
                duration = audio.info.length
                logger.debug(f"[MUSIC] Audio duration: {int(duration)}s")
                return int(duration)
            else:
                logger.debug(f"[MUSIC] No audio duration found")
                return 0
        except MutagenError:
            logger.debug(f"[MUSIC] Mutagen error reading audio file")
            return 0
    # Handle video files with OpenCV
    else:
        video = cv2.VideoCapture(filename)
        fps = video.get(cv2.CAP_PROP_FPS)
        frame_count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps if fps else 0
        video.release()
        logger.debug(f"[MUSIC] Video duration: {int(duration)}s")
        return int(duration)

# Modified media download with progress
async def download_media_with_progress(client, msg, media_msg, type_of):
    start_time = time.time()
    filename = getattr(media_msg, 'file_name', 'file')
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}/{msg.chat.id}"
    os.makedirs(user_dir, exist_ok=True)
    try:
        file_path = await client.download_media(media_msg,file_name=f"{user_dir}/",
            progress=progress_bar,
            progress_args=(client, msg, type_of, filename, start_time))
        return file_path
    except Exception as e:
        logger.error(f"[MUSIC] Download error for user {client.me.id}: {e}")
        return None

# Modified progress bar with error handling
async def progress_bar(current, total, client, msg, type_of, filename, start_time):
    if total == 0:
        return

    try:
            progress_percent = current * 100 / total
            progress_message = f"{type_of} {filename}: {progress_percent:.2f}%\n"

            # Progress bar calculation
            progress_bar_length = 20
            num_ticks = int(progress_percent / (100 / progress_bar_length))
            progress_bar_text = '█' * num_ticks + '░' * (progress_bar_length - num_ticks)

            # Speed calculation
            elapsed_time = time.time() - start_time
            speed = current / (elapsed_time * 1024 * 1024) if elapsed_time > 0 else 0

            # Time remaining calculation
            time_left = (total - current) / (speed * 1024 * 1024) if speed > 0 else 0

            # Format message
            progress_message += (
                f"Speed: {speed:.2f} MB/s\n"
                f"Time left: {time_left:.2f}s\n"
                f"Size: {current/1024/1024:.2f}MB / {total/1024/1024:.2f}MB\n"
                f"[{progress_bar_text}]"
            )

            # Edit message with exponential backoff
            try:
              if random.choices([True, False], weights=[1, 20])[0]:
                await msg.edit(progress_message)
            except Exception as e:
                logger.debug(f"[MUSIC] Progress update error for user {client.me.id}: {e}")

    except Exception as e:
        logger.error(f"[MUSIC] Progress bar error for user {client.me.id}: {e}")


async def put_queue(
    message,
    title,
    client,
    yt_link,
    chat,
    by,
    duration,
audio_flags,
stream_url = None,
forceplay = False):
    try:
        duration_in_seconds = time_to_seconds(duration) - 3
    except:
        duration_in_seconds = 0
    put = {
        "message": message,
        "title": title,
        "duration": duration,
        "mode": audio_flags,
        "yt_link": yt_link,
        "chat": chat,
        "by": by,
        "client": client,
        "stream_url": stream_url
    }
    if forceplay:
        song_queue = queues.get(f"dic_{client.me.id}")
        check = song_queue.get(chat.id)
        if check:
            song_queue[chat.id].insert(0, put)
        else:
            song_queue[chat.id] = []
            song_queue[chat.id].append(put)
    else:
        song_queue = queues.get(f"dic_{client.me.id}")
        check = song_queue.get(chat.id)

        if not check:
           song_queue[chat.id] = []
        song_queue[chat.id].append(put)

async def dend(client, update, channel_id=None):
    song_queue_key = f"dic_{client.me.id}"
    song_queue = queues.get(song_queue_key)
    if song_queue is None:
        logger.info(f"Song queue not found for user: {client.me.id}")
        call_py = songs_client.get(client.me.id)
        if call_py:
            await call_py.leave_call(channel_id or update.chat.id)
        await remove_active_chat(client, channel_id or update.chat.id)
        if (channel_id or update.chat.id) in playing:
            playing[channel_id or update.chat.id].clear()
        return

    call_py = songs_client.get(client.me.id)
    if not call_py:
        logger.info(f"Call client not found for user: {client.me.id}")
        return

    try:
        if (channel_id or update.chat.id) in song_queue and song_queue[(channel_id or update.chat.id)]:
            next_song = song_queue[(channel_id or update.chat.id)].pop(0)
            playing[(channel_id or update.chat.id)] = next_song
            await join_call(next_song['message'], next_song['title'], next_song['client'], next_song['yt_link'],
                           next_song['chat'], next_song['by'], next_song['duration'], next_song['mode'], next_song.get('stream_url'))
        else:
            logger.info(f"Song queue for chat {(channel_id or update.chat.id)} is empty.")
            await call_py.leave_call(channel_id or update.chat.id)
            await remove_active_chat(client, channel_id or update.chat.id)
            if (channel_id or update.chat.id) in playing:
                playing[(channel_id or update.chat.id)].clear()
    except Exception as e:
        logger.info(f"Error in end function: {e}")

# Music command handlers
@Client.on_message(filters.command(["play", "vplay", "playforce", "vplayforce"], prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def play_handler_func(client, message):
    if str(message.chat.id) == '-1001806816712':
         return
    session_name = f'user_{client.me.id}'
    user_dir = f"{ggg}/{session_name}"
    os.makedirs(user_dir, exist_ok=True)
    by = message.from_user
    escaped_prefixes = '|'.join(re.escape(p) for p in HARDCODED_PREFIXES)
    command_match = re.match(rf"^({escaped_prefixes})(\w+)", message.text or "")
    command = command_match.group(2).lower() if command_match else ""
    mode = "video" if command.startswith("v") else "audio"
    force_play = command.endswith("force")

    # Check if the command is sent in a group
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        await message.edit(
            f"Group Only\n\n"
            f"┃ Music works in groups & supergroups\n"
            f"╰▸ Join a group to stream music"
        )
        return

    youtube_link = None
    input_text = message.text.split(" ", 1)

    song_queue = queues.get(f"dic_{client.me.id}")
    if not song_queue:
        queues[f"dic_{client.me.id}"] = {}
        song_queue = queues[f"dic_{client.me.id}"]

    chat = message.chat
    target_chat_id = message.chat.id

    # Check queue for the target chat
    current_queue = len(song_queue.get(target_chat_id, [])) if song_queue else 0

    massage = await message.reply(
        f"╭━━ {Msg.EMOJI_SEARCH} SEARCHING ━━╮\n"
        f"┃ Finding your track...\n"
        f"╰━━━━━━━━━━━━━━━━━╯"
    )

    is_active = await is_active_chat(client, target_chat_id)
    await add_active_chat(client, target_chat_id)

    youtube_link = None
    media_info = {}
    stream_url = None

    # Check if replied to media message
    if message.reply_to_message and message.reply_to_message.media:
        media_msg = message.reply_to_message
        media_type = None
        duration = 0

        # Video handling
        if media_msg.video:
            media = media_msg.video
            media_type = "video"
            title = media.file_name or "Telegram Video"
            duration = media.duration

        # Audio handling
        elif media_msg.audio:
            media = media_msg.audio
            media_type = "audio"
            title = media.title or "Telegram Audio"
            duration = media.duration

        # Voice message handling
        elif media_msg.voice:
            media = media_msg.voice
            media_type = "voice"
            title = "Voice Message"
            duration = media.duration

        # Video note handling
        elif media_msg.video_note:
            media = media_msg.video_note
            media_type = "video_note"
            title = "Video Note"
            duration = media.duration
        elif media_msg.document:
            doc = media_msg.document
            for attr in doc.attributes:
                if isinstance(attr, DocumentAttributeVideo):
                    media_type = "video"
                    title = doc.file_name or "Telegram Video"
                    duration = attr.duration
                elif isinstance(attr, DocumentAttributeAudio):
                    media_type = "audio"
                    title = doc.file_name or "Telegram Audio"
                    duration = attr.duration
        else:
            await massage.edit(f"{Msg.EMOJI_ERROR} Unsupported media type")
            return await remove_active_chat(client, target_chat_id)
        if not media_type:
            await massage.edit(f"{Msg.EMOJI_ERROR} Unsupported media type")
            return await remove_active_chat(client, target_chat_id)
        # For media messages
        youtube_link = await download_media_with_progress(
            client,
            massage,
            message.reply_to_message,
            "Media"
        )

        # Format duration
        if not duration or duration <= 0:
            duration = with_opencv(youtube_link)
        duration = format_duration(int(duration))
        media_info = {
            'title': title,
            'duration': duration,
            'file_id': media.file_id,
            'media_type': media_type,
            'url': youtube_link
        }
    elif len(input_text) == 2:
        search_query = input_text[1]

        title, duration, youtube_link, thumbnail, channel_name, views, video_id, stream_url = await handle_youtube(search_query)
        logger.info(f"[MUSIC] YouTube search result for user {client.me.id}: {title}")
        if not youtube_link:
            try:
                await massage.edit(
                f"{Msg.EMOJI_SEARCH} No Results\n\n"
                f"┃ No matching track found\n"
                f"╰▸ Try a different search query"
            )
                return await remove_active_chat(client, target_chat_id)
            except:
                return await remove_active_chat(client, target_chat_id)
    else:
        try:
            await massage.edit(
                f"{Msg.EMOJI_QUESTION} No Query\n\n"
                f"┃ Please provide a search query\n"
                f"╰▸ Usage: `[prefix]play <song name>`"
            )
            return await remove_active_chat(client, target_chat_id)
        except:
            return

    # Use the same client for joining calls
    target_chat = message.chat

    await put_queue(
        massage,
        title,
        client,
        youtube_link,
        target_chat,
        by,
        duration,
        mode,
        stream_url,
        force_play
    )

    if is_active and not force_play:
        song_queue = queues.get(f"dic_{client.me.id}")
        position = len(song_queue.get(message.chat.id)) if song_queue.get(target_chat.id) else 1

        await client.send_message(message.chat.id, queue_styles[11].format(mode, title, duration, position), disable_web_page_preview=True)
    else:
        await dend(client, massage, None)
    # Message deletion removed - keeping original message

@Client.on_message(filters.command("end", prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def end_handler_func(client, message):
    # Message deletion removed - keeping original message
    try:
        call_py = songs_client.get(client.me.id)
        song_queue = queues.get(f"dic_{client.me.id}")
        is_active = await is_active_chat(client, message.chat.id)
        if is_active:
            await remove_active_chat(client, message.chat.id)
            if song_queue and message.chat.id in song_queue:
                song_queue[message.chat.id].clear()
            await client.send_message(message.chat.id, Msg.card("Stream Ended", ["Queue cleared and call left.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id)
            if call_py:
                await call_py.leave_call(message.chat.id)
            if message.chat.id in playing:
                playing[message.chat.id].clear()
        else:
            await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)
            await remove_active_chat(client, message.chat.id)
            if call_py:
                await call_py.leave_call(message.chat.id)
            if message.chat.id in playing:
                playing[message.chat.id].clear()
    except NotInCallError:
        await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)
        if message.chat.id in playing:
            playing[message.chat.id].clear()

@Client.on_message(filters.command("skip", prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def skip_handler_func(client, message):
    # Message deletion removed - keeping original message
    try:
        call_py = songs_client.get(client.me.id)
        song_queue = queues.get(f"dic_{client.me.id}")
        if song_queue and message.chat.id in song_queue:
            if len(song_queue[message.chat.id]) > 0:
                next_song = song_queue[message.chat.id].pop(0)
                await client.send_message(message.chat.id, Msg.card("Skipping", ["Loading next track...", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_INFO), reply_to_message_id=message.id)
                playing[message.chat.id] = next_song
                try:
                    if call_py:
                        await call_py.pause(message.chat.id)
                except:
                    pass
                await join_call(next_song['message'], next_song['title'], next_song['client'], next_song['yt_link'], next_song['chat'], next_song['by'], next_song['duration'], next_song['mode'], next_song.get('stream_url'))
            else:
                if call_py:
                    await call_py.leave_call(message.chat.id)
                await remove_active_chat(client, message.chat.id)
                await client.send_message(message.chat.id, Msg.card("Skipped", ["Queue is now empty.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id)
                if message.chat.id in playing:
                    playing[message.chat.id].clear()
        else:
            if call_py:
                await call_py.leave_call(message.chat.id)
            await remove_active_chat(client, message.chat.id)
            await client.send_message(message.chat.id, Msg.card("Skipped", ["Queue is now empty.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id)
            if message.chat.id in playing:
                playing[message.chat.id].clear()
    except NotInCallError:
        await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)
        if message.chat.id in playing:
            playing[message.chat.id].clear()

@Client.on_message(filters.command("pause", prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def pause_handler_func(client, message):
    try:
        call_py = songs_client.get(client.me.id)
        if await is_active_chat(client, message.chat.id):
            if call_py:
                await call_py.pause(message.chat.id)
            await client.send_message(message.chat.id, Msg.card("Paused", ["Use /resume to continue.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_INFO), reply_to_message_id=message.id)
        else:
            await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)
    except NotInCallError:
        await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)

@Client.on_message(filters.command("resume", prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def resume_handler_func(client, message):
    try:
        call_py = songs_client.get(client.me.id)
        if await is_active_chat(client, message.chat.id):
            if call_py:
                await call_py.resume(message.chat.id)
            await client.send_message(message.chat.id, Msg.card("Resumed", ["Use /pause to stop.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id)
        else:
            await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)
    except NotInCallError:
        await client.send_message(message.chat.id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id)

@Client.on_message(filters.command("loop", prefixes=HARDCODED_PREFIXES))
@is_music_on()
async def loop_handler_func(client, message):
    # Message deletion removed - keeping original message

    try:
        # Get loop count from command
        command_parts = message.text.split()
        if len(command_parts) != 2:
            await client.send_message(
                message.chat.id,
                Msg.card("Invalid Loop Command", ["Please specify the number of loops."], emoji=Msg.EMOJI_ERROR, footer="Usage: /loop <number>"), reply_to_message_id=message.id
            )
            return

        try:
            loop_count = int(command_parts[1])
            if loop_count <= 0 or loop_count > 20:
                await client.send_message(
                    message.chat.id,
                    Msg.card("Invalid Loop Count", ["Loop count must be between 1 and 20."], emoji=Msg.EMOJI_ERROR), reply_to_message_id=message.id
                )
                return
        except ValueError:
            await client.send_message(
                message.chat.id,
                Msg.card("Invalid Loop Count", ["Provide a valid number."], emoji=Msg.EMOJI_ERROR), reply_to_message_id=message.id
            )
            return

        # Check if there's a song playing
        if message.chat.id in playing and playing[message.chat.id]:
            current_song = playing[message.chat.id]
            song_queue = queues.get(f"dic_{client.me.id}")

            # Initialize queue for this chat if it doesn't exist
            if message.chat.id not in song_queue:
                song_queue[message.chat.id] = []

            # Add the current song to queue multiple times
            for _ in range(loop_count):
                song_queue[message.chat.id].insert(0, current_song)

            await client.send_message(
                message.chat.id,
                Msg.card("Loop Enabled", [f"Current song will repeat {loop_count} times.", f"By: {message.from_user.mention()}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id
            )
        else:
            await client.send_message(
                message.chat.id,
                Msg.card("No Stream", ["Assistant is not streaming anything."], emoji=Msg.EMOJI_WARNING, footer="Use /play to start"), reply_to_message_id=message.id
            )

    except Exception as e:
        await client.send_message(
            message.chat.id,
            Msg.card("Music Error", [f"An error occurred: {str(e)}"], emoji=Msg.EMOJI_ERROR), reply_to_message_id=message.id
        )

# Event handlers for stream end and voice chat events

# Additional music commands with dynamic prefix
@Client.on_message(filters.command("queue", prefixes=HARDCODED_PREFIXES) & filters.me)
@is_music_on()
async def queue_command(client, message):
    """Show current music queue"""
    try:
        song_queue = queues.get(f"dic_{client.me.id}")
        if not song_queue or not song_queue.get(message.chat.id):
            await message.edit(Msg.card("Queue Empty", ["No songs in queue."], emoji=Msg.EMOJI_INFO, footer="[prefix]play <song> to add"))
            return
        
        current_queue = song_queue[message.chat.id]
        if not current_queue:
            await message.edit(Msg.card("Queue Empty", ["No songs in queue."], emoji=Msg.EMOJI_INFO, footer="[prefix]play <song> to add"))
            return
        
        queue_text = f"╭━━ {Msg.EMOJI_MUSIC} MUSIC QUEUE ({len(current_queue)}) ━━╮\n\n"
        for i, song in enumerate(current_queue[:10], 1):  # Show first 10 songs
            title = song.get('title', 'Unknown Title')[:40]
            duration = song.get('duration', '00:00')
            queue_text += f"{i}. **{title}** - `{duration}`\n"
        
        if len(current_queue) > 10:
            queue_text += f"\n... and {len(current_queue) - 10} more songs"
        
        await message.edit(queue_text)
    except Exception as e:
        await message.edit(f"❌ **Error:** {str(e)}")

# Music.py Commands and Categories
music_commands = {
    'play': '**Play Audio** - Play audio from YouTube or other sources.\n\n**Usage:** `[prefix]play <query/url>` or reply to media\n**Example:** `[prefix]play Never Gonna Give You Up`',
    'vplay': '**Play Video** - Play video with audio from YouTube.\n\n**Usage:** `[prefix]vplay <query/url>` or reply to media\n**Example:** `[prefix]vplay music video`',
    'playforce': '**Force Play Audio** - Force play audio, skipping current queue.\n\n**Usage:** `[prefix]playforce <query/url>`\n**Example:** `[prefix]playforce song name`',
    'vplayforce': '**Force Play Video** - Force play video, skipping current queue.\n\n**Usage:** `[prefix]vplayforce <query/url>`\n**Example:** `[prefix]vplayforce video name`',
    'pause': '**Pause Playback** - Pause the current music/video.\n\n**Usage:** `[prefix]pause`\n**Note:** Use `[prefix]resume` to continue',
    'resume': '**Resume Playback** - Resume paused music/video.\n\n**Usage:** `[prefix]resume`\n**Note:** Use `[prefix]pause` to pause',
    'skip': '**Skip Track** - Skip to the next song in queue.\n\n**Usage:** `[prefix]skip`\n**Note:** Skips current track and plays next',
    'end': '**Stop Playback** - Stop music and clear the queue.\n\n**Usage:** `[prefix]end`\n**Note:** Stops all playback and clears queue',
    'loop': '**Loop Track** - Loop current song multiple times.\n\n**Usage:** `[prefix]loop <number>`\n**Example:** `[prefix]loop 5` (loops 5 times)\n**Note:** Maximum 20 loops',
    'queue': '**Show Queue** - Display current music queue.\n\n**Usage:** `[prefix]queue`\n**Note:** Shows upcoming songs',
    'music': '**Music Help** - Show all available music commands.\n\n**Usage:** `[prefix]music`\n**Note:** Displays music command help',
}

music_categories = {
    '🎵 MUSIC': ['play', 'vplay', 'playforce', 'vplayforce', 'pause', 'resume', 'skip', 'end', 'loop', 'queue', 'music'],
}

# Update global commands and categories
commands.update(music_commands)
categories.update(music_categories)
