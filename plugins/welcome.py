
import os
import base64
import re
from pyrogram import Client, filters
from tools import *
import magic

mime = magic.Magic(mime=True)

def rename_file(old_name, new_name):
    try:
        os.rename(old_name, new_name)
        new_file_path = os.path.abspath(new_name)
        print(f'File renamed from {old_name} to {new_name}')
        return new_file_path
    except FileNotFoundError:
        print(f'The file {old_name} does not exist.')
    except FileExistsError:
        print(f'The file {new_name} already exists.')
    except Exception as e:
        print(f'An error occurred: {e}')

async def convert_to_image(message, client):
    """Convert sticker to image format"""
    try:
        if message.sticker:
            file_path = await message.download()
            return file_path
        return None
    except Exception as e:
        print(f"Error converting sticker: {e}")
        return None

@Client.on_message(filters.command("setwelkm") & filters.private & filters.me)
async def set_welcome_handler(client, message):
    try:
        sender_id = message.from_user.id
        session_name = f'user_{client.me.id}'
        user_dir = f"{ggg}/{session_name}"
        os.makedirs(user_dir, exist_ok=True)

        replied_msg = message.reply_to_message
        if not replied_msg:
            usage_text = (
                "Please reply to a message to set it as welcome message.\n\n"
                "You can set:\n"
                "• Text message\n"
                "• Media (photo/video/gif/sticker)\n"
                "• Media with caption\n\n"
                "Available placeholders:\n"
                "• {name} - User's name\n"
                "• {id} - User's ID\n"
                "• {yourname} - Your name\n\n"
                "Size limits:\n"
                "• Text: Maximum 4096 characters\n"
                "• Media: Maximum 5MB\n\n"
                "Example usage:\n"
                "• 'Welcome {name}! Your ID is {id}'\n"
                "• Reply to a photo/video with caption 'Welcome to {botname}!'"
            )
            return await message.reply_text(usage_text)

        updates = []

        # Handle text if present
        if replied_msg.text or replied_msg.caption:
            text_obj = replied_msg.text or replied_msg.caption
            welcome_text = text_obj.strip()
            if len(welcome_text) > 4096:
                return await message.reply_text("Welcome message too long. Maximum 4096 characters allowed.")

            processed_text = text_obj.html

            # Validate placeholders
            ALLOWED_PLACEHOLDERS = {"{name}", "{id}", "{botname}"}
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
                error_msg += "• Welcome {name}!\n"
                error_msg += "• Your ID: {id}\n"
                error_msg += "• Welcome to {botname}!"
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
                file_size = getattr(replied_msg, 'file_size', 0)
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
                return await message.reply_text(f"Error processing media: {str(e)}")

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
<blockquote>{bold_cool(f"👋 Warm greetings, {'full_name'}! Welcome to my private message.")}</blockquote>

<blockquote>{bold_cool("Thank you for connecting with me. I am delighted to assist you. Kindly share the purpose of your message, and I will respond promptly. Your comfort is my priority.")}</blockquote>

<blockquote>{bold_cool("Please avoid excessive messaging, as it may lead to being blocked. Enjoy your time here!")}</blockquote>"""
            


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
            print(f"Error showing preview: {str(e)}")
            welcome_text = gvarstatus(sender_id, "WELCOME")
            if welcome_text:
                await client.send_message(
                    message.chat.id,
                    welcome_text,
                )

    except Exception as e:
        error_msg = f"❌ Error: `{str(e)}`"
        print(f"Error for user {message.from_user.id}: {str(e)}")
        return await message.reply_text(error_msg)

@Client.on_message(filters.command("resetwelkm") & filters.me)
async def reset_welcome_handler(client, message):
    user_id = message.from_user.id

    # Reset both LOGO and WELCOME
    unset_user_data(user_id, 'ALIVE_LOGO')
    unset_user_data(user_id, 'WELCOME')

    await message.edit("Welcome logo and message successfully reset")
