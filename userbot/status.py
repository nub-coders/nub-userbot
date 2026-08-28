
from random import choice
from platform import python_version
from pyrogram import __version__ as versipyro
from config import *
from tools import *

@Client.on_message(filters.command(["alive", "awake"], prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def alive(client, message):
    user_id, alive_logo, emoji, alive_text = await get_globals(client)
    xx = await message.edit_text("⚡️")
    send = client.send_video if alive_logo.endswith(".mp4") else client.send_photo
    uptime = await get_readable_time((time.time() - StartTime))

    stats_block = (
        f"<blockquote>\n"
        f"<b>• Master:</b> {client.me.mention}\n"
        f"<b>• Python:</b> <code>{python_version()}</code>\n"
        f"<b>• Pyrogram:</b> <code>{versipyro}</code>\n"
        f"<b>• Uptime:</b> <code>{uptime}</code>\n"
        f"</blockquote>"
    )

    man = (
        f"<b>{emoji} NUB Userbot is Online</b>\n\n"
        f"<blockquote>{alive_text}</blockquote>\n\n"
        f"{stats_block}\n\n"
        f"<b><a href='https://t.me/{GROUP}'>SUPPORT</a></b> | "
        f"<b><a href='https://t.me/{CHANNEL}'>CHANNEL</a></b> | "
        f"<b><a href='tg://user?id={client.me.id}'>OWNER</a></b>"
    )
    try:
        await xx.delete()
        await send(
            message.chat.id,
            alive_logo,
            caption=man,
            parse_mode=enums.ParseMode.HTML,
        )
    except BaseException:
        await xx.edit(man, parse_mode=enums.ParseMode.HTML, disable_web_page_preview=True)


@Client.on_message(filters.command("ping", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def pingme(client, message):
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()

    msg = await message.edit("🏓 <b>Pinging...</b>", parse_mode=enums.ParseMode.HTML)

    end = datetime.datetime.now()
    ping_duration = (end - start).microseconds / 1000

    if ping_duration < 100:
        status = "EXCELLENT 🟢"
    elif ping_duration < 200:
        status = "GOOD 🟡"
    else:
        status = "MODERATE 🔴"

    quotes = [
        "Blazing fast! ⚡",
        "Speed demon! 🔥",
        "Lightning quick! ⚡",
        "Sonic boom! 💨"
    ]

    response = (
        f"<b>🏓 Pong!</b> <code>{ping_duration:.2f}ms</code>\n\n"
        f"<blockquote>\n"
        f"<b>• Ping:</b> <code>{ping_duration:.2f} ms</code>\n"
        f"<b>• Status:</b> {status}\n"
        f"<b>• Uptime:</b> <code>{uptime}</code>\n"
        f"<b>• Owner:</b> {client.me.mention}\n"
        f"</blockquote>\n\n"
        f"<i>\"{choice(quotes)}\"</i>"
    )

    await msg.edit(response, parse_mode=enums.ParseMode.HTML)



async def get_globals(client):
    user_id = client.me.id
    session_name = f'user_{user_id}'
    user_dir = session_name
    os.makedirs(user_dir, exist_ok=True)
    try:
       logo = gvarstatus(user_id, "ALIVE_LOGO") or (await client.download_media(client.me.photo.big_file_id, f"{user_dir}/{'logo.mp4' if client.me.photo.has_animation else 'logo.jpg'}") if client.me.photo else "userbot.jpg")
    except ValueError:
       logo = "userbot.jpg"
    alive_logo = logo
    if type(logo) is bytes:
       output = f"{user_dir}/logo.jpg"
       with open(output, "wb") as fimage:
          fimage.write(base64.b64decode(logo))
       alive_logo = output
       if 'video' in mime.from_file(output):
          alive_logo = rename_file(output, f"{user_dir}/logo.mp4")
    emoji = gvarstatus(user_id, "ALIVE_EMOJI") or "⚡️"
    alive_text = gvarstatus(user_id, "ALIVE_TEXT_CUSTOM") or "Hey, I am alive."
    return user_id, alive_logo, emoji, alive_text

@Client.on_message(filters.command("setalivetext", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def setalivetext(client,message):
    user_id = client.me.id
    text = (
        cmd_text(message).split(None, 1)[1]
        if len(
            message.command,
        ) != 1
        else None
    )
    if message.reply_to_message:
        text = message.reply_to_message.text or message.reply_to_message.caption
    NUB = await message.edit_text("`Processing...`")
    if not text:
        return await message.edit_text("**Please provide some text or reply to a text**"
        )
    set_gvar(user_id, "ALIVE_TEXT_CUSTOM", text)
    await NUB.edit(f"**Successfully customized ALIVE TEXT to** `{text}`")
    

@Client.on_message(filters.command("setemoji", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def setemoji(client,message):
    user_id = client.me.id
    emoji = (
        cmd_text(message).split(None, 1)[1]
        if len(
            message.command,
        ) != 1
        else None
    )
    NUB = await message.edit_text("`Processing...`")
    if not emoji:
        return await message.edit_text( "**Please provide an emoji**")
    set_gvar(user_id, "ALIVE_EMOJI", emoji)
    await NUB.edit(f"**Successfully customized ALIVE EMOJI to** {emoji}")


@Client.on_message(filters.command('resetallalive', prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def deletealivekeys(client, message):
    user_id = client.me.id
    NUB = await message.edit_text( "`Deleting keys...`")

    # Function to delete keys
    def delete_user_keys(user_id, keys):
        user_sessions.update_one(
            {"user_id": user_id},
            {"$unset": {key: "" for key in keys}}
        )

    # Keys to delete
    keys_to_delete = ["ALIVE_EMOJI", "ALIVE_TEXT_CUSTOM"]
    
    # Delete the keys for the user
    delete_user_keys(user_id, keys_to_delete)
    
    await NUB.edit("**Successfully deleted ALIVE keys (emoji, text)**")

