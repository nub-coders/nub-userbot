from collections import OrderedDict
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import *
from tools import *

# ponytail: bounded in-memory cache. Telegram's delete update for private chats
# carries only message IDs (no chat, no content), so we must remember incoming
# messages ourselves to log what was deleted/edited. Private msg IDs are unique
# per account, so keying by message.id alone is safe.
# Cap at 2000; oldest evicted. Lost on restart — fine, this is a convenience log.
_CACHE = OrderedDict()
_CACHE_MAX = 2000

_MEDIA_ATTRS = ("photo", "video", "audio", "voice", "video_note", "animation", "document", "sticker")


def _media_of(message):
    for attr in _MEDIA_ATTRS:
        obj = getattr(message, attr, None)
        if obj:
            return attr, getattr(obj, "file_id", None)
    return None, None


def _remember(message):
    m_type, file_id = _media_of(message)
    _CACHE[message.id] = {
        "text": message.text or message.caption or "",
        "media_type": m_type,
        "file_id": file_id,
        "user": message.from_user,
    }
    if len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)


def _who(user):
    """Identity line for a log entry, as HTML.

    This used to build a markdown link, `[{name}](tg://user?id={id})`. A display
    name is the user's own text, and these entries describe people who are
    already trying something: a name containing "](https://elsewhere)" rewrote
    the link, and a name containing a tag was deleted outright by the HTML half
    of the default parse mode. Escaped, in an anchor, it cannot do either.
    """
    if not user:
        return "unknown"
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    uname = f" (@{user.username})" if user.username else ""
    return f'<a href="tg://user?id={user.id}">{html_esc(name) or user.id}</a>{uname} <code>{user.id}</code>'


# group=2: overlaps antyspam (group 0) and auto_download (group 1) on private
# non-me non-bot messages; separate group so all three run independently.
@Client.on_message(filters.private & ~filters.me & ~filters.bot, group=2)
async def _cache_incoming(client, message: Message):
    _remember(message)


@Client.on_edited_message(filters.private & ~filters.me & ~filters.bot)
async def _log_edited(client, message: Message):
    cached = _CACHE.get(message.id)
    old = cached["text"] if cached else "(not cached)"
    new = message.text or message.caption or ""
    if old == new:
        return
    _remember(message)  # keep cache current for a later delete
    # The bodies are somebody else's message text. Sent through the default parse
    # mode they were reinterpreted -- asterisks became formatting, tags were
    # deleted -- so the log could not be trusted to show what was actually said,
    # and a sender could forge convincing-looking log entries. Explicit HTML with
    # both bodies escaped shows them verbatim.
    text = (
        f"✏️ <b>Edited message</b> in PM\n"
        f"👤 {_who(message.from_user)}\n\n"
        f"<b>Before:</b>\n{html_esc(old)}\n\n"
        f"<b>After:</b>\n{html_esc(new)}"
    )
    try:
        await client.send_message(client.me.id, text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"[LOGGER] edited-log failed: {e}")


# No filter: private-chat delete updates have message.chat == None, so
# filters.private would never match. We only act on IDs we cached (which are
# private-only by construction), so this is implicitly scoped correctly.
@Client.on_deleted_messages()
async def _log_deleted(client, messages):
    for message in messages:
        cached = _CACHE.pop(message.id, None)
        if not cached:
            continue
        text = (
            f"🗑 <b>Deleted message</b> in PM\n"
            f"👤 {_who(cached['user'])}\n\n"
            f"{html_esc(cached['text']) or '<i>(no text)</i>'}"
        )
        try:
            await client.send_message(client.me.id, text, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)
            if cached["file_id"]:
                send = getattr(client, f"send_{cached['media_type']}", None)
                if send:
                    await send(client.me.id, cached["file_id"])
        except Exception as e:
            logger.error(f"[LOGGER] deleted-log failed: {e}")
