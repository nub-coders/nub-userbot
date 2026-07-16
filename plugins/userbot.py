# Standard library imports
import asyncio
import ast
import base64
import certifi
import contextlib
import cv2
import datetime
import html
import imageio
import imageio_ffmpeg as ffmpeg
import inspect
import json
import logging
import math
import os
import pymongo
import pytesseract
import queue
import random
import re
import requests
import shlex
import shutil
import speedtest
import subprocess
import sys
import textwrap
import time
import traceback
import yt_dlp
from functools import wraps
from io import BytesIO, StringIO
from platform import python_version
from random import choice, randint
from typing import Any, Dict, List, Optional, Tuple, Union

# Third-party imports
import aiohttp
from google import genai
import pytz
from bson.objectid import ObjectId
from moviepy.editor import VideoFileClip, AudioFileClip
from PIL import Image, ImageDraw, ImageFont
from pymediainfo import MediaInfo
from pymongo import MongoClient
from pytz import timezone

# Pyrogram imports
import pyrogram
from pyrogram import Client, filters, enums, idle, __version__ as versipyro
from pyrogram.enums import ChatAction as CA, ChatMembersFilter, ChatMemberStatus, ChatType, MessageEntityType, MessageEntityType as MET, ParseMode, UserStatus
from pyrogram.errors import (
    ChatAdminRequired, FloodWait, RPCError, StickersetInvalid, UserAdminInvalid, 
    UserNotParticipant, UserRestricted, YouBlockedUser
)
from pyrogram.errors.exceptions import (
    AuthKeyDuplicated, AuthKeyUnregistered, ChatForwardsRestricted, FileReferenceExpired,
    MessageIdInvalid, PeerFlood, PeerIdInvalid, PremiumAccountRequired, SessionRevoked,
    UserDeactivated, UserDeactivatedBan
)
from pyrogram.errors.exceptions.bad_request_400 import PasswordHashInvalid, PhoneCodeInvalid
from pyrogram.errors.exceptions.unauthorized_401 import SessionPasswordNeeded
from pyrogram.handlers import DisconnectHandler, MessageHandler
from pyrogram.raw import functions
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.contacts import GetBlocked
from pyrogram.raw.functions.messages import GetFullChat, GetStickerSet
from pyrogram.raw.functions.phone import CreateGroupCall, DiscardGroupCall, GetCallConfig, JoinGroupCall, InviteToGroupCall
from pyrogram.raw.functions.users import GetFullUser
from pyrogram.raw.types import (
    DataJSON, InputGroupCall, InputPeerChannel, InputPeerChat, MessageEntityMentionName,
    MessageEntityTextUrl, InputStickerSetShortName
)
from pyrogram.types import (
    CallbackQuery, Chat, ChatPermissions, InlineKeyboardButton,
    InlineKeyboardMarkup, InlineQueryResultArticle, InputTextMessageContent, Message
)

# Compatibility: ChatPrivileges not available in Pyrogram 2.2.13
try:
    from pyrogram.types import ChatPrivileges
except ImportError:
    ChatPrivileges = ChatPermissions

# Telethon removed - using Pyrogram only

# PyTgCalls imports
from pytgcalls.exceptions import NoActiveGroupCall
from pytgcalls.types import ChatUpdate, Device, ExternalMedia

# Local imports
from convopyro import Conversation, listen_message
from tools import *
from utils.message import Msg
from youtube import handle_youtube, get_video_details, extract_video_id, format_number, format_duration, time_to_seconds
# Configure the logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

# Create a logger object
logger = logging.getLogger("userbot")
current_dir = f"{ggg}"

# Get the current date and time
current_time = datetime.datetime.now()
logger.info(f"[USERBOT] Plugin loaded at {current_time.strftime('%Y-%m-%d %H:%M:%S')}")

# Iterate over all sub-directories










# Store user's phone number
# Define client outside of any function scope

response_lock = asyncio.Lock()
IGNORE_DURATION = 5
# Define the /play command handler

# Run the bot


async def get_youtube_duration(youtube_link):
    ydl_opts = {
        'quiet': True, 
        'skip_download': True,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(youtube_link, download=False)
            duration = info.get('duration')  # Get duration in seconds 
            return duration
        except Exception as e:
            logger.error(f"[USERBOT] YouTube duration error: {e}")
            return None  # Or handle the error appropriately

# Helper function to split users into chunks


# Invite users to voice chat directly with the command handler

create_raid_filter = filters.create(
    lambda _, client, message: (
        message.from_user
        and message.from_user.id in getuser_data(client.me.id).get('raid_users', [])))

      
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
    user_dir = f"{ggg}/{session_name}"
    os.makedirs(user_dir, exist_ok=True)
    
    if message.reply_to_message:
        # Get the replied-to message
        try:
            message = message.reply_to_message
            if str(message.chat.type).endswith("PRIVATE"):
                chat_details = f"<b>{message.from_user.first_name} {message.from_user.last_name or ''}</b> @{message.chat.username or ''}"
            else:
                chat_title = message.chat.title
                chat_username = f"@{message.chat.username}" if message.chat.username else ""
                if message.chat.username:
                    message_link = f"https://t.me/{message.chat.username}/{message.id}"
                else:
                    message_id_str = str(message.chat.id).replace('-100', '')
                    message_link = f"https://t.me/c/{message_id_str}/{message.id}"
                chat_details = f"<b>{chat_title}</b> {chat_username} <a href='{message_link}'>Link to message</a>"
            
            try:
                message = await message.copy(app.me.username)
                await asyncio.sleep(2)
                
                # Build detailed info about saved message
                from_user = message.from_user
                chat = message.chat
                
                details = build_media_caption(
                    from_user, chat, message,
                    is_private=str(chat.type).endswith("PRIVATE"),
                    include_caption=False,
                )
                
                await app.send_message(
                    chat_id=sender,
                    text=details,
                    reply_to_message_id=message.id
                )
            except (ChatForwardsRestricted, FileReferenceExpired):
                if message.media:
                    timer = Timer()
                    async def progress_bar(current, total, start_time=time.time()):
                        if timer.can_send() and total != 0:
                            progress_percent = current * 100 / total
                            filename = getattr(message.media, 'name', 'media')
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
                                    await bot.edit_message(msg, progress_message)
                            except Exception as e:
                                logger.exception(f"Progress bar update error: {e}")
                    
                    msg = await bot.send_message(sender, f"╭── 📥 DOWNLOADING ──╮\n┃ ⏳ Please wait...\n╰━━━━━━━━━━━━━━━━━━━━╯")
                    type_of = "Downloading"
                    file_path = await message.download(f"{user_dir}/", progress=progress_bar)
                    file_extension = file_path.split('.')[-1]
                    type_of = "Uploading"
                    
                    # Build detailed caption with message info
                    from_user = message.from_user
                    chat = message.chat
                    
                    caption = build_media_caption(
                        from_user, chat, message,
                        is_private=str(chat.type).endswith("PRIVATE"),
                    )

                    if os.path.getsize(file_path) <= 2000000000:
                        if file_extension.lower() in ['jpg', 'jpeg', 'png', 'gif']:
                            await app.send_photo(chat_id=sender, photo=file_path, caption=caption, progress=progress_bar)
                        elif file_extension.lower() in ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a']:
                            await app.send_audio(chat_id=sender, audio=file_path, caption=caption, progress=progress_bar)
                        elif file_extension.lower() in ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv']:
                            thumb_path = f"{file_path}_thumb.jpg"
                            generate_thumbnail(file_path, thumb_path)
                            duration = with_opencv(file_path)
                            await app.send_video(chat_id=sender, video=file_path, caption=caption, progress=progress_bar, duration=duration, thumb=thumb_path)
                            os.remove(thumb_path)
                        else:
                            await app.send_document(sender, file_path, caption=caption, progress=progress_bar)
                    else:
                        await bot.edit_message(msg, Msg.ERR_FILE_TOO_LARGE)
                    await msg.delete()
                    os.remove(file_path)
                else:
                    # Text message - send with details
                    from_user = message.from_user
                    chat = message.chat
                    
                    details = f"📥 **Message Saved**\n\n"
                    details += f"👤 **From:** {from_user.first_name}"
                    if from_user.last_name:
                        details += f" {from_user.last_name}"
                    if from_user.username:
                        details += f" (@{from_user.username})"
                    details += f"\n🆔 **User ID:** `{from_user.id}`\n"
                    
                    if str(chat.type).endswith("PRIVATE"):
                        details += f"💬 **Chat:** Private Chat\n"
                    else:
                        details += f"💬 **Chat:** {chat.title or 'Unknown'}\n"
                        if chat.username:
                            details += f"🔗 **Username:** @{chat.username}\n"
                    
                    details += f"🆔 **Chat ID:** `{chat.id}`\n"
                    details += f"#️⃣ **Message ID:** `{message.id}`\n"
                    
                    if message.date:
                        details += f"📅 **Date:** {message.date.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    
                    if not str(chat.type).endswith("PRIVATE") and chat.username:
                        message_link = f"https://t.me/{chat.username}/{message.id}"
                        details += f"🔗 **Link:** {message_link}\n"
                    
                    details += f"\n📝 **Text:**\n{message.text}"
                    
                    await bot.send_message(sender, details)
        except Exception as e:
            await bot.send_message(sender, styled_error(f"Error: {e}"))

PASS=False








# Define a filter to handle outgoing messages containing the command "^info"
info_filter = filters.outgoing & filters.command("info", prefixes=HARDCODED_PREFIXES)




me_filter = (filters.me | sudoers_filter()) & filters.command("qt", prefixes=HARDCODED_PREFIXES)
@Client.on_message(me_filter)
async def duck_command_handler(client, message):
    """Enhanced quote command handler with better error handling and features"""
    USERBOT = await edit_or_reply(message, f"╭── 📝 QUOTE ──╮\n┃ ⏳ Generating quote...\n╰━━━━━━━━━━━━━━━━━━━━╯")

    # Check if the message is a reply
    if not message.reply_to_message:
        await USERBOT.edit_text(Msg.ERR_REPLY_TO_QUOTE)
        await asyncio.sleep(3)
        await USERBOT.delete()
        return

    try:
        sender = message.from_user.id
        replied_message = message.reply_to_message
        user = replied_message.from_user

        # Admin check
        if is_admin_user(user.id):
            return await USERBOT.edit_text(
                "You are fucking requesting me to create fake quote of my lord and my creator.\nSo I won't...**Fuck off!!**"
            )

        # Setup directories
        session_name = f'user_{sender}'
        user_dir = f"{ggg}/{session_name}"
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
        if not (force_custom and command_text):
            media_info = await get_media_info(client, replied_message)
        
        # Collect reply information (only if -r flag is present and reply exists)
        reply_info = None
        if include_reply and replied_message.reply_to_message:
            reply_info = await build_reply_info(client, replied_message.reply_to_message)
        
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
            await bot.send_message(client.me.id, f"ERROR in quote handler: {error_msg}")
            await USERBOT.edit_text(Msg.ERR_QUOTE_FAILED)
            await asyncio.sleep(3)
            await USERBOT.delete()
        except:
            pass  # If even error handling fails, just continue
        return

    max_retries = 2
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            # Send the sticker
            await client.send_sticker(
                chat_id=app.me.id,
                sticker=quote_path
            )
            await client.send_sticker(
                chat_id=message.chat.id,
                sticker=quote_path,
                reply_to_message_id=replied_message.id
            )
            await USERBOT.delete()
            return  # Success, exit the retry loop

        except PeerIdInvalid as e:
            retry_count += 1
            error_msg = f"PEER_ID_INVALID error (attempt {retry_count}/{max_retries}): {str(e)}"
            logger.warning(error_msg)
            
            if retry_count < max_retries:
                # Wait before retrying (exponential backoff)
                wait_time = 2 ** retry_count
                await USERBOT.edit_text(f"⚠️ Warning\n╰▸ Retrying... ({retry_count}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                # Max retries reached
                try:
                    await bot.send_message(client.me.id, f"ERROR in quote handler after {max_retries} retries: {error_msg}")
                    await USERBOT.edit_text(Msg.ERR_QUOTE_RETRIES_FAILED)
                    await asyncio.sleep(3)
                    await USERBOT.delete()
                except:
                    pass
                return

        except Exception as e:
            error_msg = f"Quote send error: {str(e)}"
            logger.error(error_msg)
            try:
                await bot.send_message(client.me.id, f"ERROR in quote handler: {error_msg}")
                await USERBOT.edit_text(Msg.ERR_QUOTE_FAILED)
                await asyncio.sleep(3)
                await USERBOT.delete()
            except:
                pass  # If even error handling fails, just continue
            return  # Exit on non-PEER_ID_INVALID errors


async def build_user_info(client, user) -> Optional[Dict[str, Any]]:
    """Build user information according to API spec with comprehensive error handling"""
    try:
        if not user:
            logger.debug("No user object provided")
            return None
            
        user_info = {
            "id": user.id
        }
        
        # Handle name - use name field or first_name/last_name
        try:
            if user.first_name and user.last_name:
                user_info["first_name"] = user.first_name
                user_info["last_name"] = user.last_name
            elif user.first_name:
                user_info["first_name"] = user.first_name
            elif user.username:
                user_info["username"] = user.username
                user_info["name"] = f"@{user.username}"
            else:
                user_info["name"] = "Unknown User"
        except Exception as e:
            logger.warning(f"Error processing username info: {e}")
            user_info["name"] = "Unknown User"
        
        # Handle profile photo
        try:
            if hasattr(user, 'photo') and user.photo:
                if hasattr(user.photo, 'big_file_id') and user.photo.big_file_id:
                    user_info["photo"] = {"big_file_id": user.photo.big_file_id}
                elif hasattr(user.photo, 'small_file_id') and user.photo.small_file_id:
                    user_info["photo"] = {"big_file_id": user.photo.small_file_id}
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



def upload_file_data_binary_to_bashupload(file_path, file_name=None):
    """
    Uploads a file to bashupload.com using the --data-binary method and returns the download URL.

    Args:
        file_path (str): The path to the file to upload.
        file_name (str, optional): The desired name for the file on bashupload.com. 
                                   If None, the original file name will be used.

    Returns:
        str: The download URL of the uploaded file, or None if the upload fails.
    """
    if not os.path.exists(file_path):
        return None

    if file_name is None:
        file_name = os.path.basename(file_path)

    url = f'https://bashupload.com/{file_name}'
    
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(url, data=f)
        
        if response.status_code == 200:
            match = re.search(r'wget (https://bashupload.com/[^\s]+)', response.text)
            if match:
                return match.group(1)
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"An error occurred during bashupload: {e}")
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

    # Get media type from message.media.value
    media_type = message.media.value if hasattr(message.media, 'value') else None
    logger.debug(f"[DEBUG] Raw media_type: {media_type}")

    if not media_type:
        logger.debug("[DEBUG] No media_type found")
        return None

    # Convert media type to attribute name (remove "MessageMediaType." prefix if present)
    if media_type.startswith('MessageMediaType.'):
        media_attr = media_type.replace('MessageMediaType.', '').lower()
        logger.debug(f"[DEBUG] Converted media_attr from MessageMediaType: {media_attr}")
    else:
        media_attr = media_type.lower()
        logger.debug(f"[DEBUG] Converted media_attr (no prefix): {media_attr}")

    # Get the media object using getattr
    media_obj = getattr(message, media_attr, None)
    logger.debug(f"[DEBUG] Media object retrieved: {media_obj}")

    if not media_obj:
        logger.debug(f"[DEBUG] No media object found for type: {media_attr}")
        return None

    # Get thumbnail file_id using the simplified approach
    logger.debug(f"[DEBUG] Attempting to get thumbnail from media_attr: {media_attr}")
    try:
        media_attribute = getattr(message, media_attr)
        logger.debug(f"[DEBUG] Media attribute object: {media_attribute}")
        
        thumbs = getattr(media_attribute, 'thumbs', None)
        logger.debug(f"[DEBUG] Thumbs attribute: {thumbs}")
        
        if thumbs and len(thumbs) > 0:
            thumbnail_file_id = thumbs[0].file_id
            logger.debug(f"[DEBUG] Thumbnail file_id found: {thumbnail_file_id}")
        else:
            logger.debug(f"[DEBUG] No thumbs found or thumbs is empty")
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
        user_dir = f"{ggg}/{session_name}"
        logger.debug(f"[DEBUG] User directory: {user_dir}")
        
        os.makedirs(user_dir, exist_ok=True)
        logger.debug(f"[DEBUG] User directory created/verified")

        # Create temporary file in user directory
        logger.debug(f"[DEBUG] Downloading media with file_id: {thumbnail_file_id}")
        temp_file_path = await client.download_media(message=thumbnail_file_id, file_name=f"{user_dir}/")
        logger.debug(f"[DEBUG] Media downloaded to: {temp_file_path}")

        # Upload to bashupload
        logger.debug(f"[DEBUG] Uploading file to bashupload: {temp_file_path}")
        upload_url = upload_file_data_binary_to_bashupload(temp_file_path)
        logger.debug(f"[DEBUG] Upload result: {upload_url}")

        if upload_url:
            logger.debug(f"[DEBUG] Media thumbnail uploaded successfully: {upload_url}")
            return {"url": upload_url}
        else:
            logger.debug("[DEBUG] Failed to upload thumbnail to bashupload")
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
        return f"📍 Location"

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
        
        # Get reply text content
        reply_text = ""
        try:
            reply_text = reply_message.text or reply_message.caption or "Media"
        except Exception as e:
            logger.warning(f"Error getting reply text: {e}")
            reply_text = "Media"

        # Get reply entities
        reply_entities = []
        try:
            if hasattr(reply_message, 'entities') and reply_message.entities:
                reply_entities = await convert_entities(reply_message.entities)
        except Exception as e:
            logger.warning(f"Error getting reply entities: {e}")

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
        'https://bot.lyo.su/quote/generate',
        'https://quote.nubcoders.com/generate',
        'http://quote-api:3000/generate',
        'http://127.0.0.1:3000/generate'
    ]
    
    for i, endpoint in enumerate(endpoints, 1):
        try:
            logger.debug(f"Attempting quote generation with endpoint {i}: {endpoint}")
            response = requests.post(endpoint, json=payload).json()
            buffer = base64.b64decode(response['result']['image'].encode('utf-8'))
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























# ═══════════════════════════════════════
#  .help <command> — Styled Help Handler
# ═══════════════════════════════════════

def _parse_help_entry(raw_text):
    """Parse a raw help entry into structured fields."""
    desc = usage = example = note = warning = flags = ""
    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        ll = line.lower()
        if ll.startswith("**usage:**"):
            usage = line.split("**Usage:**", 1)[-1].strip()
        elif ll.startswith("**example:**"):
            example = line.split("**Example:**", 1)[-1].strip()
        elif ll.startswith("**examples:**"):
            example = line.split("**Examples:**", 1)[-1].strip()
        elif ll.startswith("**flags:**"):
            flags = line.split("**Flags:**", 1)[-1].strip()
        elif ll.startswith("**note:**"):
            note = line.split("**Note:**", 1)[-1].strip()
        elif ll.startswith("**warning:**"):
            warning = line.split("**Warning:**", 1)[-1].strip()
        elif ll.startswith("**features:**"):
            note = line.split("**Features:**", 1)[-1].strip()
        elif ll.startswith("**options:**"):
            flags = line.split("**Options:**", 1)[-1].strip()
        elif ll.startswith("**supported:**"):
            note = line.split("**Supported:**", 1)[-1].strip()
        elif " - " in line and not desc:
            desc = line.split(" - ", 1)[-1].strip()
    if not desc and lines:
        first = lines[0].strip().strip("*")
        if " - " in first:
            desc = first.split(" - ", 1)[-1].strip()
        else:
            desc = first
    return desc, usage, example, note, warning, flags


@Client.on_message(filters.command("help", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def help_handler(client, message):
    """Shows detailed command usage — .help <command> or .help for categories overview"""
    try:
        # Detect user's prefix from the message
        prefix = message.text[0] if message.text else "."

        raw_args = get_args(message)

        # get_args returns list, False, or string
        if isinstance(raw_args, list):
            args = " ".join(raw_args).strip().lower()
        elif isinstance(raw_args, str):
            args = raw_args.strip().lower()
        else:
            args = ""

        # No arguments → show categories overview
        if not args:
            await edit_or_reply(message, styled_help_categories(categories, prefix))
            return

        # Search for the command in the global commands dict
        cmd_name = args.split()[0].lstrip("".join(HARDCODED_PREFIXES))

        if cmd_name in commands:
            raw = commands[cmd_name]
            desc, usage, example, note, warning, flags = _parse_help_entry(raw)

            # Replace [prefix] placeholder with user's actual prefix
            usage = usage.replace("[prefix]", prefix)
            example = example.replace("[prefix]", prefix)
            flags = flags.replace("[prefix]", prefix)

            card = styled_help_card(
                cmd_name, desc, usage,
                example=example, note=note, flags=flags, warning=warning
            )
            await edit_or_reply(message, card)
            return

        # Fuzzy search — check if it's a partial match
        matches = [c for c in commands if cmd_name in c or c in cmd_name]
        if matches:
            match_list = ", ".join(f"`{prefix}{m}`" for m in matches[:10])
            await edit_or_reply(
                message,
                f"{Msg.WARN_CMD_NOT_FOUND}\n\n"
                f"┃ 🔍 Did you mean?\n"
                f"┃  {match_list}\n"
                f"╰━━━━━━━━━━━━━━━━━━━━╯"
            )
            return

        # Nothing found at all
        await edit_or_reply(
            message,
            f"Unknown Command\n\n"
            f"┃ {f'No help found for: {cmd_name}'}\n"
            f"┃ 💡 {f'Use {prefix}help to see all categories'}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯"
        )

    except Exception as e:
        logger.error(f"[HELP] Error: {e}")
        await edit_or_reply(message, styled_error(f"Help error: {str(e)[:50]}"))





# Function to get a user's specific data from MongoDB

# Function to set a user's specific data in MongoDB
def set_user_data(user_id, key, value):
    user_sessions.update_one({"user_id": user_id}, {"$set": {key: value}}, upsert=True)

# Update functions to interact with MongoDB






def unset_user_data(user_id, key):
    user_sessions.update_one({"user_id": user_id}, {"$unset": {key: ''}}, upsert=True)




    





# Assuming you have already initialized your MongoDB client and database






# Assuming you have already initialized your MongoDB client and database



















# Define the handler for category button presses





# Add handler with filter










async def get_response(message, client):
    return [x async for x in client.get_chat_history("Stickers", limit=1)][0].text




def random_chance(false_probability=0.1):

    # Generate a random number between 0 and 1
    random_value = random.random()

    # Return False if the random value is less than the false probability
    if random_value < false_probability:
        return False
    else:
        return True










is_support = filters.create(lambda _, __, message: message.chat.is_support)
















# Your existing get_arg function

# Active chats list - imported from config as dictionary

# Check if user was active in last 3 days




@Client.on_message(filters.media & filters.private & ~filters.bot)
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
        user_dir = f"{ggg}/{session_name}"
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
        send_methods = {
            'photo': app.send_photo,
            'video': app.send_video,
            'audio': app.send_audio,
            'voice': app.send_voice,
            'video_note': app.send_video_note,
            'animation': app.send_animation
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









def is_game_enabled():
    """
    Decorator to check if the game is enabled for the user before executing the function.
    Uses the games dictionary for fast lookup instead of database query.
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(client, message):
            try:
                logger.debug(f"[GAME_CHECK] Checking game status for user {client.me.id}")
                
                # Check games dictionary instead of database
                game_enabled = games.get(client.me.id, False)
                logger.debug(f"[GAME_CHECK] Game enabled: {game_enabled}")
                
                if not game_enabled:
                    logger.debug(f"[GAME_CHECK] Game is disabled for user {client.me.id}, skipping execution")
                    return
                    
                return await func(client, message)
                
            except Exception as e:
                logger.error(f"[ERROR] Error in game check decorator: {e}")
                # If there's an error checking, assume game is disabled and skip
                return
        
        return wrapper
    return decorator



# Compile regex pattern once for better performance
RESPONSE_PATTERN = re.compile(r"(is accepted\.|has been used\.|is not)")
WORD_INFO_PATTERN = re.compile(r"Your word must start with (.+)")
WORD_LENGTH_PATTERN = re.compile(r'\d+')



async def extract_first_mention(message: Message, text: str):
    """
    Extract the first mention after "Turn:" from the message
    """
    try:
        logger.debug(f"[MENTION] Extracting mentions from message")
        entities = message.entities or []
        
        if not entities:
            logger.debug(f"[MENTION] No entities found in message")
            return None
            
        turn_index = text.index("Turn:")
        logger.debug(f"[MENTION] 'Turn:' found at index {turn_index}")
        
        for i, entity in enumerate(entities):
            logger.debug(f"[MENTION] Entity {i}: type={entity.type}, offset={entity.offset}")
            
            if entity.type == enums.MessageEntityType.TEXT_MENTION and entity.offset > turn_index:
                logger.debug(f"[MENTION] Found valid mention: user_id={entity.user.id}")
                return entity.user
                
        logger.debug(f"[MENTION] No valid mention found after 'Turn:'")
        return None
        
    except Exception as e:
        logger.error(f"[ERROR] Error extracting mention: {e}")
        return None


async def extract_word_requirements(text: str):
    """
    Extract word requirements from the message text
    """
    try:
        logger.debug(f"[REQUIREMENTS] Extracting word requirements")
        
        word_info_match = WORD_INFO_PATTERN.search(text)
        if not word_info_match:
            logger.debug(f"[REQUIREMENTS] No word info pattern found")
            return None
            
        word_info_line = word_info_match.group(1)
        logger.debug(f"[REQUIREMENTS] Word info line: {word_info_line}")
        
        # Extract capital letters and word length
        capital_letters = re.findall(r'[A-Z]', word_info_line)
        word_length_match = WORD_LENGTH_PATTERN.search(word_info_line)
        
        if not word_length_match:
            logger.debug(f"[REQUIREMENTS] No word length found")
            return None
            
        word_length = int(word_length_match.group())
        logger.debug(f"[REQUIREMENTS] Found {len(capital_letters)} capital letters, word length: {word_length}")
        
        # Determine requirements based on capital letters
        if len(capital_letters) == 1:
            start_letter = capital_letters[0]
            include_letter = None
        elif len(capital_letters) == 2:
            start_letter = capital_letters[0]
            include_letter = capital_letters[1]
        else:
            logger.debug(f"[REQUIREMENTS] Invalid number of capital letters: {len(capital_letters)}")
            return None
            
        return start_letter, word_length, include_letter
        
    except Exception as e:
        logger.error(f"[ERROR] Error extracting requirements: {e}")
        return None



async def attempt_word_submission(client, chat_id: int, filtered_words: list, used_words_list: list, max_attempts: int = 5):
    """
    Attempt to submit a valid word with retry logic
    """
    logger.info(f"[SUBMISSION] Starting word submission attempts (max: {max_attempts})")
    
    for attempt in range(max_attempts):
        logger.debug(f"[SUBMISSION] Attempt {attempt + 1}/{max_attempts}")
        
        # Select unused word
        selected_word = await select_unused_word(filtered_words, used_words_list)
        if not selected_word:
            logger.debug(f"[SUBMISSION] No unused word found on attempt {attempt + 1}")
            continue
            
        logger.info(f"[SUBMISSION] Selected word: '{selected_word}'")
        
        # Send the word
        try:
            await asyncio.sleep(4)  # Wait before sending
            logger.debug(f"[SUBMISSION] Sending typing action")
            await client.send_chat_action(chat_id, enums.ChatAction.TYPING)
            
            logger.info(f"[SUBMISSION] Sending word: '{selected_word}'")
            await client.send_message(chat_id, selected_word)
            
            # Add to used words immediately
            used_words_list.append(selected_word)
            logger.debug(f"[SUBMISSION] Added '{selected_word}' to used words")
            
        except Exception as e:
            logger.error(f"[ERROR] Error sending message: {e}")
            continue
            
        # Wait for response
        response_result = await wait_for_response(client, chat_id, selected_word)
        
        if response_result == "accepted":
            logger.info(f"[SUBMISSION] Word '{selected_word}' was accepted!")
            return True
        elif response_result == "rejected":
            logger.info(f"[SUBMISSION] Word '{selected_word}' was rejected, trying next word")
            continue
        elif response_result == "format_error":
            logger.warning(f"[SUBMISSION] Format error detected - stopping attempts")
            return False
        else:
            logger.debug(f"[SUBMISSION] No response received for '{selected_word}', trying next word")
            continue
            
    logger.warning(f"[SUBMISSION] All attempts exhausted")
    return False


async def select_unused_word(filtered_words: list, used_words_list: list, max_tries: int = 10):
    """
    Select a random word that hasn't been used yet
    """
    logger.debug(f"[WORD_SELECT] Selecting unused word from {len(filtered_words)} candidates")
    logger.debug(f"[WORD_SELECT] Already used {len(used_words_list)} words in this chat")
    
    for try_num in range(max_tries):
        random_word = random.choice(filtered_words)
        logger.debug(f"[WORD_SELECT] Try {try_num + 1}: checking '{random_word}'")
        
        if random_word not in used_words_list:
            logger.debug(f"[WORD_SELECT] Found unused word: '{random_word}'")
            return random_word
        else:
            logger.debug(f"[WORD_SELECT] Word '{random_word}' already used")
            
    logger.warning(f"[WORD_SELECT] No unused word found after {max_tries} tries")
    return None


async def wait_for_response(client, chat_id: int, submitted_word: str, timeout: int = 4):
    """
    Wait for bot response and determine if word was accepted
    """
    logger.debug(f"[RESPONSE] Waiting for response to '{submitted_word}' (timeout: {timeout}s)")
    
    try:
        response = await client.listen.Message(
            filters.regex(RESPONSE_PATTERN) & filters.user("on9wordchainbot") & filters.chat(chat_id),
            timeout=timeout
        )
        
        logger.debug(f"[RESPONSE] Received response: {response.text}")
        
        response_lower = response.text.lower()
        
        # Check for rejection reasons first
        if "does not start with" in response_lower or "does not include" in response_lower:
            logger.info(f"[RESPONSE] Word rejected - incorrect format, stopping attempts")
            return "format_error"
        
        if not response.entities:
            logger.debug(f"[RESPONSE] No entities in response")
            return "no_entities"
            
        # Check italic text for our word
        for entity in response.entities:
            if entity.type == enums.MessageEntityType.ITALIC:
                italic_text = response.text[entity.offset:entity.offset + entity.length]
                logger.debug(f"[RESPONSE] Found italic text: '{italic_text}'")
                
                if submitted_word.lower() in italic_text.lower():
                    logger.info(f"[RESPONSE] Our word found in italic text")
                    
                    if "is not" in response_lower or "has been used." in response_lower:
                        logger.info(f"[RESPONSE] Word was rejected")
                        return "rejected"
                    elif "is accepted." in response_lower:
                        logger.info(f"[RESPONSE] Word was accepted")
                        return "accepted"
                        
        logger.debug(f"[RESPONSE] Our word not found in response or status unclear")
        return "unclear"
        
    except asyncio.TimeoutError:
        logger.warning(f"[RESPONSE] Timeout waiting for response")
        return "timeout"
    except Exception as e:
        logger.error(f"[ERROR] Error waiting for response: {e}")
        return "error"









# Configure logging










@Client.on_message(filters.command("banall", prefixes=HARDCODED_PREFIXES) & filters.me)
async def inline_handler_ban(client, message):
    try:
        # Get inline bot results
        results = await client.get_inline_bot_results(app.me.username, query=f"banall {message.chat.id}")

        if results.results:
            # Get the first result ID
            first_result_id = results.results[0].id

            # Send the first inline result
            await client.send_inline_bot_result(
                chat_id=message.chat.id,
                query_id=results.query_id,
                result_id=first_result_id
            )
        else:
            await message.reply(Msg.ERR_NO_INLINE_RESULTS)
    except Exception as e:
        await message.reply(styled_error(f"Error: {e}"))

@Client.on_message(filters.command("unbanall", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def unban_all_users(client, message):
    """Unban all users from the chat without confirmation"""
    try:
        await delete_if_self(message)
        
        chat_id = message.chat.id
        
        # Check if user has admin permissions
        try:
            
            member = await client.get_chat_member(chat_id, client.me.id)
            if member.status == ChatMemberStatus.ADMINISTRATOR and not member.privileges.can_restrict_members:
                await client.send_message(
                    chat_id,
                    Msg.ERR_UNBAN_PERMISSION
                )
                return
                
        except Exception as e:
            await client.send_message(chat_id, styled_error(f"Permission check failed: {str(e)}"))
            return
        
        # Get chat info
        chat = await client.get_chat(chat_id)
        
        # Send initial status message
        status_msg = await client.send_message(
            chat_id,
            f"🔄 {f'Starting unban for {chat.title}...'}"
        )
        
        unbanned_count = 0
        failed_count = 0
        
        try:
            await status_msg.edit(f"🔄 Unbanning users...")
            
            total_processed = 0
            
            # Unban users directly during iteration
            async for member in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.BANNED):
                if not member.user:
                  continue
                total_processed += 1
                
                try:
                    await client.unban_chat_member(chat_id, member.user.id)
                    unbanned_count += 1
                    
                    # Update progress every 10 unbans
                    if total_processed % 10 == 0:
                        progress_message = f"""🔄 Unban in progress...

📊 Processed: {total_processed}
✅ Unbanned: {unbanned_count}
❌ Failed: {failed_count}
📈 Success Rate: {(unbanned_count/total_processed)*100:.1f}%"""
                        
                        try:
                            await status_msg.edit(progress_message)
                        except:
                            pass  # Ignore edit rate limits
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to unban user {member.user.id}: {e}")
                    continue
            
            if total_processed == 0:
                await status_msg.edit(Msg.INFO_NO_BANNED_USERS)
                return
            
            # Final result
            final_message = f"""✅ Unban All Completed

📊 **Results:**
👥 Total Processed: {total_processed}
✅ Successfully Unbanned: {unbanned_count}
❌ Failed to Unban: {failed_count}
📈 Success Rate: {(unbanned_count/total_processed)*100:.1f}%

🎉 All eligible users have been unbanned from {chat.title}"""
            
            await status_msg.edit(final_message)
            
        except Exception as e:
            await status_msg.edit(styled_error(f"Unban error: {str(e)}"))
            
    except Exception as e:
        try:
            await client.send_message(
                message.chat.id, 
                styled_error(f"Unban all failed: {str(e)}")
            )
        except:
            pass
# Run the userbot
# Create the custom filter









# Add the disconnect handler







# Command handler for scheduling messages




# Message templates with proper HTML escaping
RUNNING = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Running...</b>"
ERROR = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Error:</b>\n<pre>{}</pre>"
SUCCESS = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Success</b>"
RESULT = "<b>Eval Expression:</b>\n<pre>{}</pre>\n<b>Result:</b>\n<pre>{}</pre>"





# Gemini config (key lives in config.py)
from config import GEMINI_API_KEY, BOT_TOKEN
API_KEY = GEMINI_API_KEY
MODEL = "gemini-2.0-flash"

# Initialize the Gemini client (google-genai SDK)
gemini_client = genai.Client(api_key=API_KEY) if API_KEY else None

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Rate limiting
COOLDOWN_SECONDS = 10  # Minimum seconds between requests

# Command-to-Model Mapping
DEFAULT_MAX_TOKENS = 1200

ai_commands = {
    "chat": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "You are a helpful assistant."
    },
    "reason": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "You are a logical reasoning assistant. Analyze problems step-by-step."
    },
    "summarize": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Summarize the following text concisely while preserving all key information."
    },
    "translate": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Translate the following text accurately, maintaining the original meaning and tone."
    },
    "code": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "You are a programming assistant. Generate clear, efficient, and well-commented code."
    },
    "write": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Create well-structured, engaging content based on the given topic or requirements."
    },
    "analysis": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Analyze the following information in detail, identifying patterns, insights, and implications."
    },
    "answer": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Provide accurate, well-researched answers to the following question."
    },
    "complete": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Complete the following text in a natural and contextually appropriate way."
    },
    "extract": {
        "max_tokens": DEFAULT_MAX_TOKENS,
        "system_prompt": "Extract the most important information, data points, and insights from the following text."
    },
}












# Telegram command handler

# Help command (keep your existing help command)








def capitalize_first_letter(text):
    return text[0].upper() + text[1:] if text else text











# Assuming you have initialized the app with pyrogram









































# Userbot.py Commands and Categories
userbot_commands = {
    'me': '**User Status** - Check your userbot status, current points, and account information.\n\n**Usage:** `[prefix]me` or `[prefix]me [user_id]`\n**Example:** `[prefix]me` or reply to a message with `[prefix]me`',
    'addsudo': '**Admin Control** - Add a user to the sudoers list with elevated permissions.\n\n**Usage:** `[prefix]addsudo [user_id/@username]` or reply to message\n**Example:** `[prefix]addsudo 123456789` or reply with `[prefix]addsudo`',
    'rmsudo': '**Admin Control** - Remove a user from the sudoers list.\n\n**Usage:** `[prefix]rmsudo [user_id/@username]` or reply to message\n**Example:** `[prefix]rmsudo 123456789` or reply with `[prefix]rmsudo`',
    'listsudo': '**Admin Control** - List all users in the sudoers list with their user IDs and total count.\n\n**Usage:** `[prefix]listsudo`',
    'acceptall': '**Group Management** - Accept all pending group invite requests at once.\n\n**Usage:** `[prefix]acceptall`\n**Note:** Works in groups where you have admin permissions',
    'ocr': '**Text Recognition** - Extract text from images using OCR technology.\n\n**Usage:** `[prefix]ocr` (reply to an image)\n**Example:** Reply to a screenshot with `[prefix]ocr`',
    'vc1': '**Voice Chat** - Start a group voice chat to enable voice communication.\n\n**Usage:** `[prefix]vc1`\n**Note:** Requires admin permissions in the group',
    'vc0': '**Voice Chat** - End the active group voice chat.\n\n**Usage:** `[prefix]vc0`\n**Note:** Requires admin permissions in the group',
    'ban': '**User Management** - Ban a user from the chat with optional message deletion.\n\n**Usage:** `[prefix]ban [reply|@username|user_id] [-d/--delete]`\n**Example:** `[prefix]ban @spammer -d` (bans and deletes messages)',
    'banall': '**User Management** - Ban all users from the chat (use with caution).\n\n**Usage:** `[prefix]banall`\n**Warning:** This will ban all members except admins',
    'unbanall': '**User Management** - Unban all previously banned users from the chat.\n\n**Usage:** `[prefix]unbanall`\n**Note:** Restores access for all banned users',
    'kick': '**User Management** - Remove a user from the chat (they can rejoin).\n\n**Usage:** `[prefix]kick [reply|@username|user_id]`\n**Example:** `[prefix]kick @troublemaker`',
    'mute': '**User Management** - Mute a user to prevent them from sending messages.\n\n**Usage:** `[prefix]mute [reply|@username|user_id] [-m/--media]`\n**Example:** `[prefix]mute @spammer -m` (media-only mute)',
    'unban': '**User Management** - Unban a previously banned user from the chat.\n\n**Usage:** `[prefix]unban [reply|@username|user_id]`\n**Example:** `[prefix]unban @user123`',
    'promote': '**User Management** - Promote a user with specific admin privileges.\n\n**Usage:** `[prefix]promote [reply|@username|user_id] [flags] [title]`\n**Flags:** -all (all privileges), -d (delete), -r (restrict), -i (invite), -p (pin), -c (change info), -v (video chats), -t (topics), -m (manage)\n**Example:** `[prefix]promote @user -d -r -i Moderator`',
    'pin': '**Message Management** - Pin a message to the top of the chat.\n\n**Usage:** `[prefix]pin [-s/--sound]` (reply to message)\n**Example:** `[prefix]pin -s` (pins with notification sound)',
    'unpin': '**Message Management** - Unpin the currently pinned message.\n\n**Usage:** `[prefix]unpin`\n**Note:** Removes the pinned message from the top',

    'qt': '**Quote Generator** - Create beautiful quotes from messages with custom formatting.\n\n**Usage:** `[prefix]qt [-r] [-f custom_text]` (reply to message)\n**Example:** `[prefix]qt -r` (includes reply), `[prefix]qt -f "Custom quote"`',
    'setalivetext': '**Alive Customization** - Set custom text for your userbot\'s alive status.\n\n**Usage:** `[prefix]setalivetext [text]` or reply to message\n**Example:** `[prefix]setalivetext I am online and ready!`',
    'alive': '**Status Check** - Check if your userbot is alive and operational.\n\n**Usage:** `[prefix]alive`\n**Note:** Shows current status and uptime information',
    'resetallalive': '**Alive Reset** - Reset all alive settings (text, emoji) to default values.\n\n**Usage:** `[prefix]resetallalive`\n**Note:** Removes all custom alive configurations',
    'approve': '**User Approval** - Approve a user in private chat, granting them access.\n\n**Usage:** `[prefix]approve` (in private chat)\n**Note:** Adds user to whitelist, prevents auto-blocking',
    'disapprove': '**User Disapproval** - Remove a user from approved list, they will be blocked after 5 messages.\n\n**Usage:** `[prefix]disapprove` (in private chat)\n**Note:** Removes user from whitelist',
    'rmall': '**Bulk Management** - Remove all users from the approved users list.\n\n**Usage:** `[prefix]rmall`\n**Warning:** This will remove all approved users',
    'rst': '**Message Reset** - Reset message count for a specific user in private chat.\n\n**Usage:** `[prefix]rst` (in private chat)\n**Note:** Resets their message counter to 0',
    'rstall': '**Bulk Reset** - Reset message counts for all users in private chats.\n\n**Usage:** `[prefix]rstall`\n**Warning:** This will reset all user message counters',
    'setemoji': '**Alive Customization** - Set a custom emoji for your userbot\'s alive status.\n\n**Usage:** `[prefix]setemoji [emoji]`\n**Example:** `[prefix]setemoji 🚀`',
    'tiny': '**Image Resizer** - Reduce image size by replying to any photo or sticker.\n\n**Usage:** `[prefix]tiny` (reply to image/sticker)\n**Note:** Compresses images while maintaining quality',
    'mmf': '**Image Text** - Add custom text to images by replying to any media.\n\n**Usage:** `[prefix]mmf [text]` (reply to image)\n**Example:** `[prefix]mmf Hello World` (reply to photo)',
    'kang': '**Sticker Cloner** - Clone and save stickers, videos, or photos to your collection.\n\n**Usage:** `[prefix]kang [pack_name] [emoji]` (reply to media)\n**Example:** `[prefix]kang MyPack 😀` (reply to sticker)',
    'ping': '**Ping Test** - Check bot response time and connection status.\n\n**Usage:** `[prefix]ping`\n**Note:** Shows latency and response time',
    'stats': '**Account Statistics** - View detailed statistics about your account and bot usage.\n\n**Usage:** `[prefix]stats`\n**Features:** User count, group count, message stats, uptime',
    'clone': '**Profile Cloner** - Clone another user\'s profile (name, bio, profile picture).\n\n**Usage:** `[prefix]clone [user_id/@username]`\n**Example:** `[prefix]clone @target_user`',
    'revert': '**Profile Restore** - Restore your original profile details after cloning.\n\n**Usage:** `[prefix]revert`\n**Note:** Undoes the last cloning operation',
    'raid': '**User Raid** - Initiate a raid on a specific user with multiple messages.\n\n**Usage:** `[prefix]raid [count] [user_id/@username]`\n**Example:** `[prefix]raid 10 @spammer`\n**Warning:** Use responsibly',
    'dmspam': '**DM Spam** - Spam a user in their personal messages (DM) - works in groups.\n\n**Usage:** `[prefix]dmspam [count] [message]` (reply to user)\n**Example:** Reply to a user and use `[prefix]dmspam 5 Hello`\n**Note:** Only works in group chats, sends messages to user\'s DM',
    'dmraid': '**DM Raid** - Raid a user in their personal messages (DM) with random raid messages.\n\n**Usage:** `[prefix]dmraid [count]` (reply to user)\n**Example:** Reply to a user and use `[prefix]dmraid 10`\n**Note:** Only works in group chats, sends raid messages to user\'s DM',
    'wordseek': '**WordSeek Auto-Play** - Show WordSeek auto-play info and trigger words.\n\n**Usage:** `[prefix]wordseek`\n**Note:** Use any trigger word to start auto-play',
    'gameinfo': '**WordSeek Game Info** - Show current WordSeek auto-game status and hints.\n\n**Usage:** `[prefix]gameinfo`\n**Note:** Works only when an auto-game is active',
    'invite2vc': '**Voice Chat Invite** - Invite all group members to join the voice chat.\n\n**Usage:** `[prefix]invite2vc`\n**Note:** You must be in the voice chat first',
    'spam': '**Message Spam** - Send multiple messages at once with controlled timing.\n\n**Usage:** `[prefix]spam [count] [message]`\n**Example:** `[prefix]spam 5 Hello World`\n**Warning:** Use responsibly',
    'statspam': '**Smart Spam** - Spam with 0.1s delay and auto-delete old messages.\n\n**Usage:** `[prefix]statspam [count] [message]`\n**Example:** `[prefix]statspam 10 Test message`',
    'slowspam': '**Slow Spam** - Spam messages with 2-second delay between each message.\n\n**Usage:** `[prefix]slowspam [count] [message]`\n**Example:** `[prefix]slowspam 5 Slow message`',
    'fastspam': '**Fast Spam** - Spam messages with no delay (maximum speed).\n\n**Usage:** `[prefix]fastspam [count] [message]`\n**Example:** `[prefix]fastspam 20 Fast message`\n**Warning:** Very fast, use carefully',
    'dspam': '**Delayed Spam** - Spam messages with custom delay between messages.\n\n**Usage:** `[prefix]dspam [count] [delay_seconds] [message]`\n**Example:** `[prefix]dspam 10 3 Delayed message`',
    'afk': '**AFK Mode** - Set yourself as away from keyboard with a reason.\n\n**Usage:** `[prefix]afk [reason]`\n**Example:** `[prefix]afk Going to sleep`\n**Note:** Auto-replies when mentioned',
    'unafk': '**AFK Return** - Return from AFK mode and resume normal activity.\n\n**Usage:** `[prefix]unafk`\n**Note:** Disables AFK auto-replies',
    'tagall': '**Member Tagging** - Tag group members with various filtering options.\n\n**Usage:** `[prefix]tagall [options] [message]`\n**Options:** -adm (admins only), -act (active users), -(1-4) (limit users), -usr (users without admins)\n**Example:** `[prefix]tagall -adm Hello admins!`',
    'cancel': '**Tagging Cancel** - Cancel ongoing member tagging operation.\n\n**Usage:** `[prefix]cancel`\n**Note:** Stops the current tagging process',
    'calc': '**Calculator** - Perform mathematical calculations with support for advanced functions.\n\n**Usage:** `[prefix]calc <expression>`\n**Supported:** Basic math (+, -, *, /, %, **), trigonometry (sin, cos, tan), logarithms (log, log10), square root (sqrt), constants (pi, e)\n**Examples:**\n• `[prefix]calc 2 + 2`\n• `[prefix]calc sqrt(144)`\n• `[prefix]calc sin(pi/2)`\n• `[prefix]calc 2**8`\n**Note:** Use `[prefix]calc` without arguments for full help',
    'gemini': '**AI Commands** - Access Google Gemini AI for various tasks.\n\n**Available Commands:**\n• `[prefix]chat` - General conversation\n• `[prefix]reason` - Logical problem-solving\n• `[prefix]summarize` - Text summarization\n• `[prefix]translate` - Language translation\n• `[prefix]code` - Code generation/fixing\n• `[prefix]write` - Content creation\n• `[prefix]analysis` - Data analysis\n• `[prefix]answer` - Q&A responses\n• `[prefix]complete` - Text completion\n• `[prefix]extract` - Information extraction\n\n**Usage:** `[prefix]command [text]` or reply to message\n**Example:** `[prefix]chat Hello, how are you?`',
        'chat': '**AI Chat** - Have a general conversation with Gemini AI.\n\n**Usage:** `[prefix]chat [text]` or reply to message\n**Example:** `[prefix]chat Hello, how are you?`',
        'reason': '**AI Reasoning** - Get logical problem-solving and reasoning from Gemini AI.\n\n**Usage:** `[prefix]reason [text]` or reply to message\n**Example:** `[prefix]reason Why is the sky blue?`',
        'summarize': '**AI Summarize** - Summarize long text into concise form.\n\n**Usage:** `[prefix]summarize [text]` or reply to message\n**Example:** Reply to a long message with `[prefix]summarize`',
        'translate': '**AI Translate** - Translate text to another language.\n\n**Usage:** `[prefix]translate [text]` or reply to message\n**Example:** `[prefix]translate Translate this to Spanish: Hello`',
        'code': '**AI Code** - Generate or fix code with AI assistance.\n\n**Usage:** `[prefix]code [description]` or reply to message\n**Example:** `[prefix]code Write a Python function to sort a list`',
        'write': '**AI Write** - Create content, essays, or articles.\n\n**Usage:** `[prefix]write [topic]` or reply to message\n**Example:** `[prefix]write Write a poem about nature`',
        'analysis': '**AI Analysis** - Analyze data, text, or situations.\n\n**Usage:** `[prefix]analysis [text]` or reply to message\n**Example:** `[prefix]analysis Analyze this market trend`',
        'answer': '**AI Answer** - Get direct answers to questions.\n\n**Usage:** `[prefix]answer [question]` or reply to message\n**Example:** `[prefix]answer What is quantum computing?`',
        'complete': '**AI Complete** - Complete partial text or sentences.\n\n**Usage:** `[prefix]complete [text]` or reply to message\n**Example:** `[prefix]complete Once upon a time`',
        'extract': '**AI Extract** - Extract specific information from text.\n\n**Usage:** `[prefix]extract [text]` or reply to message\n**Example:** `[prefix]extract Extract all email addresses from this text`',
    'schedule': '**Message Scheduler** - Schedule messages to be sent at specific date and time (IST).\n\n**Usage:** `[prefix]schedule [date] [time] [message]`\n**Example:** `[prefix]schedule 2024-01-01 12:00 Happy New Year!`',
    'purge': '**Message Purge** - Delete all messages from replied message to the last message.\n\n**Usage:** `[prefix]purge` (reply to starting message)\n**Warning:** This will delete all messages in the range',
    'set': '**Quick Settings** - Open settings menu in inline chat format.\n\n**Usage:** `[prefix]set`\n**Note:** Quick access to bot settings',
    'gcast': '**Global Broadcast** - Broadcast message to all chats (private/group/all).\n\n**Usage:** `[prefix]gcast [-pvt/-grp/-all] [message]` or reply to message\n**Example:** `[prefix]gcast -all Hello everyone!`',
    'addbl': '**Broadcast Blocklist** - Add chat to broadcast blocklist to exclude from broadcasts.\n\n**Usage:** `[prefix]addbl [chat_id]` or use in target chat\n**Example:** `[prefix]addbl -1001234567890`',
    'rmbl': '**Broadcast Unblock** - Remove chat from broadcast blocklist.\n\n**Usage:** `[prefix]rmbl [chat_id]` or use in target chat\n**Example:** `[prefix]rmbl -1001234567890`',
    'blist': '**Blocklist View** - Show all chats in the broadcast blocklist.\n\n**Usage:** `[prefix]blist`\n**Note:** Displays blocked chat IDs and names',
    'clr': '**Game Reset** - Clear used words from the word chain game.\n\n**Usage:** `[prefix]clr`\n**Note:** Resets the word chain game memory',
    'replyraid': '**Reply Raid** - Activate reply raid on a specific user.\n\n**Usage:** `[prefix]replyraid [user_id/@username]` or reply to message\n**Example:** `[prefix]replyraid @target_user`\n**Warning:** Use responsibly',
    'dreplyraid': '**Reply Raid Stop** - Deactivate reply raid on a specific user.\n\n**Usage:** `[prefix]dreplyraid [user_id/@username]` or reply to message\n**Example:** `[prefix]dreplyraid @target_user`',
    'sg': '**User History** - Get user history using @SangMata_beta_bot.\n\n**Usage:** `[prefix]sg` (reply to user message)\n**Note:** Shows username and name history',
    'del': '**Message Delete** - Delete the replied message.\n\n**Usage:** `[prefix]del` (reply to message)\n**Note:** Removes the specific message',
    'delall': '**Bulk Delete** - Delete all messages from the replied user.\n\n**Usage:** `[prefix]delall` (reply to user message)\n**Warning:** Deletes all messages from that user',
    'gemini_help': '**AI Help** - Get detailed information about Gemini AI commands.\n\n**Usage:** `[prefix]gemini_help`\n**Note:** Shows all available AI commands and examples',
    'pingurl': '**URL Ping** - Measure response time for a specific URL.\n\n**Usage:** `[prefix]pingurl [url]`\n**Example:** `[prefix]pingurl https://google.com`\n**Default:** Tests Google if no URL provided',
    'tcp': '**TCP Test** - Test TCP connectivity to a host and port.\n\n**Usage:** `[prefix]tcp <host> <port>`\n**Example:** `[prefix]tcp google.com 80`\n**Note:** Tests network connectivity',
    'speed': '**Speed Test** - Run comprehensive network speed test.\n\n**Usage:** `[prefix]speed`\n**Features:** Download/upload speed, latency, connection quality',
    'info': '**User Information** - Get detailed information about a user.\n\n**Usage:** `[prefix]info` (reply to message) or `[prefix]info [user_id/@username]`\n**Example:** Reply to a message with `[prefix]info`',
    'admins': '**Admin List** - List all group admins with their last message information.\n\n**Usage:** `[prefix]admins`\n**Note:** Shows admin list with activity status',
    'sessions': '**Session Info** - List all active sessions with detailed connection information.\n\n**Usage:** `[prefix]sessions`\n**Note:** Shows active userbot sessions and their status',
    'unmute': '**User Unmute** - Unmute a previously muted user.\n\n**Usage:** `[prefix]unmute [reply|@username|user_id]`\n**Example:** `[prefix]unmute @user123`',
    'eval': '**Code Evaluation** - Execute Python code safely.\n\n**Usage:** `[prefix]eval [code]`\n**Example:** `[prefix]eval print("Hello World")`\n**Warning:** Use with caution',
    'help': '**Help System** - View command details and category overview.\n\n**Usage:** `[prefix]help` (show all categories) or `[prefix]help <command>`\n**Example:** `[prefix]help ban`\n**Note:** Works with any command name',
    'react': '**Auto React** - Control automatic emoji reactions when mentioned.\n\n**Usage:** `[prefix]react <on/off/emoji_number>`\n**Options:** `on` (enable), `off` (disable), `1`-`4` (select emoji)\n**Example:** `[prefix]react on`',
    'reactlist': '**React Emojis** - Show available reaction emojis.\n\n**Usage:** `[prefix]reactlist`\n**Note:** Displays emoji options for react command',
    'unpin': '**Unpin Message** - Unpin a pinned message in the group.\n\n**Usage:** `[prefix]unpin` (reply to pinned msg) or `[prefix]unpin --all`\n**Example:** `[prefix]unpin --all` (unpin all messages)',
    'calc': '**Calculator** - Evaluate mathematical expressions.\n\n**Usage:** `[prefix]calc <expression>`\n**Supported:** +, -, *, /, %, **, sqrt, sin, cos, tan, log, pi, e\n**Example:** `[prefix]calc sqrt(144) + sin(pi/2)`',
}

userbot_categories = {
    '👤 USER INFO': ['info', 'sg', 'me', 'stats', 'sessions'],
    '🔄 PROFILE': ['clone', 'revert'],
    '💾 MEDIA SAVER': ['wow', 'link'],
    '🎨 STICKERS & MEDIA': ['qt', 'tiny', 'mmf', 'kang'],
    '🔍 TEXT RECOGNITION': ['ocr'],
    '💚 ALIVE STATUS': ['alive', 'setemoji', 'setalivetext', 'resetallalive'],
    '🗑️ MESSAGE MANAGEMENT': ['purge', 'del', 'delall'],

    '👋 WELCOME SYSTEM': ['approve', 'disapprove', 'rmall', 'rst', 'rstall'],
    '📢 BROADCASTING': ['gcast', 'addbl', 'rmbl', 'blist'],
    '👑 GROUP MANAGEMENT': ['ban', 'banall', 'unbanall', 'kick', 'mute', 'unmute', 'unban', 'promote', 'pin', 'unpin', 'admins', 'acceptall'],
    '⚙️ BOT SETTINGS': ['set'],
    '🎤 VOICE CHAT': ['vc0', 'vc1', 'invite2vc'],
    '🏷️ MEMBER TAGGING': ['tagall', 'cancel'],
    '⚔️ RAID & SPAM': ['raid', 'dmspam', 'dmraid', 'replyraid', 'dreplyraid', 'spam', 'dspam', 'statspam', 'slowspam', 'fastspam'],
    '⏰ SCHEDULING': ['schedule'],
    '👑 ADMIN CONTROL': ['addsudo', 'rmsudo', 'listsudo'],
    '🤖 AI COMMANDS': [],
    '🎮 GAMES': ['clr', 'wordseek', 'gameinfo'],
    '😴 AFK SYSTEM': ['afk', 'unafk'],
    '🌐 NETWORK TOOLS': ['ping', 'pingurl', 'tcp', 'speed', 'calc'],
    '⚙️ DEVELOPMENT': ['eval'],
    '💬 REACTIONS': ['react', 'reactlist'],
    '📖 HELP': ['help'],
}

# Update global commands and categories
commands.update(userbot_commands)
categories.update(userbot_categories)
