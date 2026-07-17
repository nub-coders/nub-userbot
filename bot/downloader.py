"""
Bot-side URL / media downloader (the `app` bot client, not the userbot).

DM the bot a link and it saves the media back to you:
  • t.me message/story links  → fetched via your userbot (clients[you]); if the
    source forbids forwarding, it downloads and re-uploads instead.
  • plain HTTP/HTTPS links     → downloaded and sent as a document.
  • a chat id / @username      → offers a batch download of the last N messages.

Adapted from the multi-tenant deployer for this self-hosted single-session
build: the deployer's premium gating and /login multi-tenant fallbacks are
dropped — the userbot is either connected (clients[sender]) or it isn't.
"""
import os
import time
import random
import shutil
import asyncio
import logging
from urllib.parse import urlparse

import requests
from pyrogram import Client, filters
from pyrogram.enums import MessageEntityType
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from pyrogram.errors import FloodWait, ChatForwardsRestricted, FileReferenceExpired, MessageIdInvalid
try:
    from pyrogram.errors import PremiumAccountRequired
except ImportError:  # older pyrogram/kurigram builds
    PremiumAccountRequired = ()
from convopyro import listen_message

from config import *
from tools import *
from utils.message import Msg

logger = logging.getLogger("userbot")

# Per-sender pending batch-download context set up before the count buttons.
_batch_downloads = {}

_PHOTO_EXT = ('jpg', 'jpeg', 'png', 'gif')
_AUDIO_EXT = ('mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a')
_VIDEO_EXT = ('mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv')
_SIZE_LIMIT = 2_000_000_000  # 2 GB; larger files go to gofile via big_file()


def _user_dir(sender):
    d = f"{ggg}/user_{sender}"
    os.makedirs(d, exist_ok=True)
    return d


def _make_progress(msg, label="Downloading"):
    """Build a throttled pyrogram progress callback that edits `msg`."""
    timer = Timer()

    async def progress_bar(current, total, start_time=time.time()):
        if timer.can_send() and total:
            pct = current * 100 / total
            ticks = int(pct / 5)
            bar = '█' * ticks + '░' * (20 - ticks)
            elapsed = time.time() - start_time
            speed = current / (elapsed * 1024 * 1024) if elapsed else 0
            left = (total - current) / (speed * 1024 * 1024) if speed else 0
            text = (
                f"{label}: {pct:.2f}%\n"
                f"Speed: {speed:.2f} MB/s\n"
                f"Time left: {left:.2f}s\n"
                f"Size: {current / 1024 / 1024:.2f} MB / {total / 1024 / 1024:.2f} MB\n"
                f"[{bar}]"
            )
            try:
                if random.choices([True, False], weights=[1, 99])[0]:
                    await msg.edit_text(text)
            except Exception as e:
                logger.debug(f"[DOWNLOAD] progress edit error: {e}")

    return progress_bar


async def _send_file(sender, file_path, caption="", progress=None):
    """Upload a downloaded file to `sender`, picking the right send_* by extension.
    Files over the size limit are offloaded to gofile via big_file()."""
    ext = file_path.rsplit('.', 1)[-1].lower() if '.' in file_path else ''
    if os.path.getsize(file_path) > _SIZE_LIMIT:
        holder = await app.send_message(sender, "Uploading large file...")
        return await big_file(holder, sender, file_path)
    if ext in _PHOTO_EXT:
        await app.send_photo(sender, file_path, caption=caption, progress=progress)
    elif ext in _AUDIO_EXT:
        await app.send_audio(sender, file_path, caption=caption, progress=progress)
    elif ext in _VIDEO_EXT:
        thumb = f"{file_path}_thumb.jpg"
        try:
            generate_thumbnail(file_path, thumb)
            duration = with_opencv(file_path)
            await app.send_video(sender, file_path, caption=caption, progress=progress, duration=duration, thumb=thumb)
        finally:
            if os.path.exists(thumb):
                os.remove(thumb)
    else:
        await app.send_document(sender, file_path, caption=caption, progress=progress)


def _get_file_name_from_url(url):
    try:
        resp = requests.head(url, allow_redirects=True, timeout=10)
        cd = resp.headers.get('Content-Disposition')
        if cd and 'filename=' in cd:
            return cd.split('filename=')[-1].strip('"')
    except Exception:
        pass
    return url.split('/')[-1].split('?')[0] or 'downloaded_file'


# ─────────────────────────── t.me link parsing ─────────────────────────────
def _parse_tme_link(url):
    """Parse a t.me URL into (chat_id, message_id, is_story) or None if unsupported."""
    parts = urlparse(url).path.strip('/').split('/')
    if len(parts) == 3 and parts[0] == 'c':
        # https://t.me/c/<internal_id>/<msg>  → private channel/supergroup
        cid = parts[1]
        chat_id = int(cid if cid.startswith('-100') else f"-100{cid}")
        return chat_id, int(parts[2]), False
    if len(parts) == 3 and parts[1] == 's':
        # https://t.me/<user>/s/<story>  → story
        return parts[0], int(parts[2]), True
    if len(parts) == 2:
        # https://t.me/<user>/<msg>
        return parts[0], int(parts[1]), False
    if len(parts) == 3:
        # https://t.me/<user>/<thread>/<msg>
        return parts[0], int(parts[2]), False
    return None


async def _download_tme(message, sender, chat_id, message_id, is_story):
    """Copy a t.me message to the sender; on forward restriction, download & re-upload."""
    userbot = clients.get(sender)
    if not userbot:
        return await message.reply(
            f"{Msg.EMOJI_WARNING} That link points to a chat only your userbot can reach, "
            f"but the userbot isn't connected. Use /restart to bring it back online."
        )
    try:
        src = (
            await userbot.get_stories(chat_id, message_id)
            if is_story
            else await userbot.get_messages(chat_id, message_id)
        )
        await src.copy(sender)
    except (ChatForwardsRestricted, FileReferenceExpired, MessageIdInvalid, *(
        (PremiumAccountRequired,) if PremiumAccountRequired else ()
    )):
        if not src.media:
            return await app.send_message(sender, src.text or "(no content)")
        msg = await app.send_message(sender, f"{Msg.EMOJI_DOWNLOAD} Downloading...")
        progress = _make_progress(msg, "Downloading")
        file_path = await src.download(f"{_user_dir(sender)}/", progress=progress)
        try:
            await _send_file(sender, file_path, caption=src.caption or "", progress=_make_progress(msg, "Uploading"))
        finally:
            await msg.delete()
            if os.path.exists(file_path):
                os.remove(file_path)
    except Exception as e:
        await message.reply(f"{Msg.EMOJI_ERROR} Error getting message: {e}")


async def _download_http(message, sender, url):
    """Download a plain HTTP/HTTPS URL and send it back as a file."""
    user_dir = _user_dir(sender)
    filename = _get_file_name_from_url(url)
    dest = f"{user_dir}/{filename}"
    msg = await app.send_message(sender, f"{Msg.EMOJI_DOWNLOAD} Downloading...")
    try:
        dest = await download_file(url, dest, _make_progress(msg, "Downloading"))
        await _send_file(sender, dest, progress=_make_progress(msg, "Uploading"))
        await msg.delete()
    except Exception as e:
        await message.reply(f"{Msg.EMOJI_ERROR} Error getting file: {e}")
    finally:
        if os.path.exists(dest):
            os.remove(dest)


# ─────────────────────────── the URL entry point ───────────────────────────
def _url_filter(_, __, message: Message):
    """Private, non-command text/media messages that carry a URL entity or look
    like a bare chat id / @username. Commands (/start, /ping, ...) are excluded."""
    if not message.from_user or (message.text and message.text.startswith('/')):
        return False
    if message.from_user.id in conversations:
        return False
    text = (message.text or "").strip()
    entities = message.entities or []
    has_url = any(e.type == MessageEntityType.URL for e in entities)
    if has_url:
        return True
    # bare @username or chat id (but not a phone number)
    if text.startswith('@'):
        return True
    if text.startswith('-') and text[1:].isdigit():
        return True
    if text.isdigit() and int(text) < 10_000_000_000:
        return True
    return False


@Client.on_message(filters.private & filters.incoming & filters.create(_url_filter))
async def handle_url(client, message: Message):
    sender = message.from_user.id
    text = (message.text or "").strip()
    entities = message.entities or []

    # Bare chat id / username → batch download flow
    if not any(e.type == MessageEntityType.URL for e in entities) and not text.startswith('http'):
        return await _start_batch_download(message, sender, text)

    # Handle each URL entity in the message
    for entity in entities:
        if entity.type != MessageEntityType.URL:
            continue
        url = text[entity.offset:entity.offset + entity.length]
        parsed = _parse_tme_link(url) if "t.me" in url else None
        if parsed:
            await _download_tme(message, sender, *parsed)
        else:
            await _download_http(message, sender, url)


# ─────────────────────────── batch download ────────────────────────────────
async def _start_batch_download(message, sender, chat_identifier):
    userbot = clients.get(sender)
    if not userbot:
        return await message.reply(
            f"{Msg.EMOJI_WARNING} Your userbot isn't connected, so I can't read that chat. "
            f"Use /restart to bring it back online."
        )
    try:
        if str(chat_identifier).lstrip('-').isdigit():
            cid = int(chat_identifier)
            if cid > 0 and not str(cid).startswith('-100'):
                try:
                    chat = await userbot.get_chat(int(f"-100{cid}"))
                except Exception:
                    chat = await userbot.get_chat(cid)
            else:
                chat = await userbot.get_chat(cid)
        else:
            chat = await userbot.get_chat(chat_identifier)
    except Exception as e:
        return await message.reply(
            f"{Msg.EMOJI_ERROR} Cannot access chat: {e}\n\n"
            "<b>Provide one of:</b>\n"
            "• @username\n• chat id (e.g. -1001234567890)\n• user id\n\n"
            "<b>Note:</b> you must be a member of the chat.",
            parse_mode=ParseMode.HTML,
        )

    _batch_downloads[sender] = chat.id
    buttons = InlineKeyboardMarkup([
        [InlineKeyboardButton("📥 Last 10", callback_data="batch_10"),
         InlineKeyboardButton("📥 Last 25", callback_data="batch_25")],
        [InlineKeyboardButton("📥 Last 50", callback_data="batch_50"),
         InlineKeyboardButton("📥 Last 100", callback_data="batch_100")],
        [InlineKeyboardButton("📝 Custom Range", callback_data="batch_custom")],
        [InlineKeyboardButton("❌ Cancel", callback_data="batch_cancel")],
    ])
    title = getattr(chat, 'title', None) or getattr(chat, 'first_name', 'Chat')
    await message.reply(
        f"{Msg.EMOJI_FOLDER} <b>Chat:</b> {title}\n"
        f"🆔 <b>ID:</b> <code>{chat.id}</code>\n\n"
        "Select how many messages to download:",
        reply_markup=buttons,
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r"^batch_"))
async def batch_download_callback(client, callback_query: CallbackQuery):
    sender = callback_query.from_user.id
    action = callback_query.data.split('_', 1)[1]

    if action == 'cancel':
        _batch_downloads.pop(sender, None)
        return await callback_query.edit_message_text(f"{Msg.EMOJI_ERROR} Batch download cancelled.")

    if sender not in _batch_downloads:
        return await callback_query.answer(f"{Msg.EMOJI_WARNING} Session expired. Please try again.", show_alert=True)

    chat_id = _batch_downloads[sender]
    userbot = clients.get(sender)
    if not userbot:
        _batch_downloads.pop(sender, None)
        return await callback_query.edit_message_text(f"{Msg.EMOJI_WARNING} Userbot not connected. Use /restart.")

    try:
        if action == 'custom':
            await callback_query.edit_message_text(
                f"{Msg.EMOJI_NOTE} <b>Custom Range Mode</b>\n\n"
                "Send message IDs as:\n"
                "• Single: <code>12345</code>\n"
                "• Range: <code>100:150</code>\n"
                "• Multiple: <code>100,105,110</code>\n\n"
                "You have 60 seconds to respond.",
                parse_mode=ParseMode.HTML,
            )
            conversations[sender] = True
            try:
                response = await listen_message(client, sender, timeout=60)
            finally:
                conversations.pop(sender, None)
            if response is None:
                return await app.send_message(sender, f"{Msg.EMOJI_LOADING} Timeout. Please try again.")
            raw = (response.text or "").strip()
            if raw.startswith('/'):
                return await app.send_message(sender, f"{Msg.EMOJI_ERROR} Cancelled.")
            try:
                message_ids = _parse_message_ids(raw)
            except ValueError as e:
                return await app.send_message(sender, f"{Msg.EMOJI_ERROR} {e}")
            await _download_messages_batch(userbot, sender, chat_id, message_ids=message_ids)
        else:
            count = int(action)
            await callback_query.edit_message_text(f"{Msg.EMOJI_DOWNLOAD} Downloading last {count} messages...")
            await _download_messages_batch(userbot, sender, chat_id, count=count)
    except Exception as e:
        await callback_query.edit_message_text(f"{Msg.EMOJI_ERROR} Error: {e}")
    finally:
        _batch_downloads.pop(sender, None)


def _parse_message_ids(raw):
    """Parse a custom-range string into a list of message ids. Raises ValueError on bad input."""
    if ':' in raw:
        try:
            start, end = map(int, raw.split(':'))
        except Exception:
            raise ValueError("Invalid range format. Use start:end")
        if start > end:
            start, end = end, start
        return list(range(start, end + 1))
    if ',' in raw:
        try:
            return [int(x.strip()) for x in raw.split(',')]
        except Exception:
            raise ValueError("Invalid format. Use comma-separated numbers.")
    try:
        return [int(raw)]
    except Exception:
        raise ValueError("Invalid message ID.")


async def _download_messages_batch(userbot, sender, chat_id, message_ids=None, count=None):
    """Download multiple messages from a chat via the userbot, with flood control."""
    user_dir = _user_dir(sender)
    status = await app.send_message(sender, f"{Msg.EMOJI_LOADING} Starting batch download...")

    messages = []
    if message_ids:
        for i in range(0, len(message_ids), 100):
            chunk = message_ids[i:i + 100]
            try:
                msgs = await userbot.get_messages(chat_id, chunk)
                messages.extend(m for m in (msgs if isinstance(msgs, list) else [msgs]) if m)
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"[BATCH] chunk fetch error: {e}")
                await asyncio.sleep(2)
    else:
        async for m in userbot.get_chat_history(chat_id, limit=count):
            messages.append(m)

    if not messages:
        return await status.edit_text(f"{Msg.EMOJI_ERROR} No messages found.")

    await status.edit_text(f"{Msg.EMOJI_FOLDER} Found {len(messages)} messages. Processing...")

    success = failed = 0
    for idx, m in enumerate(messages, 1):
        try:
            if idx % 10 == 0:
                await status.edit_text(
                    f"{Msg.EMOJI_DOWNLOAD} Progress: {idx}/{len(messages)}\n"
                    f"{Msg.EMOJI_SUCCESS} Success: {success} | {Msg.EMOJI_ERROR} Failed: {failed}"
                )
            if m.media:
                file_path = await m.download(f"{user_dir}/")
                try:
                    await _send_file(sender, file_path, caption=m.caption or "")
                    success += 1
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
            elif m.text:
                await app.send_message(sender, m.text)
                success += 1
            await asyncio.sleep(1)  # flood control between messages
        except FloodWait as e:
            await status.edit_text(f"{Msg.EMOJI_LOADING} Flood wait: {e.value}s. Pausing...")
            await asyncio.sleep(e.value)
        except Exception as e:
            logger.error(f"[BATCH] message {idx} error: {e}")
            failed += 1
            await asyncio.sleep(1)

    await status.edit_text(
        f"{Msg.EMOJI_SUCCESS} <b>Batch Download Complete!</b>\n\n"
        f"• Total: {len(messages)}\n• Success: {success}\n• Failed: {failed}",
        parse_mode=ParseMode.HTML,
    )
    shutil.rmtree(user_dir, ignore_errors=True)
