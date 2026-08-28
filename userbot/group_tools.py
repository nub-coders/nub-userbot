
import asyncio
import shlex
from random import randint
from pyrogram import Client, filters, enums
from pyrogram.types import ChatPrivileges, Message
from pyrogram.errors import UserRestricted, PeerFlood
from pyrogram.raw.functions.channels import GetFullChannel
from pyrogram.raw.functions.messages import GetFullChat
from pyrogram.raw.functions.phone import CreateGroupCall, InviteToGroupCall
from pyrogram.raw.types import InputPeerChannel, InputPeerChat
from config import *
from tools import *

import logging
logger = logging.getLogger("group_tools")

# ponytail: inline the one helper we used from the (nonexistent) `parser` module
def mention_markdown(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

@Client.on_message(filters.command("power", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group & filters.reply)
@retry()
async def promote_user(client, message):
    chat_id = message.chat.id
    user_id = message.reply_to_message.from_user.id
    command_parts = cmd_text(message).split()
    if len(command_parts) >= 2:
        promotion_type = command_parts[1].lower()
        title= 'admin'
        if len(command_parts) >= 3:
          title = " ".join(command_parts[2:])
        permissions = {}
        if promotion_type == "full":
            permissions = {
                "can_change_info": True,
                "can_invite_users": True,
                "can_pin_messages": True,
                "can_delete_messages": True,
                "can_manage_chat": True,
                "can_manage_video_chats": True,
                "can_restrict_members": True,
                "can_promote_members": True,
            }
        elif promotion_type == "mod":
            permissions = {
                "can_change_info": True,
                "can_invite_users": True,
                "can_pin_messages": True,
                "can_delete_messages": True,
                "can_manage_chat": True,
                "can_manage_video_chats": True,
                "can_restrict_members": True,
                "can_promote_members": False,
            }
        elif promotion_type == "nub":
            permissions = {
                "can_change_info": False,
                "can_invite_users": True,
                "can_pin_messages": False,
                "can_delete_messages": False,
                "can_manage_chat": True,
                "can_manage_video_chats": True,
                "can_restrict_members": False,
                "can_promote_members": False,
            }
        elif promotion_type == "less":
            permissions = {
                "can_change_info": False,
                "can_invite_users": False,
                "can_pin_messages": False,
                "can_delete_messages": False,
                "can_manage_chat": False,
                "can_manage_video_chats": False,
                "can_restrict_members": False,
                "can_promote_members": False,
            }
        else:
            return  # Invalid promotion type
        try:
            await client.promote_chat_member(
                chat_id,
                user_id,privileges=ChatPrivileges(
                **permissions,)
            )
            if promotion_type == "less":
              return await message.edit("User demoted successfully.")
            await message.edit("User promoted successfully.")
            await asyncio.sleep(2)
            await client.set_administrator_title(chat_id, user_id, title)
        except Exception as e:
            await message.edit(f"Failed to promote user: {e}")
    else:
        await message.edit("Invalid command usage. Please provide promotion type and title.")

def get_args(message):
    try:
        message = message.text
    except AttributeError:
        pass
    if not message:
        return False
    message = message.split(maxsplit=1)
    if len(message) <= 1:
        return []
    message = message[1]
    try:
        split = shlex.split(message)
    except ValueError:
        return message
    return list(filter(lambda x: len(x) > 0, split))

@Client.on_message(filters.command("inv", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group & filters.reply)
@retry()
async def inv(client, message):
    sender = client.me.id
    text = cmd_text(message).split(" ", 1)
    if len(text) < 2 or not text[1].strip():
        # text[1] was read unconditionally, so a bare .inv raised IndexError --
        # and @retry() re-ran the handler to raise it again.
        return await message.edit_text(styled_error("Usage: <code>.inv &lt;chat&gt;</code>"))
    Man = await message.edit_text("`Processing . . .`")
    queryy = text[1].strip()
    chat = await client.get_chat(queryy)
    tgchat = message.chat
    await Man.edit_text(f"inviting users from {chat.username}")
    async for member in client.get_chat_members(chat.id):
        user = member.user
        zxb = [
            enums.UserStatus.ONLINE,
            enums.UserStatus.OFFLINE,
            enums.UserStatus.RECENTLY,
        ]
        if user.status in zxb:
            try:
                await client.add_chat_members(tgchat.id, user.id)
                await asyncio.sleep(3)
            except (UserRestricted, PeerFlood) as e:
                # The details were interpolated into a message the default parse
                # mode reads as HTML, so an error mentioning a <tag> arrived with
                # that part deleted. styled_error escapes them.
                await bot.send_message(sender, styled_error("Invite stopped", details=e))
                break
            except Exception as e:
                mg = await bot.send_message(sender, styled_error("Invite failed", details=e))
                await asyncio.sleep(3)
                await mg.delete()

# Helper function to split users into chunks
def user_dist(l, n):
    for i in range(0, len(l), n):
        yield l[i: i + n]

# Invite users to voice chat directly with the command handler
@Client.on_message(filters.command("invite2vc", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def invite_to_voice_chat(client, message):
    chat_id = message.chat.id
    users = []
    await message.edit("Starting to invite users to voice chat...")

    # Resolve the peer for the chat and get the call information
    try:
        input_channel = await client.resolve_peer(chat_id)
        full_channel = await client.invoke(GetFullChannel(channel=input_channel))
        call = full_channel.full_chat.call

        if not call:
            await message.edit("No active group call found.")
            return
    except Exception as e:
        await message.edit(f"Error retrieving group call: {str(e)}")
        return

    # Collect user IDs (non-bot, non-deleted members)
    async for m in client.get_chat_members(chat_id):
        if m.user and not m.user.is_bot and not m.user.is_deleted:
            users.append(m.user.id)  # Add user ID to the list

    # Invite users in chunks
    z = 0
    hmm = list(user_dist(users, 6))
    for p in hmm:
        try:
            await client.invoke(
                InviteToGroupCall(
                    call=call,  # Pass the call object retrieved from messages.ChatFull
                    users = [await client.resolve_peer(user_id) for user_id in p]
                )
            )
            z += 6
        except Exception as e:
            logger.warning(f"Group call invite chunk failed: {e}")

        await asyncio.sleep(10)  # Wait for 10 seconds before inviting the next chunk

    await message.edit(f"Finished inviting users. Total invited: {z}")



@Client.on_message(filters.command("id", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def id_command(client, message):
    lines = [f"<b>• Chat ID:</b> <code>{message.chat.id}</code>"]
    reply = message.reply_to_message
    if reply and reply.from_user:
        lines.append(f"<b>• Replied User ID:</b> <code>{reply.from_user.id}</code>")
    elif message.from_user:
        lines.append(f"<b>• Your User ID:</b> <code>{message.from_user.id}</code>")
    if reply:
        lines.append(f"<b>• Message ID:</b> <code>{reply.id}</code>")
        # media file IDs
        _MEDIA = ("photo", "video", "audio", "voice", "video_note", "animation", "document", "sticker")
        for attr in _MEDIA:
            obj = getattr(reply, attr, None)
            if obj:
                lines.append(f"<b>• File ID ({attr}):</b> <code>{obj.file_id}</code>")
                thumb = getattr(obj, "thumbs", None) or getattr(obj, "thumb", None)
                if thumb:
                    t = thumb[0] if isinstance(thumb, list) else thumb
                    lines.append(f"<b>• Thumb File ID:</b> <code>{t.file_id}</code>")
                break

    result_text = (
        f"<b>🆔 Identifier Details</b>\n\n"
        f"<blockquote>\n" + "\n".join(lines) + "\n</blockquote>"
    )
    await message.edit(result_text, parse_mode=enums.ParseMode.HTML)




@Client.on_message(filters.command("leave", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def leave_command(client, message):
    chat_id = message.chat.id
    await message.edit("👋 Leaving this chat...")
    try:
        await client.leave_chat(chat_id)
    except Exception as e:
        await client.send_message(client.me.id, styled_error(f"Failed to leave `{chat_id}`: {e}"))
