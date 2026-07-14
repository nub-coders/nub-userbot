
from pyrogram import Client, filters
from config import *
from tools import *

@Client.on_message(filters.outgoing & filters.command("info"))
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

    # Build the full info message
    full_info_message = (f"User Info:\n"
                         f"User ID: {user_id}\n"
                         f"Name: {first_name} {last_name}\n"
                         f"Username: @{username}\n"
                         f"Total Messages by User: {user_message_count}\n"
                         f"Chat Info:\n"
                         f"Chat ID: {chat_id}\n"
                         f"Chat Title: {chat_title}\n"
                         f"Total Messages in Chat: {total_messages}\n"
                         f"User Join Date: {join_date}")

    # Edit the initial reply with the complete information
    await reply_message.edit_text(full_info_message)
