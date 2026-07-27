# Core userbot plugin: message-save handler + auto media download.
# Help lives in help.py; ban/unban in moderation.py; the rest of this file's
# former contents were dead code and were removed.
import asyncio
import datetime
import logging
import os
import random
import re
import time

from pyrogram import Client, filters, enums
from pyrogram.errors import ChatForwardsRestricted, FileReferenceExpired
from pyrogram.types import Message

from tools import *
from utils.message import Msg

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)
logger = logging.getLogger("userbot")

current_time = datetime.datetime.now()
logger.info(f"[USERBOT] Plugin loaded at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

create_custom_filter = filters.create(lambda _, __, message: re.match(getuser_data(message.from_user.id).get("save_com", "^(Wow|wow)$"), message.text) if message.from_user else False)


def build_media_caption(from_user, chat, message, is_private, include_caption=True, recipient=None):
    """Build the '📥 Media Saved' caption/details block.

    :param is_private: whether the source chat is a private chat
    :param include_caption: append the original message caption/text if present
    :param recipient: if provided (and is_private), include recipient info
    """
    caption = f"📥 **Media Saved**\n\n"
    caption += f"👤 **From:** {from_user.first_name}"
    if from_user.last_name:
        caption += f" {from_user.last_name}"
    if from_user.username:
        caption += f" (@{from_user.username})"
    caption += f"\n🆔 **User ID:** `{from_user.id}`\n"

    if is_private:
        if recipient is not None:
            caption += f"\n👥 **To:** {recipient.first_name}"
            if recipient.last_name:
                caption += f" {recipient.last_name}"
            if recipient.username:
                caption += f" (@{recipient.username})"
            caption += f"\n🆔 **Recipient ID:** `{recipient.id}`\n"
        caption += f"💬 **Chat:** Private Chat\n"
    else:
        caption += f"💬 **Chat:** {chat.title or 'Unknown'}\n"
        if chat.username:
            caption += f"🔗 **Username:** @{chat.username}\n"

    caption += f"🆔 **Chat ID:** `{chat.id}`\n"
    caption += f"#️⃣ **Message ID:** `{message.id}`\n"

    if message.date:
        caption += f"📅 **Date:** {message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"

    if not is_private and chat.username:
        message_link = f"https://t.me/{chat.username}/{message.id}"
        caption += f"🔗 **Link:** {message_link}\n"

    if include_caption:
        original_text = message.text if message.caption is None else message.caption
        if original_text:
            caption += f"\n📝 **Caption:** {original_text}\n"

    return caption


@Client.on_message(filters.me & filters.text & create_custom_filter)
async def handle_message(client, message):
    sender = message.from_user.id
    session_name = f'user_{sender}'
    user_dir = session_name
    os.makedirs(user_dir, exist_ok=True)

    if message.reply_to_message:
        # Get the replied-to message
        try:
            target_message = message.reply_to_message
            from_user = target_message.from_user or client.me
            chat = target_message.chat
            is_private = str(chat.type).endswith("PRIVATE")

            # Optionally delete the triggering message to keep the chat clean
            try:
                await message.delete()
            except Exception:
                pass

            try:
                # Save to saved messages ("me") using the user client
                copied_msg = await target_message.copy("me")
                await asyncio.sleep(1)

                # Build detailed info about saved message
                details = build_media_caption(
                    from_user, chat, target_message,
                    is_private=is_private,
                    include_caption=False,
                )

                await client.send_message(
                    chat_id="me",
                    text=details,
                    reply_to_message_id=copied_msg.id
                )
            except (ChatForwardsRestricted, FileReferenceExpired):
                if target_message.media:
                    timer = Timer()
                    async def progress_bar(current, total, start_time=time.time()):
                        if timer.can_send() and total != 0:
                            progress_percent = current * 100 / total
                            filename = getattr(target_message.media, 'name', 'media')
                            progress_bar_length = 20
                            num_ticks = int(progress_percent / (100 / progress_bar_length))
                            progress_bar_text = '█' * num_ticks + '░' * (progress_bar_length - num_ticks)
                            elapsed_time = time.time() - start_time
                            speed = current / (elapsed_time * 1024 * 1024)
                            time_left = (total - current) / (speed * 1024 * 1024) if speed != 0 else 0
                            progress_message = (
                                f"{type_of} {filename}: {progress_percent:.2f}%\n"
                                f"Speed: {speed:.2f} MB/s\n"
                                f"Time left: {time_left:.2f} seconds\n"
                                f"Size: {current / (1024 * 1024):.2f} MB / {total / (1024 * 1024):.2f} MB\n"
                                f"[{progress_bar_text}]"
                            )
                            try:
                                if random.choices([True, False], weights=[1, 99])[0]:
                                    await msg.edit_text(progress_message)
                            except Exception as e:
                                logger.exception(f"Progress bar update error: {e}")

                    msg = await client.send_message("me", f"╭── 📥 DOWNLOADING ──╮\n┃ ⏳ Please wait...\n╰━━━━━━━━━━━━━━━━━━━━╯")
                    type_of = "Downloading"
                    file_path = await target_message.download(f"{user_dir}/", progress=progress_bar)
                    file_extension = file_path.split('.')[-1]
                    type_of = "Uploading"

                    # Build detailed caption with message info
                    caption = build_media_caption(
                        from_user, chat, target_message,
                        is_private=is_private,
                    )

                    if os.path.getsize(file_path) <= 2000000000:
                        if file_extension.lower() in ['jpg', 'jpeg', 'png', 'gif']:
                            await client.send_photo(chat_id="me", photo=file_path, caption=caption, progress=progress_bar)
                        elif file_extension.lower() in ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a']:
                            await client.send_audio(chat_id="me", audio=file_path, caption=caption, progress=progress_bar)
                        elif file_extension.lower() in ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv']:
                            thumb_path = f"{file_path}_thumb.jpg"
                            try:
                                generate_thumbnail(file_path, thumb_path)
                                duration = with_opencv(file_path)
                                await client.send_video(chat_id="me", video=file_path, caption=caption, progress=progress_bar, duration=duration, thumb=thumb_path)
                            except Exception as e:
                                logger.warning(f"Error generating thumbnail: {e}")
                                await client.send_video(chat_id="me", video=file_path, caption=caption, progress=progress_bar)
                            finally:
                                if os.path.exists(thumb_path):
                                    os.remove(thumb_path)
                        else:
                            await client.send_document("me", file_path, caption=caption, progress=progress_bar)
                    else:
                        await msg.edit_text(Msg.ERR_FILE_TOO_LARGE)
                    await msg.delete()
                    os.remove(file_path)
                else:
                    # Text message - send with details
                    details = f"📥 **Message Saved**\n\n"
                    details += f"👤 **From:** {from_user.first_name}"
                    if from_user.last_name:
                        details += f" {from_user.last_name}"
                    if from_user.username:
                        details += f" (@{from_user.username})"
                    details += f"\n🆔 **User ID:** `{from_user.id}`\n"

                    if is_private:
                        details += f"💬 **Chat:** Private Chat\n"
                    else:
                        details += f"💬 **Chat:** {chat.title or 'Unknown'}\n"
                        if chat.username:
                            details += f"🔗 **Username:** @{chat.username}\n"

                    details += f"🆔 **Chat ID:** `{chat.id}`\n"
                    details += f"#️⃣ **Message ID:** `{target_message.id}`\n"

                    if target_message.date:
                        details += f"📅 **Date:** {target_message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"

                    if not is_private and chat.username:
                        message_link = f"https://t.me/{chat.username}/{target_message.id}"
                        details += f"🔗 **Link:** {message_link}\n"

                    details += f"\n📝 **Text:**\n{target_message.text}"

                    await client.send_message("me", details)
        except Exception as e:
            try:
                await client.send_message("me", styled_error(f"Error: {e}"))
            except Exception:
                pass


@Client.on_message(filters.media & filters.private & ~filters.bot, group=1)
async def auto_download_media(client, message: Message):
    """
    Auto downloads media files less than 100MB and forwards to saved messages
    Only processes unread media from private chats
    """
    try:
        # Get sender information
        sender = message.from_user
        if not sender:
            return

        sender_id = sender.id
        is_self_message = str(sender_id) == str(client.me.id)

        # Create session directory
        session_name = f'user_{sender_id}'
        user_dir = session_name
        os.makedirs(user_dir, exist_ok=True)

        # Get media info using a mapping approach
        media_mapping = {
            'photo': message.photo,
            'video': message.video,
            'audio': message.audio,
            'voice': message.voice,
            'video_note': message.video_note,
            'animation': message.animation
        }

        # Find the media type and object
        media_type = None
        media_obj = None
        for m_type, m_obj in media_mapping.items():
            if m_obj:
                media_type = m_type
                media_obj = m_obj
                break

        if not media_obj:
            return  # No supported media found

        # Check file size (100MB limit)
        media_size = media_obj.file_size
        max_size = 100 * 1024 * 1024
        if media_size > max_size:
            logger.info(f"Skipping {media_type} from user {sender_id}: File size {media_size} bytes exceeds 100MB limit")
            return

        logger.info(f"Downloading {media_type} from user {sender_id} (Size: {media_size} bytes)")

        # Download the file
        file_path = await message.download(f"{user_dir}/")
        if not file_path:
            return

        logger.debug(f"Downloaded: {file_path}")

        # Build detailed caption with message info
        from_user = message.from_user
        chat = message.chat

        is_private = chat.type == enums.ChatType.PRIVATE

        # Caption for saved messages (without recipient info)
        caption_saved = build_media_caption(from_user, chat, message, is_private)

        # Caption for group/channel (with recipient info for private chats)
        caption_group = build_media_caption(
            from_user, chat, message, is_private, recipient=client.me
        )

        # Define send methods mapping
        target_client = apps.get("app") or client
        send_methods = {
            'photo': target_client.send_photo,
            'video': target_client.send_video,
            'audio': target_client.send_audio,
            'voice': target_client.send_voice,
            'video_note': target_client.send_video_note,
            'animation': target_client.send_animation
        }

        send_method = send_methods.get(media_type)
        if not send_method:
            return

        try:
            # Send to saved messages only if not self-message and media is unread
            if not is_self_message and message.unread_media:
                kwargs = {
                    'chat_id': client.me.id,
                    media_type: file_path
                }
                # Add caption for media types that support it
                if media_type not in ['video_note']:
                    kwargs['caption'] = caption_saved

                # Add thumbnail for videos
                if media_type == 'video':
                    thumb_path = f"{file_path}_thumb.jpg"
                    try:
                        generate_thumbnail(file_path, thumb_path)
                        duration = with_opencv(file_path)
                        kwargs['duration'] = duration
                        kwargs['thumb'] = thumb_path
                    except Exception as e:
                        logger.warning(f"Error generating thumbnail: {e}")

                await send_method(**kwargs)

                # Clean up thumbnail if created
                if media_type == 'video' and os.path.exists(thumb_path):
                    os.remove(thumb_path)

            # Send to main bot (app.me.id) if main_bot client exists
            app_client = apps.get("app")
            app_me_id = getattr(getattr(app_client, "me", None), "id", None) if app_client else None
            if app_me_id and app_me_id != client.me.id:
                kwargs = {
                    'chat_id': app_me_id,
                    media_type: file_path
                }
                if media_type not in ['video_note']:
                    kwargs['caption'] = caption_group

                if media_type == 'video':
                    thumb_path = f"{file_path}_thumb.jpg"
                    try:
                        generate_thumbnail(file_path, thumb_path)
                        duration = with_opencv(file_path)
                        kwargs['duration'] = duration
                        kwargs['thumb'] = thumb_path
                    except Exception as e:
                        logger.warning(f"Error generating thumbnail: {e}")

                await send_method(**kwargs)

                if media_type == 'video' and os.path.exists(thumb_path):
                    os.remove(thumb_path)

        except Exception as e:
            logger.error(f"Error sending {media_type}: {e}")

        # Clean up downloaded file
        try:
            os.remove(file_path)
            logger.debug(f"Deleted local file: {file_path}")
        except Exception as e:
            logger.warning(f"Error deleting file {file_path}: {e}")

    except Exception as e:
        logger.error(f"Error in auto_download_media handler: {e}")
