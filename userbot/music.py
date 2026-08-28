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
from pytgcalls import PyTgCalls
from pytgcalls import filters as call_filters
from pytgcalls.types import (
    ChatUpdate,
    AudioQuality,
    MediaStream,
    VideoQuality,
    GroupCallConfig,
    StreamEnded,
)
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

from tools import *
from utils.message import Msg
from config import *

# No logging.basicConfig here: this module is imported as a plugin, and calling
# it reconfigured the root logger for the whole process behind main.py's back.
# Create a logger object
logger = logging.getLogger("userbot")

current_dir = os.getcwd()

# Get the current date and time
current_time = datetime.datetime.now()
logger.info(f"[MUSIC] Plugin loaded at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

# Iterate over all sub-directories

def is_music_on():
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message):
            # Only the toggle lookup is guarded. The handler used to run inside
            # this try as well, so every failure in every music command was
            # swallowed into a log line -- which is how five undefined names in
            # this file went unnoticed: the commands just did nothing.
            try:
                user_data = user_sessions.find_one({"user_id": client.me.id})
                music_enabled = user_data.get('music', False) if user_data else False
            except Exception as e:
                logger.error(f"[MUSIC] Could not read the music toggle for {client.me.id}: {e}")
                return
            if not music_enabled:
                return  # Silent exit if music is off for this user
            try:
                return await func(client, message)
            except Exception as e:
                logger.exception(f"[MUSIC] {func.__name__} failed: {e}")
                try:
                    await client.send_message(
                        message.chat.id,
                        styled_error("Music command failed", details=str(e)),
                        reply_to_message_id=message.id,
                    )
                except Exception:
                    pass
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


async def remove_active_chat(client, chat_id):
    """Mirror of add_active_chat: forget that we are streaming in this chat."""
    if not hasattr(client, 'me'):
        return
    chats = active.get(client.me.id)
    if chats and chat_id in chats:
        chats.remove(chat_id)


# ═══════════════ PLAYBACK RUNTIME ═══════════════
# The state and the three helpers the handlers below have always assumed but
# which never existed anywhere in this repo -- `queues`, `playing`,
# `queue_styles`, `join_call()` and `remove_active_chat()`. Every music command
# raised NameError on its first use, and `is_music_on`'s except swallowed it, so
# the whole plugin looked like it merely did nothing.
#
#   queues   {f"dic_{owner_id}": {chat_id: [song, ...]}}  what is waiting
#   playing  {chat_id: song}                              what is on air
#
# A "song" is the dict built by put_queue() below. `playing` holds a *copy* of
# it: the .loop command re-queues the playing song, and several handlers call
# playing[chat].clear(), which would otherwise empty the queued entries too.
queues: Dict[str, Dict[int, list]] = {}
playing: Dict[int, dict] = {}

# Style 11 is the plain one; it is what the queue message has always asked for.
DEFAULT_STYLE = 11
# Cap on a replied-to file we are willing to download for playback.
MAX_MEDIA_BYTES = 500 * 1024 * 1024
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
_QUEUE_FALLBACK = (
    "➕ **Added to queue**\n┃ **Mode:** {}\n┃ **Title:** {}\n"
    "┃ **Duration:** {}\n╰▸ **Position:** #{}"
)
_PLAY_FALLBACK = (
    "🎧 **Now Playing**\n┃ **Mode:** {}\n┃ **Title:** {}\n"
    "┃ **Duration:** {}\n╰▸ **Requested by:** {}"
)


def _load_styles(filename: str, fallback: str) -> Dict[int, str]:
    """Load the numbered message templates from data/, keyed by int.

    The JSON keys are strings but every call site indexes with an int. Templates
    with the wrong number of {} slots are dropped rather than allowed to raise
    IndexError mid-playback, and DEFAULT_STYLE is always present so indexing it
    cannot fail even with the file missing or corrupt.
    """
    styles: Dict[int, str] = {}
    path = os.path.join(_DATA_DIR, filename)
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        for key, template in (raw or {}).items():
            if not isinstance(template, str) or template.count("{}") != 4:
                logger.warning(f"[MUSIC] Skipping style {key} in {filename}: needs exactly 4 slots")
                continue
            try:
                styles[int(key)] = template
            except (TypeError, ValueError):
                logger.warning(f"[MUSIC] Skipping non-numeric style key {key!r} in {filename}")
    except Exception as e:
        logger.warning(f"[MUSIC] Could not load {path}: {e}")
    styles.setdefault(DEFAULT_STYLE, fallback)
    return styles


queue_styles = _load_styles("queue_styles.json", _QUEUE_FALLBACK)
play_styles = _load_styles("play_styles.json", _PLAY_FALLBACK)

# One PyTgCalls per userbot, created on first use; and one lock per userbot so
# two simultaneous .play commands cannot both build and start one.
_call_start_locks: Dict[int, asyncio.Lock] = {}
# One lock per chat, so the two StreamEnded events of a video track (AUDIO and
# VIDEO end separately) cannot advance the queue twice.
_advance_locks: Dict[int, asyncio.Lock] = {}


def _register_call_handlers(call_py: PyTgCalls, client) -> None:
    """Wire the call client's updates back into the queue."""

    @call_py.on_update(call_filters.stream_end())
    async def _on_stream_end(_, update: StreamEnded):
        chat_id = update.chat_id
        # Captured before taking the lock: a video track ends its audio and its
        # video stream separately, so this fires twice for one song. Whichever
        # event gets in first advances; the second sees a different (or no)
        # current song and stops, instead of skipping the next track unheard.
        finished = playing.get(chat_id)
        lock = _advance_locks.setdefault(chat_id, asyncio.Lock())
        async with lock:
            if playing.get(chat_id) is not finished:
                return
            logger.info(f"[MUSIC] Stream ended in {chat_id}; advancing queue")
            await dend(client, None, channel_id=chat_id)

    @call_py.on_update(
        call_filters.chat_update(
            ChatUpdate.Status.CLOSED_VOICE_CHAT
            | ChatUpdate.Status.KICKED
            | ChatUpdate.Status.LEFT_GROUP
        )
    )
    async def _on_call_gone(_, update: ChatUpdate):
        # The call is gone for reasons outside our control. Drop the state now,
        # otherwise is_active_chat keeps claiming we are streaming and every
        # later command talks to a call that no longer exists.
        chat_id = update.chat_id
        logger.info(f"[MUSIC] Call in {chat_id} ended externally ({update.status})")
        await remove_active_chat(client, chat_id)
        song_queue = queues.get(f"dic_{client.me.id}") or {}
        leftovers = song_queue.pop(chat_id, [])
        playing.pop(chat_id, None)
        for song in leftovers:
            _cleanup_song_file(song, [])


async def get_call_client(client) -> PyTgCalls:
    """Return this userbot's started PyTgCalls, creating it on first use.

    config.songs_client was declared but never populated by anything, so the
    call client was always None and every `if call_py:` in this file quietly did
    nothing. Built lazily: a userbot that never plays anything should not pay
    for a voice-call stack at startup.
    """
    owner_id = client.me.id
    call_py = songs_client.get(owner_id)
    if call_py is not None:
        return call_py

    lock = _call_start_locks.setdefault(owner_id, asyncio.Lock())
    async with lock:
        call_py = songs_client.get(owner_id)
        if call_py is not None:
            return call_py
        call_py = PyTgCalls(client)
        _register_call_handlers(call_py, client)
        await call_py.start()
        songs_client[owner_id] = call_py
        logger.info(f"[MUSIC] Call client started for user {owner_id}")
        return call_py


def _pick_source(yt_link, stream_url) -> Optional[str]:
    """Choose what to hand ffmpeg: a downloaded file, else a direct URL.

    A local path always wins -- it is already on disk and cannot expire.
    Otherwise the direct stream URL from youtube.py, and failing that the watch
    URL, which py-tgcalls resolves through yt-dlp itself.
    """
    if yt_link and os.path.exists(str(yt_link)):
        return str(yt_link)
    return stream_url or yt_link or None


def _cleanup_song_file(song: Optional[dict], keep: list) -> None:
    """Delete a finished track's download unless something still needs it.

    Downloads used to accumulate under user_<id>/<chat_id>/ forever: nothing in
    this file ever removed them. `keep` is the remaining queue, because .loop
    re-queues the same dict and would otherwise be left pointing at a file we
    just deleted.
    """
    if not song:
        return
    path = song.get("yt_link")
    if not path or not isinstance(path, str) or not os.path.exists(path):
        return
    # Only ever touch our own download directory.
    if not os.path.basename(os.path.dirname(os.path.dirname(path))).startswith("user_"):
        return
    if any(other.get("yt_link") == path for other in keep):
        return
    try:
        os.remove(path)
        logger.debug(f"[MUSIC] Removed finished download {path}")
    except OSError as e:
        logger.debug(f"[MUSIC] Could not remove {path}: {e}")


async def _say(message, client, chat_id, text):
    """Edit the status message, or send a new one if it is gone."""
    try:
        if message is not None:
            return await message.edit(text)
    except Exception as e:
        logger.debug(f"[MUSIC] Status edit failed, sending instead: {e}")
    try:
        return await client.send_message(chat_id, text)
    except Exception as e:
        logger.warning(f"[MUSIC] Could not report to {chat_id}: {e}")


def _requester(message):
    """Who asked, for the "By:" line of a card.

    `message.from_user` is None when the account posts as an anonymous admin or
    as the channel itself; `filters.me` still matches those (it also accepts a
    bare `outgoing`), so every card that reached straight for
    `.from_user.mention()` was one anonymous `.skip` away from an
    AttributeError. `mention` html-escapes its own text, so this is safe to
    interpolate.
    """
    return message.from_user.mention() if message.from_user else "unknown"


async def _drop_chat(client, chat_id):
    """Forget everything about a chat after a failed or finished stream."""
    await remove_active_chat(client, chat_id)
    song_queue = queues.get(f"dic_{client.me.id}") or {}
    for song in song_queue.pop(chat_id, []):
        _cleanup_song_file(song, [])
    playing.pop(chat_id, None)


async def join_call(message, title, client, yt_link, chat, by, duration, mode, stream_url=None):
    """Join the chat's voice call and stream one track.

    Called by dend() when a track comes off the queue and by .skip. On failure
    it clears the chat's state rather than leaving `active` claiming a stream
    that is not running.
    """
    chat_id = chat.id
    audio_only = str(mode).lower() != "video"
    source = _pick_source(yt_link, stream_url)
    if not source:
        await _say(message, client, chat_id, styled_error("Nothing to stream", hint="The download or lookup produced no media"))
        await _drop_chat(client, chat_id)
        return False

    try:
        call_py = await get_call_client(client)
    except Exception as e:
        logger.error(f"[MUSIC] Could not start the call client: {e}")
        await _say(message, client, chat_id, styled_error("Voice call support failed to start", details=str(e)))
        await _drop_chat(client, chat_id)
        return False

    stream = MediaStream(
        source,
        audio_parameters=AudioQuality.HIGH,
        video_parameters=VideoQuality.SD_480p,
        # IGNORE, not AUTO_DETECT: .play on a video file must stay audio-only,
        # otherwise it silently turns into a video stream.
        video_flags=MediaStream.Flags.IGNORE if audio_only else MediaStream.Flags.AUTO_DETECT,
    )

    try:
        # auto_start=False deliberately: creating a group call in somebody's
        # group is not something .play should do behind their back. `.vc1`
        # exists for that, and the message below points at it.
        await call_py.play(chat_id, stream, config=GroupCallConfig(auto_start=False))
    except NoActiveGroupCall:
        await _say(message, client, chat_id, Msg.card(
            "No Voice Chat",
            ["This chat has no voice chat running."],
            emoji=Msg.EMOJI_WARNING,
            footer="[prefix]vc1 to start one",
        ))
        await _drop_chat(client, chat_id)
        return False
    except Exception as e:
        logger.error(f"[MUSIC] play() failed in {chat_id}: {e}")
        await _say(message, client, chat_id, styled_error("Could not start the stream", details=str(e)))
        await _drop_chat(client, chat_id)
        return False

    await add_active_chat(client, chat_id)
    template = play_styles.get(DEFAULT_STYLE, _PLAY_FALLBACK)
    # Escaped: the title comes from YouTube or from a file name, and this goes
    # out under a parse mode that also processes HTML.
    requester = by.mention() if by is not None else "unknown"
    await _say(message, client, chat_id, template.format(
        "Video" if not audio_only else "Audio",
        html_esc(title),
        duration,
        requester,
    ))
    return True


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
def _media_of(media_msg):
    """The media object carrying file_name/file_size, whatever kind it is."""
    return (
        media_msg.audio or media_msg.video or media_msg.document
        or media_msg.voice or media_msg.video_note or media_msg.animation
    )


async def download_media_with_progress(client, msg, media_msg, type_of):
    start_time = time.time()
    # file_name lives on the media object; Message has no such attribute, so
    # this always used to read 'file'.
    media_obj = _media_of(media_msg)
    filename = getattr(media_obj, 'file_name', None) or 'file'
    session_name = f'user_{client.me.id}'
    user_dir = f"{session_name}/{msg.chat.id}"
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
    except Exception as e:
        logger.debug(f"duration parse failed for {duration!r}: {e}")
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
    # setdefault: the queue dict for this owner may not exist yet, and .get()
    # returning None here used to be an AttributeError two lines later.
    song_queue = queues.setdefault(f"dic_{client.me.id}", {})
    chat_songs = song_queue.setdefault(chat.id, [])
    if forceplay:
        chat_songs.insert(0, put)
    else:
        chat_songs.append(put)

async def dend(client, update, channel_id=None):
    """Advance the queue in one chat: play the next track, or leave the call.

    `update` is the status message to edit; it may be None when the caller is
    the stream-end handler, in which case channel_id says which chat.
    """
    chat_id = channel_id if channel_id is not None else (update.chat.id if update else None)
    if chat_id is None:
        logger.warning("[MUSIC] dend called without a chat to act on")
        return

    song_queue_key = f"dic_{client.me.id}"
    song_queue = queues.setdefault(song_queue_key, {})

    # The call client is created on demand: on the very first .play nothing has
    # built it yet, and the old `if not call_py: return` here meant the first
    # track was dropped on the floor before it could ever be played.
    try:
        call_py = await get_call_client(client)
    except Exception as e:
        logger.error(f"[MUSIC] Could not start the call client: {e}")
        await _say(update, client, chat_id, styled_error("Voice call support failed to start", details=str(e)))
        await _drop_chat(client, chat_id)
        return

    finished = playing.get(chat_id)

    try:
        if song_queue.get(chat_id):
            next_song = song_queue[chat_id].pop(0)
            # A copy, so .clear() on the playing entry elsewhere cannot empty a
            # song that .loop has also put back in the queue.
            playing[chat_id] = dict(next_song)
            if finished is not None:
                _cleanup_song_file(finished, song_queue.get(chat_id, []))
            await join_call(
                next_song['message'], next_song['title'], next_song['client'], next_song['yt_link'],
                next_song['chat'], next_song['by'], next_song['duration'], next_song['mode'],
                next_song.get('stream_url'),
            )
        else:
            logger.info(f"Song queue for chat {chat_id} is empty.")
            try:
                await call_py.leave_call(chat_id)
            except (NoActiveGroupCall, NotInCallError):
                pass
            await remove_active_chat(client, chat_id)
            playing.pop(chat_id, None)
            _cleanup_song_file(finished, [])
    except Exception as e:
        # exception(), not info(): join_call reports its own failures, so anything
        # arriving here is a malformed queue entry or a bug, and "Error in end
        # function" with no traceback is how this file hid five NameErrors.
        logger.exception(f"[MUSIC] Queue advance failed in {chat_id}")
        await _say(update, client, chat_id, styled_error("Could not advance the queue", details=str(e)))
        await _drop_chat(client, chat_id)


async def _abort_play(client, chat_id, was_active):
    """Undo .play's provisional `active` claim without disturbing a live stream.

    .play marks the chat active before it searches, so a second .play arriving
    while the first is still downloading queues instead of racing it into a
    rival stream. That makes every early return responsible for undoing the
    claim -- but only when nothing was playing to begin with. Unconditional
    removal meant a reply to an unsupported file cleared the flag out from under
    the track that was already streaming, after which .pause and .skip both
    answered "No Stream".
    """
    if not was_active:
        await remove_active_chat(client, chat_id)


# Music command handlers
# `is_music_on` is a feature toggle, not an authorization check: it reads the
# *owner's* `music` flag, so once the owner turns music on it says yes to whoever
# sent the command. Every handler below therefore carries its own sender gate.
# Without one, any member of any group the account is in could drive voice-chat
# joins and unbounded downloads on the owner's host (`.queue` below always had
# the gate, which is what made the omission on the rest look accidental).
# Sudo users are allowed through because delegating playback is the point of a
# music plugin in a group; tighten to plain `filters.me` if that is unwanted.
@Client.on_message(filters.command(["play", "vplay", "playforce", "vplayforce"], prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def play_handler_func(client, message):
    if str(message.chat.id) == '-1001806816712':
         return
    session_name = f'user_{client.me.id}'
    user_dir = session_name
    os.makedirs(user_dir, exist_ok=True)
    by = message.from_user
    escaped_prefixes = '|'.join(re.escape(p) for p in HARDCODED_PREFIXES)
    command_match = re.match(rf"^({escaped_prefixes})(\w+)", cmd_text(message))
    command = command_match.group(2).lower() if command_match else ""
    mode = "video" if command.startswith("v") else "audio"
    force_play = command.endswith("force")

    # Check if the command is sent in a group
    if message.chat.type not in [ChatType.GROUP, ChatType.SUPERGROUP]:
        # edit_or_reply, not edit: sudo users can run .play and their message is
        # not ours to edit, so this raised MessageAuthorRequired instead of
        # telling them music is group-only.
        await edit_or_reply(
            message,
            f"Group Only\n\n"
            f"┃ Music works in groups & supergroups\n"
            f"╰▸ Join a group to stream music"
        )
        return

    youtube_link = None
    input_text = cmd_text(message).split(" ", 1)

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
            media = doc
            # pyrogram's Document has no `attributes` -- that is a raw-API type.
            # Iterating it raised AttributeError, and `media` was never bound in
            # this branch either, so replying to any document file blew up two
            # lines further down. Decide on the mime type instead.
            mime = (doc.mime_type or "").lower()
            if mime.startswith("video/"):
                media_type = "video"
                title = doc.file_name or "Telegram Video"
            elif mime.startswith("audio/"):
                media_type = "audio"
                title = doc.file_name or "Telegram Audio"
            else:
                # Some clients send audio as application/octet-stream; fall back
                # to the extension before giving up.
                ext = os.path.splitext(doc.file_name or "")[1].lower()
                if ext in ('.mp3', '.m4a', '.flac', '.wav', '.ogg', '.opus', '.aac', '.wma'):
                    media_type = "audio"
                    title = doc.file_name or "Telegram Audio"
                elif ext in ('.mp4', '.mkv', '.webm', '.avi', '.mov', '.m4v'):
                    media_type = "video"
                    title = doc.file_name or "Telegram Video"
        else:
            await massage.edit(f"{Msg.EMOJI_ERROR} Unsupported media type")
            return await _abort_play(client, target_chat_id, is_active)
        if not media_type:
            await massage.edit(f"{Msg.EMOJI_ERROR} Unsupported media type")
            return await _abort_play(client, target_chat_id, is_active)

        # Cap the download: this runs on the owner's own disk, and a reply to a
        # 4GB file used to be accepted without a word.
        file_size = getattr(media, "file_size", 0) or 0
        if file_size > MAX_MEDIA_BYTES:
            await massage.edit(Msg.card(
                "File Too Large",
                [f"That file is {file_size / 1048576:.0f}MB.",
                 f"The limit is {MAX_MEDIA_BYTES // 1048576}MB."],
                emoji=Msg.EMOJI_WARNING,
            ))
            return await _abort_play(client, target_chat_id, is_active)
        # For media messages
        youtube_link = await download_media_with_progress(
            client,
            massage,
            message.reply_to_message,
            "Media"
        )

        # Bail out here rather than queueing a track with no source: the
        # download returns None on failure.
        if not youtube_link:
            await massage.edit(styled_error("Download failed", hint="Could not fetch that media from Telegram"))
            return await _abort_play(client, target_chat_id, is_active)

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
                return await _abort_play(client, target_chat_id, is_active)
            except Exception as e:
                logger.debug(f"No-results edit failed: {e}")
                return await _abort_play(client, target_chat_id, is_active)
    else:
        try:
            await massage.edit(
                f"{Msg.EMOJI_QUESTION} No Query\n\n"
                f"┃ Please provide a search query\n"
                f"╰▸ Usage: `[prefix]play <song name>`"
            )
            return await _abort_play(client, target_chat_id, is_active)
        except Exception as e:
            logger.debug(f"No-query edit failed: {e}")
            # Still undo the claim: whether the status message could be edited
            # has nothing to do with whether we are streaming.
            return await _abort_play(client, target_chat_id, is_active)

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
        song_queue = queues.get(f"dic_{client.me.id}") or {}
        position = len(song_queue.get(target_chat.id) or []) or 1
        # Escaped: the title comes from YouTube or from a file name.
        await client.send_message(
            message.chat.id,
            queue_styles.get(DEFAULT_STYLE, _QUEUE_FALLBACK).format(
                "Video" if mode == "video" else "Audio", html_esc(title), duration, position
            ),
            disable_web_page_preview=True,
        )
    else:
        await dend(client, massage, target_chat_id)
    # Message deletion removed - keeping original message

@Client.on_message(filters.command("end", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def end_handler_func(client, message):
    # Message deletion removed - keeping original message
    chat_id = message.chat.id
    was_active = await is_active_chat(client, chat_id) or chat_id in playing
    call_py = songs_client.get(client.me.id)
    if call_py:
        try:
            await call_py.leave_call(chat_id)
        except (NotInCallError, NoActiveGroupCall):
            pass
        except Exception as e:
            logger.debug(f"[MUSIC] leave_call on .end failed: {e}")
    # One helper for the whole teardown: drop the chat from `active`, empty its
    # queue, delete the downloads it left behind and forget what was playing.
    # The four hand-rolled copies of this used to each forget something.
    await _drop_chat(client, chat_id)
    if was_active:
        card = Msg.card("Stream Ended", ["Queue cleared and call left.", f"By: {_requester(message)}"], emoji=Msg.EMOJI_SUCCESS)
    else:
        card = Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="[prefix]play to start")
    await client.send_message(chat_id, card, reply_to_message_id=message.id)

@Client.on_message(filters.command("skip", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def skip_handler_func(client, message):
    # Message deletion removed - keeping original message
    chat_id = message.chat.id
    if not await is_active_chat(client, chat_id) and chat_id not in playing:
        await client.send_message(chat_id, Msg.card("No Stream", ["Nothing is playing right now."], emoji=Msg.EMOJI_WARNING, footer="[prefix]play to start"), reply_to_message_id=message.id)
        return

    upcoming = (queues.get(f"dic_{client.me.id}") or {}).get(chat_id) or []
    if upcoming:
        card = Msg.card("Skipping", ["Loading next track...", f"By: {_requester(message)}"], emoji=Msg.EMOJI_INFO)
    else:
        card = Msg.card("Skipped", ["Queue is now empty.", f"By: {_requester(message)}"], emoji=Msg.EMOJI_SUCCESS)
    await client.send_message(chat_id, card, reply_to_message_id=message.id)
    # dend() already does exactly this: play the next track or leave the call,
    # cleaning up the finished download either way.
    await dend(client, None, chat_id)

_NO_STREAM_LINES = ["Nothing is playing right now."]


def _no_stream_card():
    return Msg.card(
        "No Stream",
        _NO_STREAM_LINES,
        emoji=Msg.EMOJI_WARNING,
        footer="[prefix]play to start",
    )


async def _toggle_stream(client, message, action):
    """Shared body of .pause and .resume.

    `call_py` has to be present for the claim to be true: reporting "Paused"
    while the call client is missing told the operator the stream was suspended
    when nothing had been touched.
    """
    call_py = songs_client.get(client.me.id)
    if not call_py or not await is_active_chat(client, message.chat.id):
        await client.send_message(message.chat.id, _no_stream_card(), reply_to_message_id=message.id)
        return
    try:
        await getattr(call_py, action)(message.chat.id)
    except (NotInCallError, NoActiveGroupCall):
        # Our state said we were streaming and Telegram disagrees, so believe
        # Telegram and forget the chat instead of leaving `active` stale.
        await _drop_chat(client, message.chat.id)
        await client.send_message(message.chat.id, _no_stream_card(), reply_to_message_id=message.id)
        return
    except Exception as e:
        logger.exception(f"[MUSIC] .{action} failed in {message.chat.id}")
        await client.send_message(
            message.chat.id,
            styled_error(f"Could not {action} the stream", details=str(e)),
            reply_to_message_id=message.id,
        )
        return

    if action == "pause":
        card = Msg.card("Paused", ["Use [prefix]resume to continue.", f"By: {_requester(message)}"], emoji=Msg.EMOJI_INFO)
    else:
        card = Msg.card("Resumed", ["Use [prefix]pause to stop.", f"By: {_requester(message)}"], emoji=Msg.EMOJI_SUCCESS)
    await client.send_message(message.chat.id, card, reply_to_message_id=message.id)


@Client.on_message(filters.command("pause", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def pause_handler_func(client, message):
    await _toggle_stream(client, message, "pause")


@Client.on_message(filters.command("resume", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def resume_handler_func(client, message):
    await _toggle_stream(client, message, "resume")

@Client.on_message(filters.command("loop", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@is_music_on()
async def loop_handler_func(client, message):
    # Message deletion removed - keeping original message

    try:
        # Get loop count from command
        command_parts = cmd_text(message).split()
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
        current_song = playing.get(message.chat.id)
        if current_song:
            # setdefault, not get: nothing guarantees the owner's dict exists
            # yet -- .loop can be the first music command of the process, and
            # get() returning None made this an AttributeError.
            song_queue = queues.setdefault(f"dic_{client.me.id}", {})
            chat_songs = song_queue.setdefault(message.chat.id, [])

            # dict(...) per iteration, not the same object N times. dend() pops
            # a song and hands it to _cleanup_song_file, which deletes the
            # download once it is no longer referenced; sharing one dict across
            # every copy meant mutating or clearing one entry hit them all.
            for _ in range(loop_count):
                chat_songs.insert(0, dict(current_song))

            await client.send_message(
                message.chat.id,
                Msg.card("Loop Enabled", [f"Current song will repeat {loop_count} times.", f"By: {_requester(message)}"], emoji=Msg.EMOJI_SUCCESS), reply_to_message_id=message.id
            )
        else:
            await client.send_message(
                message.chat.id,
                _no_stream_card(), reply_to_message_id=message.id
            )

    except Exception as e:
        # exception(), not warning(): the whole reason five undefined names sat
        # in this file unnoticed is that music failures were logged without a
        # traceback and reported as "Something went wrong."
        logger.exception("[MUSIC] .loop failed")
        await client.send_message(
            message.chat.id,
            styled_error("Could not set up the loop", details=str(e)), reply_to_message_id=message.id
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
        
        lines = []
        for i, song in enumerate(current_queue[:10], 1):  # Show first 10 songs
            title = str(song.get('title', 'Unknown Title'))[:40].replace("<", "&lt;").replace(">", "&gt;")
            duration = str(song.get('duration', '00:00'))
            lines.append(f"<b>{i}.</b> {title} — <code>{duration}</code>")

        extra = f"\n\n<i>... and {len(current_queue) - 10} more songs in queue</i>" if len(current_queue) > 10 else ""

        queue_html = (
            f"<b>{Msg.EMOJI_MUSIC} Music Queue ({len(current_queue)})</b>\n\n"
            f"<blockquote>\n" + "\n".join(lines) + f"\n</blockquote>"
            f"{extra}"
        )
        await message.edit(queue_html, parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        # details=, not the headline: styled_error only escapes details, and an
        # exception string here carries a title or a file name.
        logger.exception("[MUSIC] .queue failed")
        await message.edit(styled_error("Could not show the queue", details=str(e)), parse_mode=enums.ParseMode.HTML)



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
