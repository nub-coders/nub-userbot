
import os
import base64
import re
from pyrogram import Client, filters
from tools import *
from utils.message import Msg
import magic
import logging


logger = logging.getLogger("welcome")
mime = magic.Magic(mime=True)

async def convert_to_image(message, client):
    """Convert sticker to image format"""
    try:
        if message.sticker:
            file_path = await message.download()
            return file_path
        return None
    except Exception as e:
        logger.warning(f"Error converting sticker: {e}")
        return None

@Client.on_message(filters.command("setwelkm", prefixes=HARDCODED_PREFIXES) & filters.private & filters.me)
async def set_welcome_handler(client, message):
    try:
        sender_id = message.from_user.id
        session_name = f'user_{client.me.id}'
        user_dir = session_name
        os.makedirs(user_dir, exist_ok=True)

        replied_msg = message.reply_to_message
        if not replied_msg:
            usage_guide = (
                f"<b>{Msg.EMOJI_WAVE} Welcome Message Configuration</b>\n\n"
                f"<blockquote>\n"
                f"<b>• <code>{{name}}</code>:</b> Recipient first name\n"
                f"<b>• <code>{{full_name}}</code>:</b> Recipient first + last name\n"
                f"<b>• <code>{{id}}</code>:</b> Recipient user Telegram ID\n"
                f"<b>• <code>{{yourname}}</code>:</b> Userbot owner display name\n"
                f"<b>• <code>{{botname}}</code>:</b> Same as <code>{{yourname}}</code>\n"
                f"</blockquote>\n\n"
                f"<i>Reply to any text or media message with <code>.setwelkm</code> to configure your DM greeting. The greeting is sent as a media caption, so the text may be at most 1024 characters. Maximum media size: 5MB.</i>"
            )
            return await message.reply_text(usage_guide, parse_mode=enums.ParseMode.HTML)



        updates = []

        # Handle text if present
        if replied_msg.text or replied_msg.caption:
            text_obj = replied_msg.text or replied_msg.caption
            welcome_text = text_obj.strip()
            # 1024, not 4096: the greeting always goes out as the caption of the
            # logo (see antyspam.py, which picks send_video/send_photo), and
            # Telegram caps captions at 1024 characters. Accepting 4096 here
            # meant a long greeting saved fine and then failed at send time.
            if len(welcome_text) > 1024:
                return await message.reply_text(
                    f"Welcome message too long ({len(welcome_text)} characters). "
                    "It is sent as a media caption, so Telegram allows at most 1024."
                )

            processed_text = text_obj.html

            # Validate placeholders
            # Single source of truth, shared with format_welcome_message() in
            # tools.py -- the two lists had drifted apart, so {botname} was
            # accepted but rendered literally and {full_name} was rejected even
            # though the live greeting path substituted it.
            ALLOWED_PLACEHOLDERS = set(WELCOME_PLACEHOLDERS)
            placeholder_regex = r'\{([^{}]+)\}'
            found_placeholders = set(re.findall(placeholder_regex, processed_text))

            invalid_placeholders = [f"{{{p}}}" for p in found_placeholders
                                  if f"{{{p}}}" not in ALLOWED_PLACEHOLDERS]

            if invalid_placeholders:
                error_msg = "❌ Invalid placeholders found:\n"
                error_msg += "\n".join(f"• {p}" for p in invalid_placeholders)
                error_msg += "\n\nAllowed placeholders:\n"
                error_msg += "\n".join(f"• {p}" for p in sorted(ALLOWED_PLACEHOLDERS))
                error_msg += "\n\nExample usage:\n"
                error_msg += "• Welcome {full_name}!\n"
                error_msg += "• Your ID: {id}\n"
                error_msg += "• You reached {yourname}!"
                return await message.reply_text(error_msg)

            set_gvar(sender_id, "WELCOME", processed_text)
            updates.append("welcome message")
            
        if replied_msg.media:
            m_d = None
            try:
                # Check if media type is allowed
                if not (replied_msg.photo or replied_msg.video or
                       replied_msg.sticker or replied_msg.animation):
                    return await message.reply_text("Only photos, videos, GIFs, and stickers are allowed.")

                # Check file size (5MB = 5 * 1024 * 1024 bytes)
                # file_size lives on the media object, not on Message -- the old
                # getattr(replied_msg, 'file_size', 0) always returned 0, so this
                # cap never once fired.
                media = (replied_msg.photo or replied_msg.video or
                         replied_msg.animation or replied_msg.sticker)
                file_size = getattr(media, "file_size", 0) or 0
                if file_size > 5242880:  # 5MB in bytes
                    return await message.reply_text("Media size cannot exceed 5MB.")

                # Process media based on type
                if replied_msg.sticker:
                    m_d = await convert_to_image(replied_msg, client)
                else:
                    m_d = await replied_msg.download()

                if m_d:
                    with open(m_d, "rb") as imageFile:
                        logo_data = base64.b64encode(imageFile.read())
                    os.remove(m_d)
                    set_gvar(sender_id, "ALIVE_LOGO", logo_data)
                    updates.append("logo")

            except Exception as e:
                if m_d and os.path.exists(m_d):
                    os.remove(m_d)
                # details= is the only styled_error argument that gets escaped,
                # and an exception string routinely carries paths and <...>.
                return await message.reply_text(styled_error("Error processing media", details=str(e)))

        if not updates:
            return await message.reply_text("Nothing to update. Message must contain text and/or media.")

        # Send confirmation and preview
        success_msg = f"✅ Updated {' and '.join(updates)}!"
        await client.send_message(message.chat.id, success_msg + "\n\nPreview:")

        # Show preview
        try:
            logo = gvarstatus(sender_id, "ALIVE_LOGO")
            if not logo and client.me.photo:
                photos = await client.get_profile_photos("me")
                if photos:
                    logo = await client.download_media(photos[0].file_id, f"{user_dir}/logo.jpg")
            if not logo:
                logo = "userbot.jpg"

            alive_logo = logo
            if isinstance(logo, bytes):
                alive_logo = f"{user_dir}/logo.jpg"
                with open(alive_logo, "wb") as fimage:
                    fimage.write(base64.b64decode(logo))
                if 'video' in mime.from_file(alive_logo):
                    alive_logo = rename_file(alive_logo, f"{user_dir}/logo.mp4")

            welcome_text = gvarstatus(sender_id, "WELCOME") or f"""
<blockquote>{bold_cool("👋 Warm greetings, {full_name}! Welcome to my private message.")}</blockquote>

<blockquote>{bold_cool("Thank you for connecting with me. I am delighted to assist you. Kindly share the purpose of your message, and I will respond promptly. Your comfort is my priority.")}</blockquote>

<blockquote>{bold_cool("Please avoid excessive messaging, as it may lead to being blocked. Enjoy your time here!")}</blockquote>"""

            # Render the placeholders so the preview shows what a visitor will
            # actually see instead of the raw template. The owner stands in for
            # the recipient here.
            me = client.me
            preview_full_name = f"{me.first_name or ''} {me.last_name or ''}".strip()
            welcome_text = await format_welcome_message(
                client, welcome_text, message.chat.id,
                me.first_name or "", full_name=preview_full_name
            )

            if alive_logo.endswith(".mp4"):
                await client.send_video(
                    message.chat.id,
                    alive_logo,
                    caption=welcome_text,
                )
            else:
                await client.send_photo(
                    message.chat.id,
                    alive_logo,
                    caption=welcome_text,
                )

        except Exception as e:
            logger.warning(f"Error showing preview: {e}")
            welcome_text = gvarstatus(sender_id, "WELCOME")
            if welcome_text:
                await client.send_message(
                    message.chat.id,
                    welcome_text,
                )

    except Exception as e:
        error_msg = styled_error("Welcome configuration failed", details=str(e))
        logger.warning(f"Welcome error for user {message.from_user.id}: {e}")
        return await message.reply_text(error_msg)

@Client.on_message(filters.command("resetwelkm", prefixes=HARDCODED_PREFIXES) & filters.me)
async def reset_welcome_handler(client, message):
    user_id = message.from_user.id

    # Reset both LOGO and WELCOME
    unset_user_data(user_id, 'ALIVE_LOGO')
    unset_user_data(user_id, 'WELCOME')

    await message.edit("Welcome logo and message successfully reset")
