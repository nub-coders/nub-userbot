
from config import *
from tools import *

# Global variables for AFK functionality
aaafk = {}

# Support filter
is_support = filters.create(lambda _, __, message: message.chat.is_support)

@Client.on_message(filters.mentioned & ~filters.channel & ~filters.me & ~filters.bot & ~is_support)
async def afk_handler(client, message):
    user_id = client.me.id
    aaafk.setdefault(user_id, 100)
    user_data = user_sessions.find_one({"user_id": user_id})
    afk_info = user_data.get("afk", {})
    if not afk_info or aaafk[user_id] == message.from_user.id:
        return
    is_afk = afk_info.get("is_afk", False)
    if not afk_info or not is_afk:
        return
    start = datetime.datetime.fromtimestamp(afk_info["start"])
    end = datetime.datetime.now().replace(microsecond=0)
    afk_time = end - start
    aaafk[user_id] = message.from_user.id
    await message.reply(
        f"<b>I'm AFK {afk_time}\nReason:</b> <i>{afk_info['reason']}</i>"
    )

@Client.on_message(filters.command("afk") & filters.me)
async def afk(client, message):
    if len(message.text.split()) >= 2:
        reason = message.text.split(" ", maxsplit=1)[1]
    else:
        reason = "None"

    afk_info = {
        "start": int(datetime.datetime.now().timestamp()),
        "is_afk": True,
        "reason": reason
    }

    user_sessions.update_one({"user_id": client.me.id}, {"$set": {"afk": afk_info}}, upsert=True)
    await message.edit(f"<b>I'm going AFK.\n" f"Reason:</b> <i>{reason}</i>")

@Client.on_message(filters.command("unafk") & filters.me)
async def unafk(client, message):
    user_id = message.from_user.id

    user_data = user_sessions.find_one({"user_id": user_id})
    afk_info = user_data.get("afk", {})
    is_afk = afk_info.get("is_afk", False)
    if afk_info and is_afk:
        start = datetime.datetime.fromtimestamp(afk_info["start"])
        end = datetime.datetime.now().replace(microsecond=0)
        afk_time = end - start

        await message.edit(
            f"<b>I'm not AFK anymore.\n" f"I was AFK for: {afk_time}</b>"
        )
        afk_info = {
            "start": 0,
            "is_afk": False,
            "reason": ""
        }

        user_sessions.update_one({"user_id": client.me.id}, {"$set": {"afk": afk_info}}, upsert=True)
    else:
        await message.edit("<b>You weren't AFK</b>")
