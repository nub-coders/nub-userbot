
import os
from pyrogram import Client, filters
from pyrogram.errors import ChatForwardsRestricted, FileReferenceExpired, MessageIdInvalid, FloodWait
from pyrogram import enums
from config import *
from tools import *

import logging
logger = logging.getLogger("gcast")

@Client.on_message(filters.command("gcast", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def gcast_handler(client, message):
    """Handles the /gcast command."""
    session_name = f'user_{client.me.id}'
    user_dir = session_name
    os.makedirs(user_dir, exist_ok=True)
    user_id = client.me.id
    user_data = user_sessions.find_one({"user_id": user_id}) or {}
    # None here meant `dialog.chat.id in admin_ids` raised TypeError for every
    # dialog when the admin file was absent, which is the default.
    admin_ids = []
    if os.path.exists(admin_file):
       with open(admin_file, "r") as file:
          admin_ids = [int(line.strip()) for line in file.readlines()]
    try:
        parts = cmd_text(message).split(maxsplit=2)
        flag = parts[1].lower()
        logger.debug(f"gcast flag: {flag}")
        text_or_file = parts[2] if len(parts) > 2 else None  #handles cases with no message
        file = None
        reply_msg = message.reply_to_message
        if reply_msg:
            text_or_file = reply_msg.text if reply_msg.text else None # handles replies that have just media
            file = reply_msg.media

        if not text_or_file and not file:
            return await message.edit("Nothing given to Gcast.")
        try:
           message_to_cast = await reply_msg.copy(app.me.username) if reply_msg else await client.send_message(app.me.id, text_or_file)
        except (ChatForwardsRestricted, FileReferenceExpired, MessageIdInvalid):
           if not (reply_msg and reply_msg.media):
               return await message.edit(styled_error("That message cannot be copied for broadcast."))
           # The body is plain text whose formatting lives in separate entities,
           # so anything angle-bracketed in it was read as a tag and dropped.
           caption = html_esc(reply_msg.caption if reply_msg.caption is not None else (reply_msg.text or ""))
           await message.edit( "Downloading media/document......")
           file_path=await reply_msg.download(f"{user_dir}/")
           file_extension = file_path.split('.')[-1]
           # The download used to be deleted only on the over-2GB path, so every
           # successful gcast of restricted media left a copy in user_<id>/ --
           # and the generated thumbnail only went away if send_video returned.
           thumb_path = None
           try:
               if os.path.getsize(file_path) > 2100000000:
                   return await message.edit("Cannot operate on a file larger than 2GB")
               if file_extension in ['jpg', 'jpeg', 'png', 'gif']:
                   message_to_cast = await client.send_photo(chat_id=app.me.id, photo=file_path, caption=caption)
               elif file_extension in ['mp3', 'wav', 'ogg', 'flac', 'aac', 'm4a']:
                   message_to_cast = await client.send_audio(chat_id=app.me.id, audio=file_path, caption=caption)
               elif file_extension in ['mp4', 'mov', 'avi', 'mkv', 'webm', 'wmv']:
                   thumb_path = f"{file_path}_thumb.jpg"
                   generate_thumbnail(file_path, thumb_path)
                   duration=with_opencv(file_path)
                   message_to_cast = await client.send_video(chat_id=app.me.id, video=file_path, caption=caption, duration=duration,thumb=thumb_path)
               else:
                   message_to_cast = await client.send_document(app.me.id, file_path, caption=caption)
           finally:
               for leftover in (thumb_path, file_path):
                   if leftover and os.path.exists(leftover):
                       os.remove(leftover)
        except FloodWait as e:
            # This slept and fell through with message_to_cast never assigned, so
            # the loop below died on NameError and the command reported itself as
            # "Broadcast failed: name 'message_to_cast' is not defined".
            return await message.edit(styled_error(
                f"Telegram asked for a {e.value}s wait before staging the broadcast.",
                hint="Run the command again once it has passed.",
            ))
        except Exception as e:
            return await message.edit(styled_error("Could not stage the broadcast message", details=e))
        blocked_list = user_data.get("blocked_list", [])
        await message.reply("Gcasting message...")
        sed = 0
        owo = 0
        bl = 0
        async for dialog in client.get_dialogs():
          if flag in ["-all", "-pvt", "-grp"]:
            if dialog.chat.id in blocked_list or dialog.chat.id in admin_ids:
                bl +=1
                continue
            should_send = (
                flag == "-all"
                or (flag == "-pvt" and dialog.chat.type == enums.ChatType.PRIVATE)
                or (flag == "-grp" and dialog.chat.type in [enums.ChatType.GROUP, enums.ChatType.SUPERGROUP])
            )
            if not should_send:
                continue
            try:
                await message_to_cast.copy(dialog.chat.id)
                owo += 1
            except Exception as e:
                sed += 1
          else:
                return await message.edit(
                "Please provide gcast flag. \n\nAvailable options: \n• -all : To Gcast in all chats. \n• -pvt : To Gcast in private chats. \n• -grp : To Gcast in groups."
            )


        UwU = sed + owo
        omk = {"-all": "Chats", "-pvt": "PMs", "-grp": "Groups"}.get(flag, "Chats")
        rate = (owo / UwU * 100) if UwU else 0

        result_text = (
            f"<b>📢 Broadcast Completed</b>\n\n"
            f"<blockquote>\n"
            f"<b>• Target Scope:</b> {omk} (<code>{flag}</code>)\n"
            f"<b>• Delivered:</b> {owo}\n"
            f"<b>• Failed:</b> {sed}\n"
            f"<b>• Skipped (Blacklisted):</b> {bl}\n"
            f"<b>• Total Processed:</b> {UwU}\n"
            f"<b>• Success Rate:</b> {rate:.1f}%\n"
            f"</blockquote>"
        )
        await message.edit(result_text, parse_mode=enums.ParseMode.HTML)
        await client.send_message(app.me.id, f"#GCAST #{flag[1:].upper()} \n\nDelivered: {owo} | Failed: {sed} | Total: {UwU}")


    except IndexError:
        await message.edit(styled_error("Missing arguments", hint="Usage: <code>/gcast [-all|-pvt|-grp] [message/reply]</code>"), parse_mode=enums.ParseMode.HTML)
    except Exception as e:
        await message.edit(styled_error("Broadcast failed", details=e), parse_mode=enums.ParseMode.HTML)

