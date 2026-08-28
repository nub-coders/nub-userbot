
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

# users.getUsers takes at most 200 ids per call and kurigram does not split the
# list for you, so an account with a few hundred blocked users made .stats fail
# outright on the RPC.
_GET_USERS_BATCH = 200


async def categorize_blocked_users(client, blocked_user_ids):
    users = []
    bots = []

    for start in range(0, len(blocked_user_ids), _GET_USERS_BATCH):
        batch = blocked_user_ids[start:start + _GET_USERS_BATCH]
        try:
            user_details = await client.get_users(batch)
        except Exception as e:
            # One unresolvable id should not cost the whole count.
            logger.warning(f"stats: could not resolve {len(batch)} blocked users: {e}")
            continue
        for user in user_details:
            if user.is_bot:
                bots.append(user.id)
            else:
                users.append(user.id)

    return users, bots

@Client.on_message(filters.command("stats", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def status(client, message):
    NUB = await message.edit_text("`Collecting stats...`")
    start = datetime.datetime.now()
    u = g = sg = c = b = um = a_chat = up = blocked_bots = blocked_users = approved_users = 0
    progress_msg = ""

    # Fetch approved users from the database
    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
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
import logging
from pyrogram import Client, filters
from pyrogram.raw import functions
from tools import *

# Declared after the last `from tools import *`, which would otherwise rebind
# `logger` to tools' own and file these lines under the wrong name.
logger = logging.getLogger("account")

# A single message caps out at 4096 characters and a busy account can have far
# more sessions than fit; send them in batches rather than failing the command.
_MAX_MESSAGE_CHARS = 3800


def format_timestamp(ts):
    return datetime.datetime.utcfromtimestamp(ts).strftime('%B %d, %Y, %H:%M:%S')

@Client.on_message(filters.command("sessions", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def session_handler(client, message):
    result = await client.invoke(functions.account.GetAuthorizations())

    # Device model, app name and country for every login on the account. All of
    # it is text supplied by whatever client logged in, so it is escaped, and it
    # is not something to print into whichever group the command was typed in --
    # which is what this did. Details go to saved messages.
    blocks = []
    for session in result.authorizations:
        blocks.append(f"""
<blockquote>Device: {html_esc(session.device_model)}</blockquote>
<blockquote>Platform: {html_esc(session.platform)}</blockquote>
<blockquote>App Name: {html_esc(session.app_name)} (Version: {html_esc(session.app_version)})</blockquote>
<blockquote>Country: {html_esc(session.country)}</blockquote>
<blockquote>Current Session: {session.current}</blockquote>
<blockquote>Created On: {format_timestamp(session.date_created)}</blockquote>
<blockquote>Last Active: {format_timestamp(session.date_active)}</blockquote>\n\n""")

    # Group the blocks into messages that fit.
    pages = []
    current = "<b>ACTIVE SESSIONS</b>"
    for block in blocks:
        if len(current) + len(block) > _MAX_MESSAGE_CHARS:
            pages.append(current)
            current = ""
        current += block
    pages.append(current)

    in_own_dm = message.chat.id == client.me.id
    if in_own_dm:
        await message.edit_text(pages[0])
        rest = pages[1:]
    else:
        await message.edit_text(f"🔐 <b>{len(blocks)} active session(s)</b> — details sent to your saved messages.")
        rest = pages
    for page in rest:
        await client.send_message(client.me.id, page)


@Client.on_message(filters.command("bio", prefixes=HARDCODED_PREFIXES) & filters.me)
@retry()
async def set_bio(client, message):
    args = cmd_text(message).split(maxsplit=1)
    if len(args) < 2:
        return await message.edit(styled_error("Usage: `.bio <text>` (max 70 chars)"))
    bio = args[1]
    if len(bio) > 70:
        return await message.edit(styled_error("Bio must be 70 characters or fewer."))
    await client.update_profile(bio=bio)
    await message.edit(styled_success(f"Bio updated to:\n`{bio}`"))


@Client.on_message(filters.command("pfp", prefixes=HARDCODED_PREFIXES) & filters.me & filters.reply)
@retry()
async def set_pfp(client, message):
    reply = message.reply_to_message
    if not (reply.photo or (reply.document and "image" in (reply.document.mime_type or ""))):
        return await message.edit(styled_error("Reply to a photo to set it as your profile picture."))
    await message.edit("`Updating profile photo...`")
    path = await reply.download()
    try:
        await client.set_profile_photo(photo=path)
        await message.edit(styled_success("Profile photo updated."))
    finally:
        if path and os.path.exists(path):
            os.remove(path)
