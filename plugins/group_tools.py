
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

# ponytail: inline the one helper we used from the (nonexistent) `parser` module
def mention_markdown(user_id, name):
    return f"[{name}](tg://user?id={user_id})"

@Client.on_message(filters.command("power", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group & filters.reply)
@retry()
async def promote_user(client, message):
    chat_id = message.chat.id
    user_id = message.reply_to_message.from_user.id
    command_parts = message.text.split()
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
    Man = await message.edit_text("`Processing . . .`")
    text = message.text.split(" ", 1)
    queryy = text[1]
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
            except UserRestricted as e:
              mg = await bot.send_message(sender, f"**ERROR:** `{e}`")
              break
            except PeerFlood as e:
             mg = await bot.send_message(sender, f"**ERROR:** `{e}`")
             break
            except Exception as e:
                mg = await bot.send_message(sender, f"**ERROR:** `{e}`")
                await asyncio.sleep(3)
                await mg.delete()

# Helper function to split users into chunks
def user_list(users, chunk_size):
    for i in range(0, len(users), chunk_size):
        yield users[i:i + chunk_size]

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
            print(f"Error: {str(e)}")

        await asyncio.sleep(10)  # Wait for 10 seconds before inviting the next chunk

    await message.edit(f"Finished inviting users. Total invited: {z}")

def get_text(message) -> [None, str]:
    """Extract Text From Commands"""
    text_to_return = message.text
    if message.text is None:
        return None
    if " " in text_to_return:
        try:
            return message.text.split(None, 1)[1]
        except IndexError:
            return None
    else:
        return None

@Client.on_message(filters.command("admins", prefixes=HARDCODED_PREFIXES) & filters.me & filters.group)
@retry()
async def adminlist(client, message):
    replyid = None
    toolong = False

    if len(message.text.split()) >= 2:
        chat = message.text.split(None, 1)[1]
        grup = await client.get_chat(chat)
    else:
        chat = message.chat.id
        grup = await client.get_chat(chat)

    if message.reply_to_message:
        replyid = message.reply_to_message.id

    creator = []
    admin = []
    badmin = []

    async for a in client.get_chat_members(chat, filter=enums.ChatMembersFilter.ADMINISTRATORS):
        try:
            nama = a.user.first_name + " " + a.user.last_name
        except:
            nama = a.user.first_name

        if nama is None:
            nama = "☠️ Deleted account"

        if a.status == enums.ChatMemberStatus.ADMINISTRATOR:
            if a.user.is_bot:
                badmin.append((a.user, nama))
            else:
                admin.append((a.user, nama))
        elif a.status == enums.ChatMemberStatus.OWNER:
            creator.append((a.user, nama))

    # Sort admin lists by name
    admin.sort(key=lambda x: x[1])
    badmin.sort(key=lambda x: x[1])

    totaladmins = len(creator) + len(admin) + len(badmin)
    teks = f"**Admins in {grup.title}**\n"
    teks += "╒═══「 Creator 」\n"

    # Function to format time difference
    def format_time_difference(last_message_date):
        now = datetime.datetime.utcnow()
        delta = now - last_message_date

        if delta.days > 0:
            return f"{delta.days} days ago"
        elif delta.seconds >= 3600:
            hours = delta.seconds // 3600
            return f"{hours} hours ago"
        elif delta.seconds >= 60:
            minutes = delta.seconds // 60
            return f"{minutes} minutes ago"
        else:
            return "Just now"

    # Helper function to add user info
    async def add_user_info(user_list):
        nonlocal teks, toolong
        for x in user_list:
            if x[1] != "☠️ Deleted account":
                async for messages in client.search_messages(chat, from_user=x[0].id, limit=1):
                    last_message_time = datetime.datetime.utcfromtimestamp(messages.date.timestamp())
                    last_message_str = format_time_difference(last_message_time)

                    teks += f"│ • {mention_markdown(x[0].id, x[1])} : {last_message_str}\n"
                    break
            if len(teks) >= 4096:
                await message.reply(teks, reply_to_message_id=replyid)
                teks = ""
                toolong = True
            else:
                teks += f"\n"
        teks += f"</blockquote>"

    # Add creator, human admin, and bot admin info
    await add_user_info(creator)
    teks += f"<blockquote>╞══「 {len(admin)} Human Administrator 」\n"
    await add_user_info(admin)
    teks += f"\n\n<blockquote>╞══「 {len(badmin)} Bot Administrator 」\n"
    await add_user_info(badmin)

    teks += f"\n\n<blockquote>╘══「 Total {totaladmins} Admins 」</blockquote>"

    if toolong:
        await message.reply(message.chat.id, teks, reply_to_message_id=replyid)
    else:
        await message.edit(teks)
