
import requests
import base64
import asyncio
import os
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import StickersetInvalid, YouBlockedUser
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.types import InputStickerSetShortName
from config import *
from tools import *


@Client.on_message(filters.command("tiny") & filters.me)
@retry()
async def tinying(client ,message):
    reply = message.reply_to_message
    if not (reply and (reply.media)):
        return await message.edit_text( "**Please reply to any sticker!**")
    NUB = await message.edit_text( "`Processing . . .`")
    ik = await client.download_media(reply)
    im1 = Image.open("blank.png")
    if ik.endswith(".tgs"):
        await client.download_media(reply, "man.tgs")
        await bash("lottie_convert.py man.tgs json.json")
        json = open("json.json", "r")
        jsn = json.read()
        jsn = jsn.replace("512", "2000")
        ("json.json", "w").write(jsn)
        await bash("lottie_convert.py json.json man.tgs")
        file = "man.tgs"
        os.remove("json.json")
    else:
        if ik.endswith((".gif", ".mp4")):
            iik = cv2.VideoCapture(ik)
            busy = iik.read()
            cv2.imwrite("i.png", busy)
            src = "i.png"
        else:
            src = ik
        im = Image.open(src)
        z, d = im.size
        if z == d:
            xxx, yyy = 200, 200
        else:
            t = z + d
            a = z / t
            b = d / t
            aa = (a * 100) - 50
            bb = (b * 100) - 50
            xxx = 200 + 5 * aa
            yyy = 200 + 5 * bb
        k = im.resize((int(xxx), int(yyy)))
        k.save("k.png", format="PNG", optimize=True)
        im2 = Image.open("k.png")
        back_im = im1.copy()
        back_im.paste(im2, (150, 0))
        back_im.save("o.webp", "WEBP", quality=95)
        file = "o.webp"
        if src != ik:
            os.remove(src)
        os.remove("k.png")
    await asyncio.gather(
        NUB.delete(),
        client.send_sticker(
            message.chat.id,
            sticker=file,
            reply_to_message_id=reply.id,
        ),
    )
    os.remove(file)
    os.remove(ik)

@Client.on_message(filters.command("mmf") & filters.me)
@retry()
async def memify(client, message):
    if not message.reply_to_message_id:
        await message.edit_text("**Reply to any photo or sticker!**")
        return
    reply_message = message.reply_to_message
    if not reply_message.media:
        await message.edit_text( "**Reply to any photo or sticker!**")
        return
    file = await client.download_media(reply_message)
    NUB = await message.edit_text( "`Processing . . .`")
    text = get_arg(message)
    if len(text) < 1:
        return await msg.edit(f"Please use `/mmf <text>`")
    meme = await add_text_img(file, text)
    await asyncio.gather(
        NUB.delete(),
        client.send_sticker(
            message.chat.id,
            sticker=meme,
            reply_to_message_id=reply_message.id,
        ),
    )
    os.remove(meme)

async def add_text_img(image_path, text):
    font_size = 12
    stroke_width = 1

    if ";" in text:
        upper_text, lower_text = text.split(";")
    else:
        upper_text = text
        lower_text = ""

    img = Image.open(image_path).convert("RGBA")
    img_info = img.info
    image_width, image_height = img.size
    font = ImageFont.truetype(
        font="default.ttf",
        size=int(image_height * font_size) // 100,
    )
    draw = ImageDraw.Draw(img)

    char_width, char_height = draw.textbbox((0, 0), 'A', font=font)[2:4]
    chars_per_line = image_width // char_width
    top_lines = textwrap.wrap(upper_text, width=chars_per_line)
    bottom_lines = textwrap.wrap(lower_text, width=chars_per_line)

    if top_lines:
        y = 10
        for line in top_lines:
            line_width, line_height = draw.textbbox((0, 0), line, font=font)[2:4]
            x = (image_width - line_width) / 2
            draw.text(
                (x, y),
                line,
                fill="black",
                font=font,
                stroke_width=stroke_width,
            )
            y += line_height

    if bottom_lines:
        y = image_height - char_height * len(bottom_lines) - 15
        for line in bottom_lines:
            line_width, line_height = draw.textbbox((0, 0), line, font=font)[2:4]
            x = (image_width - line_width) / 2
            draw.text(
                (x, y),
                line,
                fill="black",
                font=font,
                stroke_width=stroke_width,
            )
            y += line_height

    final_image = os.path.join("memify.webp")
    img.save(final_image, **img_info)
    return final_image

@Client.on_message(filters.command("kang") & filters.me)
@retry()
async def kang(client, message):
    user = client.me
    replied = message.reply_to_message
    NUB = await message.edit_text("`It's also possible that the sticker is colong ahh...`")
    media_ = None
    emoji_ = None
    is_anim = False
    is_video = False
    resize = False
    ff_vid = False
    if replied and replied.media:
        if replied.photo:
            resize = True
        elif replied.document and "image" in replied.document.mime_type:
            resize = True
            replied.document.file_name
        elif replied.document and "tgsticker" in replied.document.mime_type:
            is_anim = True
            replied.document.file_name
        elif replied.document and "video" in replied.document.mime_type:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.animation:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.video:
            resize = True
            is_video = True
            ff_vid = True
        elif replied.sticker:
            if not replied.sticker.file_name:
                await NUB.edit("**Sticker has no Name!**")
                return
            emoji_ = replied.sticker.emoji
            is_anim = replied.sticker.is_animated
            is_video = replied.sticker.is_video
            if not (
                replied.sticker.file_name.endswith(".tgs")
                or replied.sticker.file_name.endswith(".webm")
            ):
                resize = True
                ff_vid = True
        else:
            await NUB.edit("**Unsupported File**")
            return
        media_ = await client.download_media(replied, file_name="downloads/")
    else:
        await NUB.edit("**Please Reply to Photo/GIF/Sticker Media!**")
        return
    if media_:
        args = get_arg(message)
        pack = 1
        if len(args) == 2:
            emoji_, pack = args
        elif len(args) == 1:
            if args[0].isnumeric():
                pack = int(args[0])
            else:
                emoji_ = args[0]

        if emoji_ and emoji_ not in (
            getattr(emoji, _) for _ in dir(emoji) if not _.startswith("_")
        ):
            emoji_ = None
        if not emoji_:
            emoji_ = "✨"

        u_name = user.username
        u_name = "@" + u_name if u_name else user.first_name or user.id
        packname = f"Sticker_u{user.id}_v{pack}"
        custom_packnick = f"{u_name} Sticker Pack"
        packnick = f"{custom_packnick} Vol.{pack}"
        cmd = "/newpack"
        if resize:
            media_ = await resize_media(media_, is_video, ff_vid)
        if is_anim:
            packname += "_animated"
            packnick += " (Animated)"
            cmd = "/newanimated"
        if is_video:
            packname += "_video"
            packnick += " (Video)"
            cmd = "/newvideo"
        exist = False
        while True:
            try:
                exist = await client.invoke(
                    GetStickerSet(
                        stickerset=InputStickerSetShortName(short_name=packname), hash=0
                    )
                )
            except StickersetInvalid:
                exist = False
                break
            limit = 50 if (is_video or is_anim) else 120
            if exist.set.count >= limit:
                pack += 1
                packname = f"a{user.id}_by_userge_{pack}"
                packnick = f"{custom_packnick} Vol.{pack}"
                if is_anim:
                    packname += f"_anim{pack}"
                    packnick += f" (Animated){pack}"
                if is_video:
                    packname += f"_video{pack}"
                    packnick += f" (Video){pack}"
                await NUB.edit(
                    f"`Create a New Sticker Pack {pack} Because the Sticker Pack is Full`"
                )
                continue
            break
        if exist is not False:
            try:
                await client.send_message("stickers", "/addsticker")
            except YouBlockedUser:
                await client.unblock_user("stickers")
                await client.send_message("stickers", "/addsticker")
            except Exception as e:
                return await NUB.edit(f"**ERROR:** `{e}`")
            await asyncio.sleep(2)
            await client.send_message("stickers", packname)
            await asyncio.sleep(2)
            limit = "50" if is_anim else "120"
            while limit in await get_response(message, client):
                pack += 1
                packname = f"a{user.id}_by_{user.username}_{pack}"
                packnick = f"{custom_packnick} vol.{pack}"
                if is_anim:
                    packname += "_anim"
                    packnick += " (Animated)"
                if is_video:
                    packname += "_video"
                    packnick += " (Video)"
                await NUB.edit(
                    "`Creating a New Sticker Pack"
                    + str(pack)
                    + "Because the Sticker Pack is Full"
                )
                await client.send_message("stickers", packname)
                await asyncio.sleep(2)
                if await get_response(message, client) == "Invalid pack selected.":
                    await client.send_message("stickers", cmd)
                    await asyncio.sleep(2)
                    await client.send_message("stickers", packnick)
                    await asyncio.sleep(2)
                    await client.send_document("stickers", media_)
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", emoji_)
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", "/publish")
                    await asyncio.sleep(2)
                    if is_anim:
                        await client.send_message(
                            "Stickers", f"<{packnick}>", parse_mode=ParseMode.MARKDOWN
                        )
                        await asyncio.sleep(2)
                    await client.send_message("Stickers", "/skip")
                    await asyncio.sleep(2)
                    await client.send_message("Stickers", packname)
                    await asyncio.sleep(2)
                    await NUB.edit(
                        f"**Sticker Added Successfully!**\n 🔥 **[CLICK HERE](https://t.me/addstickers/{packname})** 🔥\n**To Use Stickers**"
                    )
                    return
            await client.send_document("stickers", media_)
            await asyncio.sleep(2)
            if (
                await get_response(message, client)
                == "Sorry, the file type is invalid."
            ):
                await NUB.edit(
                    "**Failed to Add Sticker, Use @Stickers Bot to Add Your Sticker.**"
                )
                return
            await client.send_message("Stickers", emoji_)
            await asyncio.sleep(2)
            await client.send_message("Stickers", "/done")
        else:
            await NUB.edit("`Creating a New Sticker Pack`")
            try:
                await client.send_message("Stickers", cmd)
            except YouBlockedUser:
                await client.unblock_user("stickers")
                await client.send_message("stickers", "/addsticker")
            await asyncio.sleep(2)
            await client.send_message("Stickers", packnick)
            await asyncio.sleep(2)
            await client.send_document("stickers", media_)
            await asyncio.sleep(2)
            if (
                await get_response(message, client)
                == "Sorry, the file type is invalid."
            ):
                await NUB.edit(
                    "**Failed to Add Sticker, Use @Stickers Bot to Add Your Sticker.**"
                )
                return
            await client.send_message("Stickers", emoji_)
            await asyncio.sleep(2)
            await client.send_message("Stickers", "/publish")
            await asyncio.sleep(2)
            if is_anim:
                await client.send_message("Stickers", f"<{packnick}>")
                await asyncio.sleep(2)
            await client.send_message("Stickers", "/skip")
            await asyncio.sleep(2)
            await client.send_message("Stickers", packname)
            await asyncio.sleep(2)
        await NUB.edit(
            f"**Sticker Added Successfully!**\n 🔥 **[CLICK HERE](https://t.me/addstickers/{packname})** 🔥\n**To Use Stickers**"
        )
        if os.path.exists(str(media_)):
            os.remove(media_)

async def get_response(message, client):
    return [x async for x in client.get_chat_history("Stickers", limit=1)][0].text
