
import json
import requests
import base64
import asyncio
import os
import logging
import re
from typing import Any, Dict, List, Optional
from PIL import Image
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.enums import ParseMode
from pyrogram.errors import StickersetInvalid, YouBlockedUser, PeerIdInvalid
from pyrogram.raw.functions.messages import GetStickerSet
from pyrogram.raw.types import InputStickerSetShortName
from config import *
from tools import *
from utils.message import Msg

logger = logging.getLogger("userbot")



@Client.on_message(filters.command("tiny", prefixes=HARDCODED_PREFIXES) & filters.me)
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
        with open("json.json", "r") as f:
            jsn = f.read()
        jsn = jsn.replace("512", "2000")
        with open("json.json", "w") as f:
            f.write(jsn)
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

@Client.on_message(filters.command("mmf", prefixes=HARDCODED_PREFIXES) & filters.me)
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

@Client.on_message(filters.command("kang", prefixes=HARDCODED_PREFIXES) & filters.me)
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




me_filter = (filters.me | sudoers_filter()) & filters.command("qt", prefixes=HARDCODED_PREFIXES)
@Client.on_message(me_filter)
async def duck_command_handler(client, message):
    """Enhanced quote command handler with better error handling and features"""
    USERBOT = await edit_or_reply(message, f"╭── {Msg.EMOJI_NOTE} QUOTE ──╮\n┃ {Msg.EMOJI_LOADING} Generating quote...\n╰━━━━━━━━━━━━━━━━━━━━╯")

    # Check if the message is a reply
    if not message.reply_to_message:
        await USERBOT.edit_text(Msg.ERR_REPLY_TO_QUOTE)
        await asyncio.sleep(3)
        await USERBOT.delete()
        return

    try:
        sender = message.from_user.id if message.from_user else message.chat.id
        replied_message = message.reply_to_message
        user = replied_message.from_user or replied_message.sender_chat

        if not user:
            await USERBOT.edit_text(Msg.ERR_GET_USER_INFO_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
            return

        # Admin check
        if hasattr(user, 'id') and is_admin_user(user.id):
            return await USERBOT.edit_text(
                "You are fucking requesting me to create fake quote of my lord and my creator.\nSo I won't...**Fuck off!!**"
            )

        # Setup directories
        session_name = f'user_{sender}'
        user_dir = session_name
        os.makedirs(user_dir, exist_ok=True)

        # Parse command text and check for flags
        HARDCODED_PREFIXES = ["!", "_", "?", "^", "."]
        escaped_prefixes = '|'.join(re.escape(p) for p in HARDCODED_PREFIXES)
        cmd_match = re.search(rf"^({escaped_prefixes})\w+", message.text or "")
        words_to_remove = []
        if cmd_match:
            words_to_remove.append(cmd_match.group(0))

        include_reply = False
        force_custom = False

        raw_text = message.text or ""

        # Check for -r flag (include reply)
        if "-r" in raw_text:
            include_reply = True
            words_to_remove.append("-r")

        # Check for -f flag (force custom text)
        if "-f" in raw_text:
            force_custom = True
            words_to_remove.append("-f")

        # Extract command specific entities if needed
        command_text, custom_entities = update_message_and_entities(
            text=raw_text,
            entities=message.entities or [],
            words_to_remove=words_to_remove
        )

        # Determine quote text based on flags and available text
        if force_custom and command_text:
            # Use custom text when -f flag is present and text is provided
            quote_text = command_text
        else:
            # Default: always use original message content (when no -f flag or no custom text)
            quote_text = await get_message_content(replied_message)

        # If no text content but message has media, use a placeholder
        if not quote_text and await has_media(replied_message):
            quote_text = " "  # Use space as placeholder for media-only messages

        if not quote_text:
            await USERBOT.edit_text(Msg.ERR_NO_TEXT_TO_QUOTE)
            await asyncio.sleep(3)
            await USERBOT.delete()
            return

        # Step 1: Collect all information first
        
        # Collect user information
        user_info = await build_user_info(client, user)
        
        # Collect entities
        entities = []
        if force_custom and command_text:
            entities = await convert_entities(custom_entities)
        else:
            source_entities = replied_message.entities or replied_message.caption_entities
            if source_entities:
                quote_text, processed_entities = update_message_and_entities(
                    text=quote_text,
                    entities=source_entities
                )
                entities = await convert_entities(processed_entities)
        
        # Collect media information (only if not using custom text with -f flag)
        media_info = None
        parent_reply_message = replied_message.reply_to_message
        if not parent_reply_message and getattr(replied_message, "reply_to_message_id", None):
            try:
                parent_reply_message = await client.get_messages(
                    replied_message.chat.id,
                    replied_message.reply_to_message_id,
                )
            except Exception as e:
                logger.warning(f"Failed to fetch parent reply message: {e}")

        if not (force_custom and command_text):
            media_info = await get_media_info(client, replied_message)
            # Fallback: if the replied message is text-only but is replying to media,
            # include that parent media in the generated quote.
            # For .qt -r, do NOT copy parent media into the main message,
            # otherwise main and reply become duplicate media blocks.
            if not media_info and parent_reply_message and not include_reply:
                media_info = await get_media_info(client, parent_reply_message)
        
        # Collect reply information (only if -r flag is present and reply exists)
        reply_info = None
        if include_reply and parent_reply_message:
            reply_info = await build_reply_info(client, parent_reply_message)
        
        # Step 2: Validate all collected information
        if not user_info or "id" not in user_info:
            await USERBOT.edit_text(Msg.ERR_GET_USER_INFO_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
            return
        
        # Step 3: Build the complete payload after all information is collected
        
        # Create the main message object
        message_obj = {
            "from": user_info,
            "text": quote_text[:4096],  # Limit text length as per API docs
            "entities": entities,
            "avatar": True
        }
        
        # Add media if available
        if media_info:
            message_obj["media"] = media_info
        
        # Add reply if available
        if reply_info:
            message_obj["replyMessage"] = reply_info
        
        # Create the final payload
        quote_payload = {
            "type": "quote",
            "format": "webp",
            "backgroundColor": "#1b1429",
            "width": 512,
            "height": 768,
            "scale": 2,
            "emojiBrand": "apple",
            "botToken": BOT_TOKEN,  # Required for custom_emoji resolution via Telegram API
            "messages": [message_obj]
        }

        def _redact_payload_for_log(value):
            if isinstance(value, dict):
                sanitized = {}
                for k, v in value.items():
                    if k == "base64" and isinstance(v, str):
                        sanitized[k] = f"***BASE64_REDACTED*** ({len(v)} chars)"
                    else:
                        sanitized[k] = _redact_payload_for_log(v)
                return sanitized
            if isinstance(value, list):
                return [_redact_payload_for_log(v) for v in value]
            return value

        redacted_payload = _redact_payload_for_log(quote_payload)
        redacted_payload["botToken"] = "***REDACTED***" if redacted_payload.get("botToken") else None
        log_tag = "[FAKE QUOTE]" if force_custom else "[QUOTE]"
        try:
            msg0 = redacted_payload.get("messages", [{}])[0]
            reply_obj = msg0.get("replyMessage") if isinstance(msg0, dict) else None
            logger.info(
                "%s Summary: main_media=%s reply_attached=%s reply_media=%s reply_to_message_id=%s",
                log_tag,
                bool(msg0.get("media")) if isinstance(msg0, dict) else False,
                bool(reply_obj),
                bool(reply_obj.get("media")) if isinstance(reply_obj, dict) else False,
                getattr(replied_message, "reply_to_message_id", None),
            )
        except Exception as e:
            logger.warning(f"{log_tag} Failed to build summary log: {e}")

        logger.info(
            f"{log_tag} Payload: %s",
            json.dumps(redacted_payload, ensure_ascii=False)
        )
        
        quote_path = await generate_quote(client, quote_payload, user_dir)

        if not quote_path:
            await USERBOT.edit_text(Msg.ERR_GENERATE_QUOTE_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
            return

    except Exception as e:
        error_msg = f"Quote generation preparation error: {str(e)}"
        logger.error(error_msg)
        try:
            await (apps.get("app") or client).send_message(client.me.id, f"ERROR in quote handler: {error_msg}")
            await USERBOT.edit_text(Msg.ERR_QUOTE_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
        except Exception:            pass  # If even error handling fails, just continue
        return

    try:
        # Send the sticker
        await client.send_sticker(
            chat_id=message.chat.id,
            sticker=quote_path,
            reply_to_message_id=replied_message.id
        )
        await USERBOT.delete()
        return

    except PeerIdInvalid as e:
        error_msg = f"PEER_ID_INVALID error: {str(e)}"
        logger.warning(error_msg)
        try:
            await (apps.get("app") or client).send_message(client.me.id, f"ERROR in quote handler: {error_msg}")
            await USERBOT.edit_text(Msg.ERR_QUOTE_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
        except Exception:            pass
        return

    except Exception as e:
        error_msg = f"Quote send error: {str(e)}"
        logger.error(error_msg)
        try:
            await (apps.get("app") or client).send_message(client.me.id, f"ERROR in quote handler: {error_msg}")
            await USERBOT.edit_text(Msg.ERR_QUOTE_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
        except Exception:            pass  # If even error handling fails, just continue
        return



async def build_user_info(client, user) -> Optional[Dict[str, Any]]:
    """Build user information according to API spec with comprehensive error handling"""
    try:
        if not user:
            logger.debug("No user object provided")
            return None
            
        user_info = {
            "id": getattr(user, "id", 0)
        }
        
        # Handle name - use name field or first_name/last_name or title
        try:
            first_name = getattr(user, "first_name", None)
            last_name = getattr(user, "last_name", None)
            title = getattr(user, "title", None)
            username = getattr(user, "username", None)

            if first_name and last_name:
                user_info["first_name"] = first_name
                user_info["last_name"] = last_name
            elif first_name:
                user_info["first_name"] = first_name
            elif title:
                user_info["first_name"] = title
                user_info["name"] = title
            elif username:
                user_info["username"] = username
                user_info["name"] = f"@{username}"
            else:
                user_info["name"] = "Unknown User"
        except Exception as e:
            logger.warning(f"Error processing username info: {e}")
            user_info["name"] = "Unknown User"
        
        # Handle profile photo
        try:
            if hasattr(user, 'photo') and user.photo:
                file_id = None
                if hasattr(user.photo, 'big_file_id') and user.photo.big_file_id:
                    file_id = user.photo.big_file_id
                elif hasattr(user.photo, 'small_file_id') and user.photo.small_file_id:
                    file_id = user.photo.small_file_id
                
                if file_id:
                    session_name = f'user_{client.me.id}'
                    user_dir = session_name
                    os.makedirs(user_dir, exist_ok=True)
                    photo_path = await client.download_media(file_id, file_name=f"{user_dir}/")
                    if photo_path and os.path.exists(photo_path):
                        with open(photo_path, "rb") as f:
                            base64_img = base64.b64encode(f.read()).decode('utf-8')
                        user_info["photo"] = {"base64": base64_img}
                        os.remove(photo_path)
        except Exception as e:
            logger.warning(f"Error getting user photo: {e}")
        
        # Handle emoji status
        try:
            if hasattr(user, 'emoji_status') and user.emoji_status:
                if hasattr(user.emoji_status, 'custom_emoji_id') and user.emoji_status.custom_emoji_id:
                    user_info["emoji_status"] = str(user.emoji_status.custom_emoji_id)
        except Exception as e:
            logger.warning(f"Error getting emoji status: {e}")
        
        return user_info
        
    except Exception as e:
        logger.error(f"Critical error in build_user_info: {e}")
        return None



async def get_media_info(client, message) -> Optional[Dict[str, Any]]:
    logger.debug(f"[DEBUG] get_media_info called with message: {message}")
    """Extract media information for quote-api according to API spec with validation"""
    
    # Initial validation
    if not message:
        logger.debug("[DEBUG] No message provided")
        return None
        
    if not hasattr(message, 'media'):
        logger.debug("[DEBUG] Message has no media attribute")
        return None
    
    logger.debug(f"[DEBUG] Message has media attribute: {message.media}")

    # Resolve media attribute name robustly across enum implementations.
    media_enum = message.media
    media_attr = None

    # Preferred: enum name (PHOTO -> photo)
    if hasattr(media_enum, 'name') and media_enum.name:
        media_attr = str(media_enum.name).lower()
        logger.debug(f"[DEBUG] Converted media_attr from enum name: {media_attr}")

    # Fallback: enum/string value
    if not media_attr and hasattr(media_enum, 'value'):
        enum_value = media_enum.value
        logger.debug(f"[DEBUG] Raw media enum value: {enum_value}")
        if isinstance(enum_value, str) and enum_value:
            media_attr = enum_value.lower()

    # Last fallback: parse string form (MessageMediaType.PHOTO -> photo)
    if not media_attr:
        media_str = str(media_enum)
        logger.debug(f"[DEBUG] Raw media string: {media_str}")
        if media_str.startswith('MessageMediaType.'):
            media_attr = media_str.replace('MessageMediaType.', '').lower()
        elif media_str:
            media_attr = media_str.lower()

    if not media_attr:
        logger.debug("[DEBUG] Could not resolve media attribute name")
        return None

    # Get the media object using resolved attribute.
    media_obj = getattr(message, media_attr, None)

    # Defensive fallback for cases where enum mapping differs at runtime.
    if not media_obj:
        for candidate in ['photo', 'sticker', 'video', 'animation', 'document', 'video_note', 'voice', 'audio']:
            candidate_obj = getattr(message, candidate, None)
            if candidate_obj:
                media_attr = candidate
                media_obj = candidate_obj
                logger.debug(f"[DEBUG] Fallback media_attr matched: {media_attr}")
                break

    logger.debug(f"[DEBUG] Media object retrieved: {media_obj}")

    if not media_obj:
        logger.debug(f"[DEBUG] No media object found for type: {media_attr}")
        return None

    # Get thumbnail file_id first (important for stickers/animated media).
    # Quote APIs generally accept image previews, not raw animated/video payloads.
    logger.debug(f"[DEBUG] Attempting to resolve thumbnail from media_attr: {media_attr}")
    try:
        media_attribute = getattr(message, media_attr)
        logger.debug(f"[DEBUG] Media attribute object: {media_attribute}")
        
        thumbnail_file_id = None

        # 1) Prefer explicit single thumbnail objects
        thumb_obj = getattr(media_attribute, 'thumb', None) or getattr(media_attribute, 'thumbnail', None)
        if thumb_obj and getattr(thumb_obj, 'file_id', None):
            thumbnail_file_id = thumb_obj.file_id

        # 2) Then try thumbnail lists
        if not thumbnail_file_id:
            thumbs = getattr(media_attribute, 'thumbs', None)
            logger.debug(f"[DEBUG] Thumbs attribute: {thumbs}")
            if thumbs and len(thumbs) > 0 and getattr(thumbs[0], 'file_id', None):
                thumbnail_file_id = thumbs[0].file_id

        # 3) Safe fallback to original file for static image-like types only
        if not thumbnail_file_id and media_attr in ['photo', 'sticker']:
            thumbnail_file_id = getattr(media_attribute, 'file_id', None)

        # 4) Last-resort fallback for other types if no thumb exists
        if not thumbnail_file_id:
            thumbnail_file_id = getattr(media_attribute, 'file_id', None)
                
        if thumbnail_file_id:
            logger.debug(f"[DEBUG] Thumbnail file_id found: {thumbnail_file_id}")
        else:
            logger.debug(f"[DEBUG] No file_id found")
            return None
            
    except (AttributeError, IndexError, TypeError) as e:
        logger.debug(f"[DEBUG] Exception getting thumbnail for media type {media_attr}: {e}")
        return None

    # Download the thumbnail
    temp_file_path = None
    try:
        logger.debug(f"[DEBUG] Starting thumbnail download process")
        
        # Create user-specific directory
        session_name = f'user_{client.me.id}'
        user_dir = session_name
        logger.debug(f"[DEBUG] User directory: {user_dir}")
        
        os.makedirs(user_dir, exist_ok=True)
        logger.debug(f"[DEBUG] User directory created/verified")

        # Create temporary file in user directory
        logger.debug(f"[DEBUG] Downloading media with file_id: {thumbnail_file_id}")
        temp_file_path = await client.download_media(message=thumbnail_file_id, file_name=f"{user_dir}/")
        logger.debug(f"[DEBUG] Media downloaded to: {temp_file_path}")

        # Convert to base64
        if temp_file_path and os.path.exists(temp_file_path):
            with open(temp_file_path, "rb") as image_file:
                base64_data = base64.b64encode(image_file.read()).decode('utf-8')
            logger.debug(f"[DEBUG] Media thumbnail converted to base64 successfully")
            return {"base64": base64_data}
        else:
            logger.debug("[DEBUG] Failed to download thumbnail for base64 conversion")
            return None

    except Exception as e:
        logger.debug(f"[DEBUG] Exception during download/upload process: {e}")
        return None
        
    finally:
        # Clean up temporary file
        logger.debug(f"[DEBUG] Cleanup phase - temp_file_path: {temp_file_path}")
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                logger.debug(f"[DEBUG] Temporary file deleted successfully: {temp_file_path}")
            except OSError as e:
                logger.debug(f"[DEBUG] Error deleting temporary file: {e}")
        else:
            logger.debug(f"[DEBUG] No temporary file to delete or file doesn't exist")

    logger.debug("[DEBUG] Function completed, returning None")
    return None



async def has_media(message):
    """Check if message contains any media content"""
    return any([
        message.sticker,
        message.photo,
        message.video,
        message.audio,
        message.voice,
        message.document,
        message.animation,
        message.video_note
    ])


async def get_message_content(message):
    """Extract content from any message type according to quote-api standards"""
    # For text messages, return the text directly
    if message.text:
        return message.text

    # For media with captions, return the caption
    if message.caption:
        return message.caption

    # For stickers, return empty string so the sticker media gets processed
    if message.sticker:
        return ""

    # For other media types without captions, return empty string
    # The media will be handled by the media processing function
    if any([message.photo, message.video, message.audio, message.voice,
            message.document, message.animation, message.video_note]):
        return ""

    # For contact messages, return contact info
    if message.contact:
        return f"{message.contact.first_name} {message.contact.last_name or ''}".strip()

    # For location messages, return coordinates or venue info
    if message.location:
        return f"{Msg.EMOJI_LINK} Location"

    if message.venue:
        return message.venue.title

    # For polls, return the question
    if message.poll:
        return message.poll.question

    # For dice/darts, return the emoji
    if message.dice:
        return message.dice.emoji

    # For games, return the title
    if message.game:
        return message.game.title

    # For service messages or unknown types, return empty string
    return ""


async def build_reply_info(client, reply_message) -> Optional[Dict[str, Any]]:
    """Build reply message information according to API spec with validation"""
    try:
        if not reply_message:
            logger.debug("No reply message provided")
            return None
            
        if not hasattr(reply_message, 'from_user') or not reply_message.from_user:
            logger.debug("Reply message has no from_user")
            return None

        reply_user = reply_message.from_user
        
        # Get reply text content (do not inject literal "Media" for media-only messages)
        reply_text = ""
        try:
            reply_text = await get_message_content(reply_message)
            if reply_text is None:
                reply_text = ""
        except Exception as e:
            logger.warning(f"Error getting reply text: {e}")
            reply_text = ""

        # Get reply entities
        reply_entities = []
        try:
            source_entities = reply_message.entities or reply_message.caption_entities
            if source_entities:
                reply_entities = await convert_entities(source_entities)
        except Exception as e:
            logger.warning(f"Error getting reply entities: {e}")

        # Get reply media preview (thumbnail/base64)
        reply_media = None
        try:
            reply_media = await get_media_info(client, reply_message)
        except Exception as e:
            logger.warning(f"Error getting reply media: {e}")

        # For media-only replies, use a whitespace placeholder to keep API payload valid.
        if not reply_text and reply_media:
            reply_text = " "

        # Build reply user info
        reply_user_info = await build_user_info(client, reply_user)
        if not reply_user_info:
            logger.warning("Failed to build reply user info")
            return None

        reply_info = {
            "name": reply_user_info.get("name") or reply_user_info.get("first_name", "Unknown"),
            "text": reply_text[:100],  # Limit reply text length
            "entities": reply_entities,
            "chatId": getattr(reply_message.chat, 'id', 0),
            "from": reply_user_info
        }

        if reply_media:
            reply_info["media"] = reply_media

        logger.debug(f"Reply info collected: {reply_info}")
        return reply_info

    except Exception as e:
        logger.error(f"Error building reply info: {e}")
        return None


async def convert_entities(entities) -> List[Dict[str, Any]]:
    """Convert Pyrogram entities to quote API format"""
    converted = []

    # Mapping of Pyrogram entity types to quote API types
    entity_type_mapping = {
        # Legacy mappings
        'MessageEntityBold': 'bold',
        'MessageEntityItalic': 'italic',
        'MessageEntityCode': 'code',
        'MessageEntityPre': 'pre',
        'MessageEntityTextUrl': 'text_link',
        'MessageEntityUrl': 'url',
        'MessageEntityMention': 'mention',
        'MessageEntityHashtag': 'hashtag',
        'MessageEntityBotCommand': 'bot_command',
        'MessageEntityStrike': 'strikethrough',
        'MessageEntityUnderline': 'underline',
        'MessageEntityCustomEmoji': 'custom_emoji',
        'MessageEntitySpoiler': 'spoiler',
        'MessageEntityCashtag': 'cashtag',
        'MessageEntityPhone': 'phone_number',
        'MessageEntityEmail': 'email',
        
        # Pyrogram v2 Enums
        'BOLD': 'bold',
        'ITALIC': 'italic',
        'CODE': 'code',
        'PRE': 'pre',
        'TEXT_LINK': 'text_link',
        'URL': 'url',
        'MENTION': 'mention',
        'HASHTAG': 'hashtag',
        'BOT_COMMAND': 'bot_command',
        'STRIKETHROUGH': 'strikethrough',
        'UNDERLINE': 'underline',
        'CUSTOM_EMOJI': 'custom_emoji',
        'SPOILER': 'spoiler',
        'CASHTAG': 'cashtag',
        'PHONE_NUMBER': 'phone_number',
        'EMAIL': 'email',
        'BLOCKQUOTE': 'blockquote',
        'TEXT_MENTION': 'text_mention'
    }

    try:
        for entity in entities:
            # Get entity type name — use enum's .name attr (e.g. CUSTOM_EMOJI) like main.py
            entity_type_name = ""
            if hasattr(entity, 'type'):
                if hasattr(entity.type, 'name'):
                    entity_type_name = entity.type.name
                elif hasattr(entity.type, '__name__'):
                    entity_type_name = entity.type.__name__
                else:
                    entity_type_name = str(entity.type).split('.')[-1].replace('>', '')

            # Map to quote API type
            api_type = entity_type_mapping.get(entity_type_name, 'text')

            entity_dict = {
                "type": api_type,
                "offset": entity.offset,
                "length": entity.length
            }

            # Add additional fields based on entity type
            if hasattr(entity, 'url') and entity.url:
                entity_dict["url"] = entity.url
            if hasattr(entity, 'custom_emoji_id') and entity.custom_emoji_id:
                entity_dict["custom_emoji_id"] = str(entity.custom_emoji_id)  # API requires string
            if hasattr(entity, 'language') and entity.language:
                entity_dict["language"] = entity.language

            converted.append(entity_dict)

    except Exception as e:
        logger.error(f"Error converting entities: {e}")

    return converted


async def generate_quote(client, payload: Dict[str, Any], user_dir: str) -> Optional[str]:
    """Generate quote using the API with proper error handling and fallback"""
    
    # List of endpoints to try in order
    endpoints = [
        'https://quote.nubcoders.com/generate',
        'http://quote-api:3000/generate',
        'http://127.0.0.1:3000/generate',
        'https://bot.lyo.su/quote/generate'
    ]
    
    for i, endpoint in enumerate(endpoints, 1):
        try:
            logger.debug(f"Attempting quote generation with endpoint {i}: {endpoint}")
            response = requests.post(endpoint, json=payload, timeout=30)
            response.raise_for_status()
            response_json = response.json()

            if not response_json.get('ok'):
                raise ValueError(f"API error: {response_json}")

            image_b64 = response_json.get('result', {}).get('image')
            if not image_b64:
                raise ValueError(f"Invalid API response, missing image: {response_json}")

            buffer = base64.b64decode(image_b64.encode('utf-8'))
            quote_path = f'{user_dir}/Quotly.webp'
            open(quote_path, 'wb').write(buffer)
            logger.info(f"Quote generated successfully using endpoint {i}")
            return quote_path
        except Exception as e:
            logger.warning(f"Quote generation error with endpoint {i} ({endpoint}): {e}")
            if i == len(endpoints):
                logger.error("All endpoints failed")
                return None
            else:
                logger.debug("Trying next endpoint...")
                continue
    
    return None
