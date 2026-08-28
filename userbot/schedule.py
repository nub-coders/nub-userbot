
from pyrogram import Client, filters
from pyrogram.types import Message
import datetime
import pytz
from config import *
from tools import *
from utils.message import Msg

# Command handler for scheduling messages
@Client.on_message(filters.me & filters.command('schedule', prefixes=HARDCODED_PREFIXES))
@retry()
async def schedule_message(client: Client, message: Message):
    # Check if the command has the correct format
    command_parts = cmd_text(message).split(maxsplit=3)
    
    if len(command_parts) < 4:
        await message.reply("❌ **Invalid format!**\nUse: `/schedule <username/chatid> <time(HH:MM:SS or HH:MM:SS:CC)> <message>`")
        return
    
    # Extract components
    _, target, time_str, msg_content = command_parts
    
    # Validate time format (HH:MM:SS or HH:MM:SS:CC)
    hour = 0
    minute = 0
    second = 0
    centisecond = 0

    try:
        time_parts = time_str.split(':')
        if len(time_parts) == 4:
            parsed = datetime.datetime.strptime(':'.join(time_parts[:3]), "%H:%M:%S")
            if len(time_parts[3]) != 2:
                raise ValueError("centiseconds must be two digits")
            centisecond = int(time_parts[3])
        else:
            parsed = datetime.datetime.strptime(time_str, "%H:%M:%S")
        hour, minute, second = parsed.hour, parsed.minute, parsed.second
    except ValueError:
        await message.reply("❌ **Invalid time format!**\nUse HH:MM:SS or HH:MM:SS:CC format (24-hour), where CC is centiseconds (00-99).")
        return
    
    # Parse target (username or chat_id)
    chat_id = None
    try:
        # Check if target is numeric (chatid)
        if target.lstrip('-').isdigit():
            chat_id = int(target)
        else:
            # Handle username
            if not target.startswith("@"):
                target = f"@{target}"
            
            # Try to resolve username to chat_id
            try:
                chat = await client.get_chat(target)
                chat_id = chat.id
            except Exception as e:
                await message.reply(f"❌ **Error:** Could not find user/chat: {target}")
                return
    except Exception as e:
        await message.reply(f"❌ **Error:** {str(e)}")
        return
    
    # Get system's local timezone
    system_timezone = datetime.datetime.now().astimezone().tzinfo
    system_timezone_name = datetime.datetime.now().astimezone().tzname()
    
    # Get current time in system's timezone
    now = datetime.datetime.now(system_timezone)
    
    # Create the scheduled datetime with additional microseconds for centiseconds
    microseconds = centisecond * 10000  # Convert centiseconds to microseconds
    scheduled_time = now.replace(hour=hour, minute=minute, second=second, microsecond=microseconds)
    
    # If the scheduled time is in the past, schedule it for tomorrow
    if scheduled_time <= now:
        scheduled_time = scheduled_time + datetime.timedelta(days=1)
    
    # Convert to UTC for Telegram API (schedule_date needs to be in UTC)
    utc_time = scheduled_time.astimezone(pytz.UTC)
    
    try:
        # Schedule the message using Pyrogram's schedule_date parameter
        mess= await client.send_message(
            chat_id=chat_id,
            text=msg_content,
            schedule_date=utc_time
        )
        # Format time for display (include centiseconds if provided)
        if centisecond > 0:
            formatted_time = scheduled_time.strftime("%d-%m-%Y %H:%M:%S") + f".{centisecond:02d}"
        else:
            formatted_time = scheduled_time.strftime("%d-%m-%Y %H:%M:%S")
        
        # Send confirmation with standard MTProto HTML blockquote
        content_preview = (msg_content[:35] + '…') if len(msg_content) > 35 else msg_content
        # Escaped: target is whatever the sender typed and content_preview is
        # the message body, both going into HTML. A body containing tags used to
        # be silently mangled in the confirmation.
        schedule_html = (
            f"<b>{Msg.EMOJI_CALENDAR} Message Scheduled</b>\n\n"
            f"<blockquote>\n"
            f"<b>• Target:</b> <code>{html_esc(target)}</code>\n"
            f"<b>• Scheduled Time:</b> <code>{mess.date}</code>\n"
            f"<b>• Timezone:</b> {system_timezone_name}\n"
            f"<b>• Content:</b> {html_esc(content_preview)}\n"
            f"</blockquote>"
        )
        await message.reply(schedule_html, parse_mode=enums.ParseMode.HTML)


    except Exception as e:
        await message.reply(styled_error("Failed to schedule message", details=str(e)))


