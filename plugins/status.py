
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
    await asyncio.sleep(2)
    send = client.send_video if alive_logo.endswith(".mp4") else client.send_photo
    uptime = await get_readable_time((time.time() - StartTime))
    man = (
        f"""[NUB Userbot ⚡](tg://user?id={client.me.id}) is Up and Running.

<b>{alive_text}</b>

<blockquote>{emoji} <b>MASTER :</b> {client.me.mention}
{emoji} <b>Bot Version :</b> <code>1.0</code>
{emoji} <b>Python Version :</b> <code>{python_version()}</code>
{emoji} <b>Pyrogram Version :</b> <code>{versipyro}</code>
{emoji} <b>Bot Uptime :</b> <code>{uptime}</code></blockquote>

<b>[SUPPORT](https://t.me/{GROUP})</b> | <b>[CHANNEL](https://t.me/{CHANNEL})</b> | <b>[OWNER](tg://user?id={client.me.id})</b>"""
    )
    try:
            await xx.delete()
            await send(
                message.chat.id,
                alive_logo,
                caption=man,
            )
    except BaseException:
        await xx.edit(man, disable_web_page_preview=True)

@Client.on_message(filters.command("ping", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def pingme(client, message):
    # Calculate uptime
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()
    
    # Fun emoji animations for loading
    loading_emojis = ["🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚", "🕛"]
    ping_frames = [
        "█▒▒▒▒▒▒▒▒▒▒ 10%",
        "███▒▒▒▒▒▒▒ 30%",
        "█████▒▒▒▒▒ 50%",
        "███████▒▒▒ 70%",
        "█████████▒ 90%",
        "██████████ 100%"
    ]
    
    # Animated loading sequence
    msg = await message.edit("🏓 **Pinging...**")
    
    for frame in ping_frames:
        await msg.edit(f"```\n{frame}\n```{choice(loading_emojis)}")
        await asyncio.sleep(0.3)  # Smooth animation delay
    
    end = datetime.datetime.now()
    ping_duration = (end - start).microseconds / 1000
    
    # Status indicators based on ping speed
    if ping_duration < 100:
        status = "EXCELLENT 🟢"
    elif ping_duration < 200:
        status = "GOOD 🟡"
    else:
        status = "MODERATE 🔴"
    
    # Fancy formatted response
    response = f"""
╭──────────────────
│   PONG! 🏓       
├──────────────────
│ ⌚ Speed: {ping_duration:.2f}ms  
│ 📊 Status: {status} 
│ ⏱️ Uptime: {uptime}  
│ 👑 Owner: {client.me.mention} 
╰──────────────────
"""
    
    # Add random motivational messages
    quotes = [
        "Blazing fast! ⚡",
        "Speed demon! 🔥",
        "Lightning quick! ⚡",
        "Sonic boom! 💨"
    ]
    
    await msg.edit(
        response + f"\n<b>{choice(quotes)}</b>"
    )

async def get_globals(client):
    user_id = client.me.id
    session_name = f'user_{user_id}'
    user_dir = f"{ggg}/{session_name}"
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
        message.text.split(None, 1)[1]
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
        message.text.split(None, 1)[1]
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

