
from config import *
from tools import *

# When we last answered a given (chat, mentioner) pair, so one busy group cannot
# turn the account into a mention-answering machine. The old state was a single
# "last person who mentioned me" slot keyed by our own id, which two strangers
# taking turns -- or one lively group -- defeated immediately: every mention got
# an AFK reply, which is exactly the behaviour that gets accounts limited.
_afk_replied_at = {}
AFK_REPLY_COOLDOWN = 300  # seconds, per chat and per mentioner

# Support filter
is_support = filters.create(lambda _, __, message: message.chat.is_support)

@Client.on_message(filters.mentioned & ~filters.channel & ~filters.me & ~filters.bot & ~is_support)
async def afk_handler(client, message):
    # Anonymous admins and linked-channel forwards arrive with no from_user, and
    # either can carry a mention of us; `~filters.channel` only excludes channel
    # *chats*. Reading .id off None raised AttributeError here.
    if not message.from_user:
        return

    user_id = client.me.id
    user_data = cached_get_user_data(user_id) or {}
    afk_info = user_data.get("afk", {})
    if not afk_info or not afk_info.get("is_afk", False):
        return

    key = (message.chat.id, message.from_user.id)
    now = time.time()
    last = _afk_replied_at.get(key, 0)
    if now - last < AFK_REPLY_COOLDOWN:
        return
    # Drop entries that can no longer suppress anything, so a long-running
    # process in many groups does not grow this without a ceiling.
    if len(_afk_replied_at) > 500:
        for stale in [k for k, t in _afk_replied_at.items() if now - t >= AFK_REPLY_COOLDOWN]:
            del _afk_replied_at[stale]
    _afk_replied_at[key] = now

    start = datetime.datetime.fromtimestamp(afk_info["start"])
    end = datetime.datetime.now().replace(microsecond=0)
    afk_time = end - start
    await message.reply(
        f"<b>I'm AFK {afk_time}\nReason:</b> <i>{html_esc(afk_info['reason'])}</i>",
        parse_mode=enums.ParseMode.HTML,
    )

@Client.on_message(filters.command("afk", prefixes=HARDCODED_PREFIXES) & filters.me)
async def afk(client, message):
    if len(cmd_text(message).split()) >= 2:
        reason = cmd_text(message).split(" ", maxsplit=1)[1]
    else:
        reason = "None"

    afk_info = {
        "start": int(datetime.datetime.now().timestamp()),
        "is_afk": True,
        "reason": reason
    }

    # A fresh AFK session should notify everyone again, including whoever we
    # answered last time.
    _afk_replied_at.clear()
    user_sessions.update_one({"user_id": client.me.id}, {"$set": {"afk": afk_info}}, upsert=True)
    await message.edit(
        f"<b>I'm going AFK.\nReason:</b> <i>{html_esc(reason)}</i>",
        parse_mode=enums.ParseMode.HTML,
    )

@Client.on_message(filters.command("unafk", prefixes=HARDCODED_PREFIXES) & filters.me)
async def unafk(client, message):
    # Keyed on our own id, like the write in afk() -- reading from_user.id here
    # meant an anonymous-admin `.unafk` looked up None.
    user_id = client.me.id

    user_data = cached_get_user_data(user_id) or {}
    afk_info = user_data.get("afk", {})
    is_afk = afk_info.get("is_afk", False)
    if afk_info and is_afk:
        start = datetime.datetime.fromtimestamp(afk_info["start"])
        end = datetime.datetime.now().replace(microsecond=0)
        afk_time = end - start

        await message.edit(
            f"<b>I'm not AFK anymore.\nI was AFK for: {afk_time}</b>",
            parse_mode=enums.ParseMode.HTML,
        )
        afk_info = {
            "start": 0,
            "is_afk": False,
            "reason": ""
        }

        _afk_replied_at.clear()
        user_sessions.update_one({"user_id": user_id}, {"$set": {"afk": afk_info}}, upsert=True)
    else:
        await message.edit("<b>You weren't AFK</b>", parse_mode=enums.ParseMode.HTML)
