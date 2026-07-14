
from pyrogram.raw.functions.contacts import GetBlocked
from config import *
from tools import *

# NOTE: approve/disapprove/addbl/rmbl/blist/rmall/rstall/rst live in antyspam.py.
# They previously existed here too as byte-identical duplicates on the same
# userbot client (dead double-registration) and were removed. This file keeps
# only the commands unique to it: `stats` and `sessions`.

async def get_all_blocked_users(client):
    blocked_users = []
    offset = 0
    limit = 100  # Adjust as needed

    while True:
        blocked = await client.invoke(
            GetBlocked(
                offset=offset,
                limit=limit
            )
        )
        blocked_users.extend(blocked.blocked)
        offset += len(blocked.blocked)

        if len(blocked.blocked) < limit:  # Break if we've fetched all blocked users
            break

    return [user.peer_id.user_id for user in blocked_users if user.peer_id]  # Extract user IDs

async def categorize_blocked_users(client, blocked_user_ids):
    users = []
    bots = []

    if blocked_user_ids:
        # Fetch all user details using get_users
        user_details = await client.get_users(blocked_user_ids)
        for user in user_details:
            if user.is_bot:
                bots.append(user.id)
            else:
                users.append(user.id)

    return users, bots

@Client.on_message(filters.command("stats") & filters.me)
@retry()
async def status(client, message):
    NUB = await message.edit_text("`Collecting stats...`")
    start = datetime.datetime.now()
    u = g = sg = c = b = um = a_chat = up = blocked_bots = blocked_users = approved_users = 0
    progress_msg = ""

    # Fetch approved users from the database
    user_data = user_sessions.find_one({"user_id": client.me.id})
    approved_users_list = user_data.get('white_listed', [])

    # Get all blocked users using the Raw API
    blocked_user_ids = await get_all_blocked_users(client)
    blocked_users_list, blocked_bots_list = await categorize_blocked_users(client, blocked_user_ids)

    async for dialog in client.get_dialogs():
        um += dialog.unread_mentions_count
        up += dialog.unread_messages_count

        if dialog.chat.type == enums.ChatType.PRIVATE:
            u += 1
        elif dialog.chat.type == enums.ChatType.BOT:
            b += 1
            # Check if the bot is blocked
            if dialog.chat.id in blocked_bots_list:
                blocked_bots += 1
        elif dialog.chat.type == enums.ChatType.GROUP:
            g += 1
        elif dialog.chat.type == enums.ChatType.SUPERGROUP:
            sg += 1
            user_s = await dialog.chat.get_member(int(client.me.id))
            if user_s.status in (
                enums.ChatMemberStatus.OWNER,
                enums.ChatMemberStatus.ADMINISTRATOR,
            ):
                a_chat += 1
        elif dialog.chat.type == enums.ChatType.CHANNEL:
            c += 1

        # Count blocked users from the blocklist
        if dialog.chat.id in blocked_users_list:
            blocked_users += 1

        # Count approved users from the database
        if dialog.chat.id in approved_users_list:
            approved_users += 1

        # Update progress message dynamically
        progress_msg = (
            f"<b>`Collecting stats...`\n"
            f"<b>`Private Messages: {u}`\n"
            f"<b>`Groups: {g}`\n"
            f"<b>`Super Groups: {sg}`\n"
            f"<b>`Channels: {c}`\n"
            f"<b>`Admin in: {a_chat} Chats`\n"
            f"<b>`Bots: {b}`\n"
            f"<b>`Blocked Bots: {len(blocked_bots_list)}`\n"
            f"<b>`Blocked Users: {len(blocked_users_list)}`\n"
            f"<b>`Approved Users: {approved_users}`\n"
            f"<b>`Unread Messages: {up}`\n"
            f"<b>`Unread Mentions: {um}`"
        )
        if random.choices([True, False], weights=[1, 10])[0]:
            await NUB.edit_text(progress_msg)

    end = datetime.datetime.now()
    ms = (end - start).seconds

    # Final message with stats
    await NUB.edit_text(
        f"""<b>`Your Stats Obtained in {ms} seconds`
<blockquote><b>`Private Messages = {u}`
<b>`Groups = {g}`
<b>`Super Groups = {sg}`<b>
<b>`Channels = {c}`<b>
<b>`Admin in Chats = {a_chat}`<b>
`<b>Bots</b> = {b}`<b>
`<b>Blocked Bots</b> = {len(blocked_bots_list)}`<b>
`<b>Blocked Users</b> = {len(blocked_users_list)}`
`<b>Approved Users</b> = {approved_users}`
`<b>Unread messages</b> {up}`
`<b>Unread mentions</b> {um}`</blockquote>"""
    )


import datetime
from pyrogram import Client, filters
from pyrogram.raw import functions
from tools import *

def format_timestamp(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%B %d, %Y, %H:%M:%S')

@Client.on_message(filters.command("sessions") & filters.me)
@retry()
async def session_handler(client, message):
    result = await client.invoke(functions.account.GetAuthorizations())
    
    session_info = "**ACTIVE SESSIONS**"
    
    # Iterate through each session and build the session info string
    for session in result.authorizations:
        session_info += (f"""
<blockquote>Device: {session.device_model}</blockquote>
<blockquote>Platform: {session.platform}</blockquote>
<blockquote>App Name: {session.app_name} (Version: {session.app_version}</blockquote>
<blockquote>Country: {session.country}</blockquote>
<blockquote>Current Session: {session.current}</blockquote>
<blockquote>Created On: {format_timestamp(session.date_created)}</blockquote>
<blockquote>Last Active: {format_timestamp(session.date_active)}</blockquote>\n\n""")
    
    # Edit the message with the session details
    await message.edit_text(session_info)
