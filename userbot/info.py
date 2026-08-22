
from pyrogram import Client, filters
from pyrogram.types import Message
from config import *
from tools import *

# Define a filter to handle outgoing messages containing the command "/info"
info_filter = filters.outgoing & filters.command("info", prefixes=HARDCODED_PREFIXES)

@Client.on_message(info_filter)
@retry()
async def info_command_handler(client, message):
    # Check if there is an argument after the command
    args = message.text.split(maxsplit=1)
    if len(args) > 1:
        # An argument is provided, try to fetch user info by chat_id or username
        target = args[1]
        
        # Attempt to resolve the argument to a user
        try:
            if target.isdigit():
                user = await client.get_users(int(target))  # Handle as user_id if it's numeric
            else:
                user = await client.get_users(target)  # Handle as username
        except Exception as e:
            return await message.reply_text(f"Could not find user: {target}. Error: {e}")
    else:
        # No argument, use the user in the message context
        user = message.reply_to_message.from_user if message.reply_to_message else message.from_user

    # Extract user details
    user_id = user.id
    first_name = user.first_name or ""
    last_name = user.last_name or ""
    username = user.username or ""

    # Initial reply with basic information
    initial_info_message = f"User Info:\nUser ID: {user_id}\nName: {first_name} {last_name}"
    reply_message = await message.reply_text(initial_info_message)

    # Fetch additional information
    user_message_count = await client.search_messages_count(message.chat.id, from_user=user_id)
    total_messages = await client.search_messages_count(message.chat.id)

    chat = message.chat
    chat_id = chat.id
    chat_title = chat.title if chat.title else "N/A"

    # User's join date (if in a group)
    member_info = await client.get_chat_member(chat_id, user_id) if str(chat.type).endswith(('GROUP', 'SUPERGROUP')) else None
    join_date = member_info.joined_date if member_info else "Unknown"

    # Build the full info message with native HTML table
    username_display = f"@{username}" if username else "<i>None</i>"
    full_name = f"{first_name} {last_name}".strip() or "<i>Anonymous</i>"

    info_table = (
        f"<b>👤 User Information</b>\n\n"
        f"<blockquote>\n"
        f"<b>• Name:</b> {full_name}\n"
        f"<b>• Username:</b> {username_display}\n"
        f"<b>• User ID:</b> <code>{user_id}</code>\n"
        f"<b>• Messages Sent:</b> {user_message_count}\n"
        f"</blockquote>\n\n"
        f"<b>💬 Chat Information</b>\n\n"
        f"<blockquote>\n"
        f"<b>• Title:</b> {chat_title}\n"
        f"<b>• Chat ID:</b> <code>{chat_id}</code>\n"
        f"<b>• Total Messages:</b> {total_messages}\n"
        f"<b>• Joined Date:</b> {str(join_date)[:19] if join_date else 'N/A'}\n"
        f"</blockquote>"
    )

    # Edit the initial reply with the complete information
    await reply_message.edit_text(info_table, parse_mode=enums.ParseMode.HTML)



