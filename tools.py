

# Common imports used across plugins
import requests
import re
import os
import contextlib
import sys
import time
import random
import asyncio
import math
import shlex
import datetime
import subprocess
import base64
import html
import json
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

# py-tgcalls: only the pieces the playback runtime at the bottom of this file
# needs. PyTgCalls itself is deliberately absent -- main.py constructs the one
# call client per account and puts it in config.songs_client.
from pytgcalls import filters as call_filters
from pytgcalls.types import (
    AudioQuality,
    ChatUpdate,
    GroupCallConfig,
    MediaStream,
    StreamEnded,
    VideoQuality,
)
from pytgcalls.exceptions import NoActiveGroupCall, NotInCallError

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

logger = logging.getLogger("tools")

from config import (
    apps,
    clients,
    user_sessions,
    admin_file,
    SUDO,
    HARDCODED_PREFIXES,
    active,
    songs_client,
    queues,
    playing,
)
from utils.message import Msg


# ─────────────────── download destination confinement ───────────────────────
# Passing a bare directory to `download_media` (which nearly every call site in
# this project does, e.g. `download(f"{user_dir}/")`) makes kurigram fall back to
# the *sender's* filename: `download_media.py` splits the caller's argument, gets
# an empty basename, substitutes `media.file_name` from the document's
# DocumentAttributeFilename verbatim, and `Client.handle_download` then writes to
# `abspath(join(directory, file_name))` with no basename call and no traversal
# check. A document named `../userbot/x.py` therefore lands outside the intended
# directory -- and this project loads `userbot/*.py` and the extra-plugins
# directory as code at startup, so an arbitrary write there is code execution on
# the next restart. The name is chosen by whoever sent the file, not by the
# operator who runs `.kang` or `.ocr` on it.
#
# `handle_download` is patched rather than the ~20 call sites because it is the
# single funnel every download passes through -- message media, a bare file_id,
# present and future callers alike -- and it receives the directory and the final
# filename already separated, which is exactly where the basename belongs.
# Sanitising is deliberately limited to path separators, traversal and leading
# dots, so unicode filenames and spaces survive intact and downloads keep the
# names users expect.
def _safe_download_basename(file_name, fallback="download"):
    """`file_name` reduced to a basename that cannot escape its directory."""
    name = os.path.basename(str(file_name or "").replace("\\", "/"))
    # Strips ".", ".." and hidden names like ".env" in one go.
    return name.lstrip(".") or fallback


def _install_download_guard():
    original = getattr(Client, "handle_download", None)
    if original is None or getattr(original, "_nub_guarded", False):
        # Nothing to wrap, or already wrapped by a re-import of this module.
        if original is None:
            logger.warning(
                "Client.handle_download is missing; download paths are unconfined"
            )
        return

    async def handle_download(self, packet):
        file_id, directory, file_name, in_memory, file_size, progress, progress_args = packet
        safe_name = _safe_download_basename(file_name)
        if safe_name != file_name:
            logger.warning(
                "Confined download filename %r to %r in %r",
                file_name, safe_name, directory,
            )
        return await original(
            self,
            (file_id, directory, safe_name, in_memory, file_size, progress, progress_args),
        )

    handle_download._nub_guarded = True
    Client.handle_download = handle_download


_install_download_guard()

# Simple TTL cache for user session data
import copy
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
                # A copy: this used to hand back the cached document itself, so
                # a caller that mutated what it got (or held on to a nested
                # list) silently rewrote what every later reader saw.
                return copy.deepcopy(entry[0])
            return None

    def set(self, user_id, data):
        with self._lock:
            self._cache[user_id] = (copy.deepcopy(data), time.time())

    def invalidate(self, user_id=None):
        with self._lock:
            if user_id is not None:
                self._cache.pop(user_id, None)
            else:
                self._cache.clear()

_session_cache = _SessionCache(ttl=30)

# Drop cached documents as soon as anything writes to the collection, instead of
# trusting each of the twenty-odd write sites to remember (only two did).
# user_id is None for writes that don't name a single document, which clears the
# lot -- correct, if blunt.
user_sessions.on_write(_session_cache.invalidate)


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


def html_esc(text) -> str:
    """Escape untrusted text before it goes into an HTML parse-mode message.

    kurigram's HTML parser is lenient -- it does not raise on stray or unmatched
    tags -- so the damage is silent rather than loud, which is worse:

      * Anything that looks like a tag is *deleted*. "<code>KeyError:
        <users.42></code>" renders as "KeyError: " and the useful half of the
        exception is gone, with no hint that it was dropped.
      * Tags in a display name are honoured. A stranger whose first name is
        '<a href="http://evil">click</a>' gets a real link entity in the
        message our account sends -- their text, our voice.

    quote=False keeps quotes readable; they are harmless outside attributes,
    and nothing here interpolates into an attribute.
    """
    return html.escape(str(text), quote=False)


def styled_error(text, details="", hint=""):
    """Format an error message with standard MTProto HTML typography."""
    parts = [
        "<b>❌ Error</b>",
        f"<blockquote>{text}</blockquote>"
    ]
    if details:
        parts.append(f"<blockquote expandable><b>Technical Details:</b>\n<code>{html_esc(details)}</code></blockquote>")
    if hint:
        parts.append(f"💡 <i>{hint}</i>")
    return "\n\n".join(parts)


def styled_success(text, details="", table_headers=None, table_rows=None):
    """Format a success message with standard MTProto HTML."""
    parts = [
        "<b>✅ Success</b>",
        f"<blockquote>{text}</blockquote>"
    ]
    if table_rows:
        row_lines = []
        for row in table_rows:
            if table_headers and len(table_headers) == len(row):
                row_lines.append(" • " + " | ".join(f"<b>{h}:</b> {c}" for h, c in zip(table_headers, row)))
            else:
                row_lines.append(" • " + " | ".join(str(c) for c in row))
        parts.append("<blockquote>" + "\n".join(row_lines) + "</blockquote>")
    if details:
        parts.append(f"<blockquote expandable><b>Additional Info:</b>\n{details}</blockquote>")
    return "\n\n".join(parts)


def can_grant_privilege(promoter_privileges, privilege_name):
    """Check if the promoter has a specific privilege they can grant."""
    return getattr(promoter_privileges, privilege_name, False)


def styled_help_categories(categories_dict, prefix):
    """Format help categories overview using standard MTProto HTML."""
    lines = []
    for cat, cmds in categories_dict.items():
        if cmds:
            sample = ", ".join(f"<code>{prefix}{c}</code>" for c in cmds[:4])
            count = len(cmds)
            lines.append(f"<b>• {cat}</b> ({count}): {sample}")
        else:
            lines.append(f"<b>• {cat}</b>: <i>empty</i>")

    return (
        "<b>📖 Command Categories</b>\n\n"
        f"<blockquote>{chr(10).join(lines)}</blockquote>\n\n"
        f"💡 <i>Use <code>{prefix}help &lt;command&gt;</code> for detailed instructions.</i>"
    )


def styled_help_card(cmd, desc, usage, example="", note="", flags="", warning=""):
    """Format a single command help card using standard MTProto HTML."""
    parts = [
        f"<b>📖 <code>{cmd}</code></b>",
        f"{desc}"
    ]
    if usage:
        parts.append(f"<blockquote><b>Usage:</b> <code>{usage}</code></blockquote>")

    details = []
    if example:
        details.append(f"<b>• Example:</b> <code>{example}</code>")
    if flags:
        details.append(f"<b>• Flags:</b> <code>{flags}</code>")
    if note:
        details.append(f"💡 <b>Note:</b> {note}")
    if warning:
        details.append(f"⚠️ <b>Warning:</b> {warning}")

    if details:
        parts.append("<blockquote expandable><b>Options & Details:</b>\n" + "\n".join(details) + "</blockquote>")

    return "\n\n".join(parts)




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


def parse_help_entry(raw_text):
    """Parse a raw help entry into structured fields."""
    desc = usage = example = note = warning = flags = ""
    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        ll = line.lower()
        if ll.startswith("**usage:**"):
            usage = line.split("**Usage:**", 1)[-1].strip()
        elif ll.startswith("**example:**"):
            example = line.split("**Example:**", 1)[-1].strip()
        elif ll.startswith("**examples:**"):
            example = line.split("**Examples:**", 1)[-1].strip()
        elif ll.startswith("**flags:**"):
            flags = line.split("**Flags:**", 1)[-1].strip()
        elif ll.startswith("**note:**"):
            note = line.split("**Note:**", 1)[-1].strip()
        elif ll.startswith("**warning:**"):
            warning = line.split("**Warning:**", 1)[-1].strip()
        elif ll.startswith("**features:**"):
            note = line.split("**Features:**", 1)[-1].strip()
        elif ll.startswith("**options:**"):
            flags = line.split("**Options:**", 1)[-1].strip()
        elif ll.startswith("**supported:**"):
            note = line.split("**Supported:**", 1)[-1].strip()
        elif " - " in line and not desc:
            desc = line.split(" - ", 1)[-1].strip()
    if not desc and lines:
        first = lines[0].strip().strip("*")
        if " - " in first:
            desc = first.split(" - ", 1)[-1].strip()
        else:
            desc = first
    return desc, usage, example, note, warning, flags


# Global help registries
DEFAULT_COMMANDS = {
    'alive': '**Check Online** - Check if userbot is running.\n\n**Usage:** `[prefix]alive`',
    'ping': '**Ping Response** - Test response time and server stats.\n\n**Usage:** `[prefix]ping`',
    'stats': '**View Statistics** - Comprehensive userbot and account stats.\n\n**Usage:** `[prefix]stats`',
    'info': '**User Info** - Get detailed info for a user or chat.\n\n**Usage:** `[prefix]info [user]`',
    'status': '**User Status** - View detailed system status and settings.\n\n**Usage:** `[prefix]status`',
    'sessions': '**Active Sessions** - View active Telegram account sessions.\n\n**Usage:** `[prefix]sessions`',
    'ban': '**Ban User** - Ban user from current chat.\n\n**Usage:** `[prefix]ban [user]`',
    'unban': '**Unban User** - Unban user in current chat.\n\n**Usage:** `[prefix]unban [user]`',
    'kick': '**Kick User** - Kick user out of current chat.\n\n**Usage:** `[prefix]kick [user]`',
    'mute': '**Mute User** - Restrict user from sending messages.\n\n**Usage:** `[prefix]mute [user]`',
    'unmute': '**Unmute User** - Restore messaging permissions.\n\n**Usage:** `[prefix]unmute [user]`',
    'pin': '**Pin Message** - Pin replied message.\n\n**Usage:** `[prefix]pin [reply]`',
    'unpin': '**Unpin Message** - Unpin pinned message.\n\n**Usage:** `[prefix]unpin`',
    'promote': '**Promote Admin** - Grant admin rights to user.\n\n**Usage:** `[prefix]promote [user]`',
    'demote': '**Demote Admin** - Revoke admin rights from user.\n\n**Usage:** `[prefix]demote [user]`',
    'tagall': '**Mention All** - Mention all members in the group.\n\n**Usage:** `[prefix]tagall [text]`',
    'power': '**Full Power** - Promote user with full admin permissions.\n\n**Usage:** `[prefix]power [user]`',
    'play': '**Play Audio** - Stream audio in voice chat.\n\n**Usage:** `[prefix]play <query>`',
    'vplay': '**Play Video** - Stream video in voice chat.\n\n**Usage:** `[prefix]vplay <query>`',
    'playforce': '**Force Play Audio** - Stream audio immediately.\n\n**Usage:** `[prefix]playforce <query>`',
    'vplayforce': '**Force Play Video** - Stream video immediately.\n\n**Usage:** `[prefix]vplayforce <query>`',
    'pause': '**Pause Playback** - Pause active voice chat stream.\n\n**Usage:** `[prefix]pause`',
    'resume': '**Resume Playback** - Resume paused voice chat stream.\n\n**Usage:** `[prefix]resume`',
    'skip': '**Skip Track** - Skip current voice chat track.\n\n**Usage:** `[prefix]skip`',
    'end': '**Stop Playback** - Stop voice chat stream and clear queue.\n\n**Usage:** `[prefix]end`',
    'loop': '**Loop Track** - Loop current track.\n\n**Usage:** `[prefix]loop <count>`',
    'queue': '**Show Queue** - Display voice chat queue.\n\n**Usage:** `[prefix]queue`',
    'vc1': '**Start VC** - Start group voice chat call.\n\n**Usage:** `[prefix]vc1`',
    'vc0': '**End VC** - End group voice chat call.\n\n**Usage:** `[prefix]vc0`',
    'ask': '**AI Agent** - Ask the AI agent; it can search the web and read files before answering, and remembers the conversation per chat.\n\n**Usage:** `[prefix]ask <question>` or `[prefix]ai <question>`',
    'ai': '**AI Agent** - Alias for `ask`. Ask the AI agent with web search and host file capabilities.\n\n**Usage:** `[prefix]ai <question>`',
    'askclear': '**Clear AI Memory** - Forget the AI agent conversation history for this chat.\n\n**Usage:** `[prefix]askclear` or `[prefix]aiclear`',
    'askmodel': '**AI Model Info** - Show the active AI model and armed tools.\n\n**Usage:** `[prefix]askmodel` or `[prefix]aimodel`',
    'qt': '**Quote Sticker** - Create quote sticker from message.\n\n**Usage:** `[prefix]qt [reply]`',
    'kang': '**Add Sticker** - Add sticker or photo to custom pack.\n\n**Usage:** `[prefix]kang [reply]`',
    'tiny': '**Tiny Sticker** - Shrink sticker or photo.\n\n**Usage:** `[prefix]tiny [reply]`',
    'mmf': '**Meme Maker** - Add top/bottom text to photo.\n\n**Usage:** `[prefix]mmf <top> ; <bottom>`',
    'ocr': '**Extract Text** - Perform OCR on image.\n\n**Usage:** `[prefix]ocr [reply]`',
    'purge': '**Purge Messages** - Delete message range.\n\n**Usage:** `[prefix]purge [reply]`',
    'del': '**Delete Message** - Delete replied message.\n\n**Usage:** `[prefix]del [reply]`',
    'frwd': '**Raw Forward** - Forward message without forward header.\n\n**Usage:** `[prefix]frwd [reply]`',
    'block': '**Block User** - Block user in private chat.\n\n**Usage:** `[prefix]block [user]`',
    'unblock': '**Unblock User** - Unblock user.\n\n**Usage:** `[prefix]unblock [user]`',
    'clone': '**Clone Profile** - Copy user profile details.\n\n**Usage:** `[prefix]clone [user]`',
    'revert': '**Revert Profile** - Restore original profile.\n\n**Usage:** `[prefix]revert`',
    'afk': '**AFK Status** - Set away-from-keyboard state.\n\n**Usage:** `[prefix]afk [reason]`',
    'calc': '**Calculator** - Calculate mathematical expression.\n\n**Usage:** `[prefix]calc <expr>`',
    'speedtest': '**Speedtest** - Test server speed.\n\n**Usage:** `[prefix]speedtest`',
    'addsudo': '**Add Sudo** - Grant sudo user access.\n\n**Usage:** `[prefix]addsudo [user]`',
    'delsudo': '**Remove Sudo** - Revoke sudo access.\n\n**Usage:** `[prefix]delsudo [user]`',
    'sudolist': '**Sudo List** - List authorized sudo users.\n\n**Usage:** `[prefix]sudolist`',
    'spam': '**Spam Text** - Send repeated text messages.\n\n**Usage:** `[prefix]spam <count> <text>`',
    'schedule': '**Schedule Msg** - Schedule message delivery.\n\n**Usage:** `[prefix]schedule <target> <time> <text>`',
    'react': '**Auto React** - Toggle auto reaction on messages.\n\n**Usage:** `[prefix]react`',
    'gcast': '**Broadcast** - Broadcast message to chats.\n\n**Usage:** `[prefix]gcast <text>`',
    'game': '**Game Toggle** - Toggle word chain autoplay.\n\n**Usage:** `[prefix]game`',
    'solver': '**Game Solver** - Solve word search puzzles.\n\n**Usage:** `[prefix]solver`',
    'wc': '**Word Chain** - Play word chain game.\n\n**Usage:** `[prefix]wc [word]`',
    'eval': '**Execute Code** - Evaluate Python expression.\n\n**Usage:** `[prefix]eval <code>`',
    'sh': '**Run Shell** - Execute bash command.\n\n**Usage:** `[prefix]sh <cmd>`',
    'plugins': '**List Plugins** - View loaded extra plugins.\n\n**Usage:** `[prefix]plugins`',
    'setalivetext': '**Set Alive Text** - Custom alive message.\n\n**Usage:** `[prefix]setalivetext <text>`',
    'setemoji': '**Set Emoji** - Custom alive emoji.\n\n**Usage:** `[prefix]setemoji <emoji>`',
    'resetallalive': '**Reset Alive** - Reset alive settings to default.\n\n**Usage:** `[prefix]resetallalive`',
    'banall': '**Ban All** - Ban all non-admin members in group.\n\n**Usage:** `[prefix]banall`',
    'unbanall': '**Unban All** - Unban all banned users in group.\n\n**Usage:** `[prefix]unbanall`',
    'inv': '**Invite User** - Invite user to current chat.\n\n**Usage:** `[prefix]inv [user]`',
    'invite2vc': '**Invite to VC** - Invite chat members to voice call.\n\n**Usage:** `[prefix]invite2vc`',
    'id': '**Get Chat ID** - Get ID of current chat or replied user.\n\n**Usage:** `[prefix]id [reply]`',
    'leave': '**Leave Group** - Leave current group chat.\n\n**Usage:** `[prefix]leave`',
    'song': '**Download Song** - Search and download audio track.\n\n**Usage:** `[prefix]song <query>`',
    'video': '**Download Video** - Search and download video track.\n\n**Usage:** `[prefix]video <query>`',
    'music': '**Music Help** - Show all voice chat music commands.\n\n**Usage:** `[prefix]music`',
    'imagine': '**AI Image** - Generate image using AI prompt.\n\n**Usage:** `[prefix]imagine <prompt>`',
    'packinfo': '**Pack Info** - View sticker pack information.\n\n**Usage:** `[prefix]packinfo [reply]`',
    'stickerinfo': '**Sticker Info** - Get details of a sticker.\n\n**Usage:** `[prefix]stickerinfo [reply]`',
    'purgeme': '**Purge Self** - Delete own recent messages.\n\n**Usage:** `[prefix]purgeme <count>`',
    'save': '**Save Media** - Save self-destructing media.\n\n**Usage:** `[prefix]save [reply]`',
    'bio': '**Update Bio** - Update Telegram bio text.\n\n**Usage:** `[prefix]bio <text>`',
    'pfp': '**Update PFP** - Set profile picture from photo.\n\n**Usage:** `[prefix]pfp [reply]`',
    'unafk': '**Remove AFK** - Remove away status.\n\n**Usage:** `[prefix]unafk`',
    'antispam': '**Antispam Toggle** - Toggle PM anti-spam / permit filter.\n\n**Usage:** `[prefix]antispam [on|off|status]`',
    'pmpermit': '**PM Permit** - Alias for antispam. Toggle PM protection.\n\n**Usage:** `[prefix]pmpermit [on|off|status]`',
    'pmguard': '**PM Guard** - Alias for antispam. Toggle PM protection.\n\n**Usage:** `[prefix]pmguard [on|off|status]`',
    'cas': '**CAS Check** - Check Combots Anti-Spam status.\n\n**Usage:** `[prefix]cas [user]`',
    'approve': '**Approve PM** - Approve user to DM.\n\n**Usage:** `[prefix]approve [user]`',
    'disapprove': '**Disapprove PM** - Disapprove user DM access.\n\n**Usage:** `[prefix]disapprove [user]`',
    'pingurl': '**Ping URL** - Test HTTP connection to URL.\n\n**Usage:** `[prefix]pingurl <url>`',
    'tcp': '**TCP Ping** - Ping host and port via TCP.\n\n**Usage:** `[prefix]tcp <host> <port>`',
    'speed': '**Speed Test** - Run server speedtest.\n\n**Usage:** `[prefix]speed`',
    'calculate': '**Calculate** - Math expression evaluation.\n\n**Usage:** `[prefix]calculate <expr>`',
    'dspam': '**Delay Spam** - Send delayed spam messages.\n\n**Usage:** `[prefix]dspam <count> <delay> <text>`',
    'cspam': '**Char Spam** - Send character-by-character spam.\n\n**Usage:** `[prefix]cspam <text>`',
    'dmspam': '**DM Spam** - Broadcast spam to DMs.\n\n**Usage:** `[prefix]dmspam <user> <count> <text>`',
    'schedules': '**List Scheduled** - List scheduled messages.\n\n**Usage:** `[prefix]schedules`',
    'setwelkm': '**Set Welcome** - Set custom welcome message.\n\n**Usage:** `[prefix]setwelkm <text>`',
    'resetwelkm': '**Reset Welcome** - Reset welcome settings.\n\n**Usage:** `[prefix]resetwelkm`',
    'autoreact': '**Auto React Toggle** - Toggle automatic reactions.\n\n**Usage:** `[prefix]autoreact`',
    'resetwords': '**Reset Used Words** - Reset word chain history.\n\n**Usage:** `[prefix]resetwords`',
    'grid': '**Word Grid** - Show or solve word grid puzzle.\n\n**Usage:** `[prefix]grid`',
    'solvegrid': '**Solve Grid** - Auto-solve word grid.\n\n**Usage:** `[prefix]solvegrid`',
    'wordseek': '**Word Seek** - Auto play word seek game.\n\n**Usage:** `[prefix]wordseek`',
    'gameinfo': '**Game Info** - Show active game stats.\n\n**Usage:** `[prefix]gameinfo`',
    'exec': '**Exec Command** - Run shell or code command.\n\n**Usage:** `[prefix]exec <cmd>`',
}

DEFAULT_CATEGORIES = {
    'ℹ️ INFO': ['alive', 'ping', 'stats', 'info', 'status', 'sessions', 'setalivetext', 'setemoji', 'resetallalive'],
    '🛡️ ADMIN': ['ban', 'unban', 'kick', 'mute', 'unmute', 'pin', 'unpin', 'promote', 'demote', 'tagall', 'power', 'banall', 'unbanall'],
    '👥 GROUPS': ['inv', 'invite2vc', 'id', 'leave'],
    '🎵 MUSIC': ['play', 'vplay', 'playforce', 'vplayforce', 'pause', 'resume', 'skip', 'end', 'loop', 'queue', 'song', 'video', 'music', 'vc1', 'vc0'],
    '🤖 AI CHAT': ['ask', 'ai', 'askclear', 'askmodel', 'imagine'],
    '🖼️ MEDIA': ['qt', 'kang', 'tiny', 'mmf', 'ocr', 'packinfo', 'stickerinfo'],
    '💬 CHAT': ['purge', 'purgeme', 'del', 'frwd', 'save', 'block', 'unblock'],
    '👤 PROFILE': ['clone', 'revert', 'bio', 'pfp', 'afk', 'unafk'],
    '🔐 SECURITY': ['addsudo', 'delsudo', 'sudolist', 'antispam', 'cas', 'approve', 'disapprove'],
    '🌐 NETWORK': ['pingurl', 'tcp', 'speed', 'speedtest', 'calc', 'calculate'],
    '⚡ SPAM': ['spam', 'dspam', 'cspam', 'dmspam', 'gcast', 'schedule', 'schedules'],
    '👋 WELCOME': ['setwelkm', 'resetwelkm', 'react', 'autoreact'],
    '🎮 GAMES': ['game', 'solver', 'wc', 'resetwords', 'grid', 'solvegrid', 'wordseek', 'gameinfo'],
    '💻 DEVELOPER': ['eval', 'sh', 'exec', 'plugins', 'update'],
}

commands = dict(DEFAULT_COMMANDS)
categories = dict(DEFAULT_CATEGORIES)
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


def cmd_text(message) -> str:
    """The text a command was typed in, whether that was a message or a caption.

    kurigram's ``filters.command`` matches on ``message.text or message.caption``,
    so every command handler also fires for a photo/video whose *caption* is the
    command. Handlers that then reached for ``message.text.split()`` crashed with
    "'NoneType' object has no attribute 'split'" -- and because ``retry()``
    re-raises anything that is not a FloodWait or OSError, the traceback went to
    the log and the user saw no reply at all.

    Always returns a string, so ``.split()`` on the result is safe.
    """
    return message.text or message.caption or ""


def get_text(message: Message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = cmd_text(message)
    if not text_to_return:
        return None
    if " " in text_to_return:
        try:
            return text_to_return.split(None, 1)[1]
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
    args = cmd_text(message).strip().split()
    text = cmd_text(message)
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
    # (connect, read) timeouts. This is a synchronous request inside an async
    # function, so it blocks the whole event loop while it waits: without a
    # timeout a host that accepts the connection and then goes quiet freezes
    # every handler until the process is restarted by hand. The read timeout
    # applies per chunk, not to the total transfer, so large files are fine.
    response = requests.get(url, stream=True, timeout=(10, 60))
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
                    logger.info(f"Retry {retries}/{max_retries} for {func.__name__} after {wait}s")
                    await asyncio.sleep(wait)
                    delay *= backoff
                except Exception as e:
                    logger.error(f"Unexpected error in {func.__name__}: {str(e)}")
                    raise
            return await func(*args, **kwargs)
        return wrapper
    return decorator

# File and media utilities
def rename_file(old_name, new_name):
    try:
        os.replace(old_name, new_name)
        new_file_path = os.path.abspath(new_name)
        logger.info(f'File renamed from {old_name} to {new_name}')
        return new_file_path
    except FileNotFoundError:
        logger.warning(f'The file {old_name} does not exist.')
        return old_name if os.path.exists(old_name) else (new_name if os.path.exists(new_name) else None)
    except Exception as e:
        logger.warning(f'File rename failed: {e}')
        return old_name if os.path.exists(old_name) else None

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
    logger.debug(f"video duration: {int(duration)}s")
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


def unset_user_data(user_id, key):
    """Remove a single key from a user's session document."""
    user_sessions.update_one({"user_id": user_id}, {"$unset": {key: ""}}, upsert=True)
    invalidate_session_cache(user_id)


async def delete_if_self(message):
    """Delete the message only if it was sent by the account itself."""
    if message.from_user and message.from_user.is_self:
        with contextlib.suppress(Exception):
            await message.delete()

# Message formatting utilities
WELCOME_PLACEHOLDERS = ("{name}", "{full_name}", "{id}", "{yourname}", "{botname}")


async def format_welcome_message(client, text, chat_id, user_or_chat_name, full_name=None):
    """Substitute the greeting placeholders with real data.

    Kept in one place because ``setwelkm`` validates templates against
    ``WELCOME_PLACEHOLDERS`` and this is what has to honour them. ``{botname}``
    used to be advertised by the validator but implemented nowhere, so it
    rendered literally, while ``{full_name}`` -- which the greeting path did
    substitute -- was rejected as invalid.
    """
    try:
        # Escaped: the name comes from whoever messaged us, and the template is
        # sent with HTML parse mode.
        owner = html_esc(client.me.first_name)
        formatted_text = text.replace("{name}", html_esc(user_or_chat_name))
        formatted_text = formatted_text.replace(
            "{full_name}", html_esc(full_name if full_name is not None else user_or_chat_name)
        )
        formatted_text = formatted_text.replace("{id}", str(chat_id))
        formatted_text = formatted_text.replace("{yourname}", owner)
        formatted_text = formatted_text.replace("{botname}", owner)
        return formatted_text
    except Exception as e:
        logging.error(f"Error formatting welcome message: {str(e)}")
        return text

# Font formatting utility
def bold_cool(text):
    return text

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
    def filter_func(_, client, message):
        user_data = cached_get_user_data(client.me.id)
        spam_control = user_data.get('Spam_control', True)
        if isinstance(spam_control, str):
            spam_control = spam_control.lower() not in ('false', '0', 'off', 'disable', 'disabled')
        if not spam_control:
            return False
        white_listed = user_data.get('white_listed', [])
        if not message.from_user:
            return False
        sender_id = message.from_user.id
        if sender_id in white_listed:
            return False
        return True
    return filters.create(filter_func)

# File upload utilities
_GOFILE_SERVERS_URL = "https://api.gofile.io/servers"


def _gofile_pick_server():
    """Ask gofile.io which upload server to use. Blocking -- call in a thread.

    This used https://api.gofile.io/servers' predecessor, /getServer, which no
    longer exists: it answers 404 with the JSON string "error-notFound", so
    data["data"]["server"] raised TypeError and every oversized upload died
    before a byte moved. /servers returns data.servers as a list of
    {name, zone}; any of them will take the file.
    """
    response = requests.get(_GOFILE_SERVERS_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    servers = (payload.get("data") or {}).get("servers") or []
    for entry in servers:
        if isinstance(entry, dict) and entry.get("name"):
            return entry["name"]
    return None


async def big_file(msg, sender, zip_filename):
    """Hand a file too large for Telegram to gofile.io and report the link."""
    try:
        # In a thread: requests is synchronous, and this used to block the whole
        # event loop on a third-party host.
        server = await asyncio.to_thread(_gofile_pick_server)
    except Exception as e:
        logger.warning(f"gofile server lookup failed: {e}")
        return await bot.edit_message(msg, f"Could not reach gofile.io: {html_esc(e)}")

    if not server:
        return await bot.edit_message(msg, "No storage available in gofile.io please try again later:")

    logger.debug(f"gofile server: {server}")
    await bot.edit_message(msg, 'File size is greater than 2GB\nUploading file to gofile.io server...')

    transfer_url = f"https://{server}.gofile.io/uploadFile"
    command = ["curl", "-F", f"file=@{zip_filename}", transfer_url]
    logger.debug(f"upload command: {command}")
    start_time = time.time()

    try:
        # asyncio, not subprocess.Popen: the old code read the pipe with a
        # blocking loop, so the entire userbot was frozen for the length of a
        # multi-gigabyte upload, and it never called wait() or closed the pipe,
        # leaving a defunct curl and a leaked descriptor behind every time.
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except OSError as e:
        # The old handler caught subprocess.CalledProcessError, which Popen
        # never raises, so a missing curl went out as an unhandled exception.
        logger.error(f"gofile upload could not start: {e}")
        return await bot.edit_message(msg, f"Upload failed to start: {html_esc(e)}")

    display_name = html_esc(os.path.basename(zip_filename))
    recent = []
    edit = 0
    buffer = b""
    try:
        while True:
            chunk = await process.stdout.read(512)
            if not chunk:
                break
            # curl separates progress updates with \r, not \n. The old code got
            # away with readline() only because it opened the pipe in text mode,
            # where universal newlines translate \r for you; asyncio streams
            # split on \n alone, so do the translation here or lose every
            # progress update.
            buffer = (buffer + chunk).replace(b"\r", b"\n")
            *complete, buffer = buffer.split(b"\n")
            for raw in complete:
                line = raw.decode("utf-8", "replace").strip()
                if not line:
                    continue
                logger.debug(line)
                recent.append(line)
                # Bounded: a long upload emits thousands of progress lines, and
                # only the tail holds the response we need.
                del recent[:-20]

                if edit % 5 == 0:
                    parts = line.split()
                    if len(parts) > 10:
                        total = re.sub("[^0-9]", "", parts[1])
                        current = re.sub("[^0-9]", "", parts[5])
                        if total.isdigit() and current.isdigit():
                            total = int(total)
                            current = int(current)
                            if current != 0 and total != 0:
                                progress_percent = current * 100 / total
                                progress_message = f"Uploading {display_name}: {progress_percent:.2f}%\n\n"

                                elapsed_time = time.time() - start_time
                                speed = current / (elapsed_time * 10) if elapsed_time else 0
                                progress_message += f"Speed: {speed:.2f} MB/s\n"

                                time_left = (total - current) / (speed * 10) if speed else 0
                                progress_message += f"Time left: {time_left:.2f} seconds\n"
                                progress_message += f"Size: {current:.2f} MB / {total:.2f} MB"

                                progress_bar_length = int(progress_percent / 5)
                                progress_bar_text = "█" * progress_bar_length + "░" * (20 - progress_bar_length)
                                progress_message += f"\n[{progress_bar_text}]"

                                try:
                                    if random.choices([True, False], weights=[1, 99])[0]:
                                        await bot.edit_message(msg, progress_message, parse_mode='html')
                                except Exception as e:
                                    logger.warning(f"progress edit failed: {e}")

                edit += 1
    finally:
        # Always reap, even if the loop above raised or the task was cancelled.
        if process.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                process.kill()
        returncode = await process.wait()

    tail = buffer.decode("utf-8", "replace").strip()
    if tail:
        recent.append(tail)
    combined = "\n".join(recent)

    start_index = combined.find("https://gofile.io")
    if start_index == -1:
        # No link in the output: curl failed, or gofile changed the upload
        # endpoint under us. Either way, say so instead of sending a message
        # with a mangled slice of an error page in it.
        logger.error(f"gofile upload produced no link (curl exit {returncode}): {combined[-500:]}")
        return await bot.edit_message(
            msg, f"Upload to gofile.io failed (curl exit {returncode})."
        )

    end_index = combined.find('"', start_index)
    link = combined[start_index:end_index] if end_index != -1 else combined[start_index:].split()[0]

    try:
        await bot.send_message(sender, f"Not able to upload files more than 500MB here.\nDownload link: {link}")
    except Exception as e:
        logger.warning(f"Error sending link: {link}, Error: {e}")
    return link


def get_arg(message: Message):
    msg = message.text
    msg = msg.replace(" ", "", 1) if msg[1] == " " else msg
    split = msg[1:].replace("\n", " \n").split(" ")
    if " ".join(split[1:]).strip() == "":
        return ""
    return " ".join(split[1:])


def get_args(message: Message):
    try:
        message = cmd_text(message)
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
    body = cmd_text(message)
    if not body:
        return []
    first_char = body[0]
    if first_char not in HARDCODED_PREFIXES:
        return []
    text = body[1:]
    parts = text.split()
    if len(parts) <= 1:
        return []
    return parts[1:]


def get_command_from_caret(message):
    """Extract command name from prefixed commands."""
    body = cmd_text(message)
    if not body:
        return ""
    first_char = body[0]
    if first_char not in HARDCODED_PREFIXES:
        return ""
    text = body[1:]
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


def scratch_name(suffix: str) -> str:
    """A unique working-file name for media conversions.

    These helpers used to write to fixed names like "sticker.png". Two people
    running a sticker command at the same time then shared one file on disk,
    and whichever conversion finished second decided what *both* of them got
    sent -- so one user could receive the other's media. Stay in the current
    directory, as before, so relative paths and caller cleanup are unaffected;
    only the name changes.
    """
    return f"nub_scratch_{os.getpid()}_{time.time_ns()}{suffix}"


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
            final_path = scratch_name(".png")
            path_s = await message.reply_to_message.download()
            im = Image.open(path_s)
            im.save(final_path, "PNG")
        else:
            path_s = await client.download_media(message.reply_to_message)
            final_path = scratch_name(".png")
            # Quote the paths: run_cmd shlex.splits the string, so a downloaded
            # name containing a space would otherwise arrive as two argv items.
            cmd = (
                "lottie_convert.py --frame 0 -if lottie -of png "
                f"{shlex.quote(path_s)} {shlex.quote(final_path)}"
            )
            await run_cmd(cmd)
    elif message.reply_to_message.audio:
        thumb = message.reply_to_message.audio.thumbs[0].file_id
        final_path = await client.download_media(thumb)
    elif message.reply_to_message.video or message.reply_to_message.animation:
        final_path = scratch_name(".png")
        vid_path = await client.download_media(message.reply_to_message)
        await run_cmd(
            f"ffmpeg -i {shlex.quote(vid_path)} -filter:v scale=500:500 -an "
            f"{shlex.quote(final_path)}"
        )
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
    file_name = scratch_name(".png")
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
        cmd = f"ffmpeg -i {shlex.quote(media)} {cmd_f} -ss 00:00:00 -to 00:00:03 -an -c:v libvpx-vp9 {fps_cmd}-fs 256K {shlex.quote(resized_video)}"
        _, error, __, ___ = await run_cmd(cmd)
        os.remove(media)
        return resized_video

    image = Image.open(media)
    maxsize = 512
    scale = maxsize / max(image.width, image.height)
    new_size = (int(image.width * scale), int(image.height * scale))

    image = image.resize(new_size, Image.LANCZOS)
    resized_photo = scratch_name(".png")
    image.save(resized_photo)
    os.remove(media)
    return resized_photo


# ══════════════════════ VOICE CALL PLAYBACK RUNTIME ══════════════════════
# The shared half of the music feature, split the way the upstream deployer
# splits it: state in config, runtime here, commands in userbot/music.py.
#
# It lives in tools rather than in the plugin because main.py has to wire the
# call client at startup and must not import from userbot/ to do it: those
# modules are loaded by pyrogram's own plugin loader, and importing one directly
# would load it a second time under a different module name, giving the plugin
# two copies of every module-level dict -- one holding the handlers pyrogram
# dispatches to, the other holding the queue main.py seeded.
#
#   config.queues   {f"dic_{owner_id}": {chat_id: [song, ...]}}  what is waiting
#   config.playing  {chat_id: song}                              what is on air
#
# A "song" is the dict built by put_queue() in userbot/music.py. `playing` holds
# a *copy* of it: the .loop command re-queues the playing song, and several
# handlers call playing[chat].clear(), which would otherwise empty the queued
# entries too.

# Style 11 is the plain one; it is what the queue message has always asked for.
DEFAULT_STYLE = 11
QUEUE_FALLBACK = (
    "➕ **Added to queue**\n┃ **Mode:** {}\n┃ **Title:** {}\n"
    "┃ **Duration:** {}\n╰▸ **Position:** #{}"
)
PLAY_FALLBACK = (
    "🎧 **Now Playing**\n┃ **Mode:** {}\n┃ **Title:** {}\n"
    "┃ **Duration:** {}\n╰▸ **Requested by:** {}"
)
_STYLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def _load_styles(filename: str, fallback: str) -> Dict[int, str]:
    """Load the numbered message templates from data/, keyed by int.

    The JSON keys are strings but every call site indexes with an int. Templates
    with the wrong number of {} slots are dropped rather than allowed to raise
    IndexError mid-playback, and DEFAULT_STYLE is always present so indexing it
    cannot fail even with the file missing or corrupt.
    """
    styles: Dict[int, str] = {}
    path = os.path.join(_STYLE_DIR, filename)
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


queue_styles = _load_styles("queue_styles.json", QUEUE_FALLBACK)
play_styles = _load_styles("play_styles.json", PLAY_FALLBACK)

# One lock per chat, plus the time its last advance finished. A video track ends
# its audio and its video stream separately -- StreamEnded carries a stream_type
# saying which -- and py-tgcalls hands every end event to the loop as its own
# task (run_coroutine_threadsafe, from the ntgcalls thread), so the pair arrives
# as two concurrent handler calls that must not each pull a song off the queue.
_advance_locks: Dict[int, asyncio.Lock] = {}
_last_advance: Dict[int, float] = {}
# The two end events of one track arrive within milliseconds of each other, so
# this window is what separates them from a genuine end of the *next* track. A
# track shorter than the window would have its own end event read as the
# duplicate and playback would sit there until the next command; nothing a queue
# plays is that short.
DUPLICATE_END_WINDOW = 2.0


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


def no_call_client_card():
    """Shown when songs_client is empty: main.py could not start the call client."""
    return Msg.card(
        "Voice Calls Unavailable",
        ["The voice call client is not running."],
        emoji=Msg.EMOJI_ERROR,
        footer="Check the startup log and restart",
    )


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

    Downloads used to accumulate under user_<id>/<chat_id>/ forever: nothing
    ever removed them. `keep` is the remaining queue, because .loop re-queues
    the same dict and would otherwise be left pointing at a file we just
    deleted.
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


async def drop_chat(client, chat_id):
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
        await drop_chat(client, chat_id)
        return False

    # Read the call client main.py started; never build one here. If it is
    # missing, startup failed and there is nothing to stream through.
    call_py = songs_client.get(client.me.id)
    if call_py is None:
        logger.error("[MUSIC] No call client for %s; startup must have failed", client.me.id)
        await _say(message, client, chat_id, no_call_client_card())
        await drop_chat(client, chat_id)
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
        await drop_chat(client, chat_id)
        return False
    except Exception as e:
        logger.error(f"[MUSIC] play() failed in {chat_id}: {e}")
        await _say(message, client, chat_id, styled_error("Could not start the stream", details=str(e)))
        await drop_chat(client, chat_id)
        return False

    await add_active_chat(client, chat_id)
    template = play_styles.get(DEFAULT_STYLE, PLAY_FALLBACK)
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

    # The call client belongs to main.py, which starts it alongside the pyrogram
    # client. Nothing to advance into if it never came up.
    call_py = songs_client.get(client.me.id)
    if call_py is None:
        logger.error("[MUSIC] No call client for %s; startup must have failed", client.me.id)
        await _say(update, client, chat_id, no_call_client_card())
        await drop_chat(client, chat_id)
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
        await drop_chat(client, chat_id)


# The two call-client callbacks main.py registers with add_handler. py-tgcalls
# invokes a handler as (call_py, update), and PyTgCalls exposes the pyrogram
# client it was built around as `mtproto_client`, so nothing has to be bound in
# for these to reach the account they belong to.
async def stream_end_handler(call_py, update: StreamEnded):
    """A track finished: play the next one in this chat, or leave the call."""
    client = call_py.mtproto_client
    chat_id = update.chat_id
    lock = _advance_locks.setdefault(chat_id, asyncio.Lock())
    async with lock:
        loop = asyncio.get_running_loop()
        last = _last_advance.get(chat_id)
        if last is not None and loop.time() - last < DUPLICATE_END_WINDOW:
            logger.debug(f"[MUSIC] Ignoring the {update.stream_type} end in {chat_id}: already advanced")
            return
        logger.info(f"[MUSIC] Stream ended in {chat_id} ({update.stream_type}); advancing queue")
        try:
            await dend(client, None, channel_id=chat_id)
        finally:
            # Stamped on the way out, not on the way in: the second event sits on
            # the lock for as long as play() takes to join the call, and against
            # a start time a slow join would look like a genuine next-track end.
            _last_advance[chat_id] = loop.time()


async def call_gone_handler(call_py, update: ChatUpdate):
    """The voice chat closed, or we were kicked or removed: forget the chat.

    Without this, is_active_chat keeps claiming we are streaming and every later
    command talks to a call that no longer exists.
    """
    client = call_py.mtproto_client
    chat_id = update.chat_id
    logger.info(f"[MUSIC] Call in {chat_id} ended externally ({update.status})")
    await remove_active_chat(client, chat_id)
    song_queue = queues.get(f"dic_{client.me.id}") or {}
    leftovers = song_queue.pop(chat_id, [])
    playing.pop(chat_id, None)
    for song in leftovers:
        _cleanup_song_file(song, [])


# The filter each callback is registered with, kept next to the callbacks so
# main.py does not have to know which updates the queue cares about.
STREAM_END_FILTER = call_filters.stream_end()
CALL_GONE_FILTER = call_filters.chat_update(
    ChatUpdate.Status.CLOSED_VOICE_CHAT
    | ChatUpdate.Status.KICKED
    | ChatUpdate.Status.LEFT_GROUP
)
