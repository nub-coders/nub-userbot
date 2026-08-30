import datetime
import os
import base64
import magic
import logging
from pyrogram import Client, filters, enums
from pyrogram.types import Message
from config import *
from tools import *

logger = logging.getLogger("antyspam")

# Initialize magic for file type detection
mime = magic.Magic(mime=True)

# Support filter
is_support = filters.create(lambda _, __, message: message.chat.is_support)


def _is_spam_control_enabled(user_data: dict) -> bool:
    val = user_data.get("Spam_control", True)
    if isinstance(val, str):
        return val.lower() not in ("false", "0", "off", "disable", "disabled")
    return bool(val)


# Custom filter for spam control
def crcustom_filter():
    def filte_func(_, client, message):
        user_data = cached_get_user_data(client.me.id)
        if not _is_spam_control_enabled(user_data):
            return False
        white_listed = user_data.get("white_listed", [])
        if not message.from_user:
            return False
        sender_id = message.from_user.id
        if sender_id in white_listed:
            return False
        return True
    return filters.create(filte_func)


async def _extract_target_user(client, message):
    """Extract (user_id, display_name) from reply, command argument, or current PM chat."""
    if message.reply_to_message and message.reply_to_message.from_user:
        u = message.reply_to_message.from_user
        name = html_esc(f"{u.first_name} {u.last_name or ''}".strip())
        return u.id, name

    args = cmd_text(message).split(maxsplit=1)
    if len(args) >= 2:
        target_str = args[1].strip()
        try:
            u = await client.get_users(int(target_str) if target_str.isdigit() or (target_str.startswith("-") and target_str[1:].isdigit()) else target_str)
            name = html_esc(f"{u.first_name} {u.last_name or ''}".strip())
            return u.id, name
        except Exception:
            if target_str.isdigit():
                return int(target_str), target_str
            raise

    if message.chat.type == enums.ChatType.PRIVATE:
        name = html_esc(message.chat.first_name or str(message.chat.id))
        return message.chat.id, name

    return None, None


@Client.on_message(filters.private & ~filters.me & ~filters.bot & crcustom_filter())
@retry()
async def handle_user(client, message):
    if getattr(message, 'service', None):
        return

    logger.debug("Handling user...")
    sender_id = message.from_user.id

    # Check if the user is an admin
    if os.path.exists(admin_file):
        try:
            with open(admin_file, "r") as file:
                admin_ids = [int(line.strip()) for line in file.readlines() if line.strip().isdigit()]
                if sender_id in admin_ids:
                    return
        except Exception as e:
            logger.warning(f"Error reading admin_file: {e}")

    if message.chat.id == 777000 or sender_id == 777000:
        return

    logger.debug(f"Sender ID: {sender_id}")

    # Check if user is whitelisted or spam control is disabled
    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    if not _is_spam_control_enabled(user_data):
        logger.debug("Spam control is off, returning.")
        return

    white_listed = user_data.get('white_listed', [])
    if sender_id in white_listed:
        logger.debug("User is whitelisted. Skipping...")
        return

    # Update user count in user_sessions
    user_sessions.update_one(
        {"user_id": client.me.id},
        {
            "$inc": {f"users.{sender_id}": 1},
        },
        upsert=True
    )
    invalidate_session_cache(client.me.id)
    logger.debug("User count updated.")

    # Check if user should receive welcome or be blocked/deleted
    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    users = user_data.get('users', {})
    user_count = users.get(str(sender_id), 0)
    session_name = f'user_{client.me.id}'
    user_dir = session_name
    os.makedirs(user_dir, exist_ok=True)

    full_name = html_esc(f"{message.from_user.first_name} {message.from_user.last_name or ''}".strip())

    delete_count = user_data.get('delete_count', 0)
    block_count = user_data.get('block_count', 0)

    if user_count == 1:
        logo = gvarstatus(client.me.id, "ALIVE_LOGO") or (await client.download_media(client.me.photo.big_file_id, f"{user_dir}/{'logo.mp4' if getattr(client.me.photo, 'has_animation', False) else 'logo.jpg'}") if client.me.photo else "userbot.jpg")
        alive_logo = logo
        if isinstance(logo, bytes):
            alive_logo = f"{user_dir}/logo.jpg"
            with open(alive_logo, "wb") as fimage:
                fimage.write(base64.b64decode(logo))
            if 'video' in mime.from_file(alive_logo):
                alive_logo = rename_file(alive_logo, f"{user_dir}/logo.mp4")

        greet_message = gvarstatus(client.me.id, "WELCOME") or f"""<blockquote>{bold_cool(f"👋 Warm greetings, {{full_name}}! Welcome to my private message.")}</blockquote>

<blockquote>{bold_cool("Thank you for connecting with me. I am delighted to assist you. Kindly share the purpose of your message, and I will respond promptly. Your comfort is my priority.")}</blockquote>

<blockquote>{bold_cool("Please avoid excessive messaging, as it may lead to being blocked. Enjoy your time here!")}</blockquote>"""

        caption = await format_welcome_message(
            client, greet_message, message.chat.id, message.from_user.first_name, full_name=full_name
        )
        send = client.send_video if (alive_logo and str(alive_logo).endswith(".mp4")) else client.send_photo
        await send(
            message.chat.id,
            alive_logo or "userbot.jpg",
            caption=caption
        )

    elif block_count > 0 and user_count >= block_count:
        if user_count == block_count:
            warning_message = bold_cool('Auto-block mode activated.\n\nYour message was flagged as potentially unwanted. Further messages from you will result in your account being blocked.')
            await client.send_message(message.chat.id, warning_message)
        else:
            logger.debug("Blocking user...")
            await client.block_user(sender_id)
    elif delete_count > 0 and user_count >= delete_count:
        if user_count == delete_count:
            warning_message = bold_cool('Auto-delete mode activated.\n\nYour message was flagged as potentially irrelevant. All subsequent messages from you will be automatically deleted.')
            await client.send_message(message.chat.id, warning_message)
        else:
            logger.debug("Deleting message...")
            await message.delete()


@Client.on_message(filters.command(["antispam", "pmpermit", "pmguard"], prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def toggle_antispam(client, message):
    args = cmd_text(message).split()[1:] if len(cmd_text(message).split()) > 1 else []
    user_id = client.me.id
    user_data = user_sessions.find_one({"user_id": user_id}) or {}
    current = _is_spam_control_enabled(user_data)

    if not args:
        new_state = not current
    elif args[0].lower() in ("on", "enable", "true", "yes", "1"):
        new_state = True
    elif args[0].lower() in ("off", "disable", "false", "no", "0"):
        new_state = False
    elif args[0].lower() == "status":
        state_str = "Enabled 🟢" if current else "Disabled 🔴"
        return await edit_or_reply(message, f"<b>PM Anti-Spam / Permit:</b> <code>{state_str}</code>")
    else:
        return await edit_or_reply(message, styled_error("Usage: `[prefix]antispam [on|off|status]`"))

    user_sessions.update_one({"user_id": user_id}, {"$set": {"Spam_control": new_state}}, upsert=True)
    invalidate_session_cache(user_id)
    state_str = "Enabled 🟢" if new_state else "Disabled 🔴"
    await edit_or_reply(message, styled_success(f"PM Anti-Spam / Permit is now <b>{state_str}</b>."))


@Client.on_message(filters.command("approve", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def approve_user(client, message):
    logger.debug("Approving user...")
    try:
        target_id, target_name = await _extract_target_user(client, message)
    except Exception as e:
        return await edit_or_reply(message, styled_error("Failed to find user", details=str(e)))

    if not target_id:
        return await edit_or_reply(message, styled_error("Reply to a user, provide user ID/username, or use in a private chat."))

    try:
        await client.unblock_user(target_id)
        logger.debug(f"User {target_id} unblocked.")
    except Exception as e:
        logger.warning(f"Error unblocking user {target_id}: {e}")

    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    white_listed = user_data.get('white_listed', [])
    if target_id not in white_listed:
        user_sessions.update_one(
            {"user_id": client.me.id},
            {
                "$push": {"white_listed": target_id},
                "$set": {f"users.{target_id}": 0}
            },
            upsert=True
        )
        invalidate_session_cache(client.me.id)
        logger.debug(f"User {target_id} added to whitelist.")
    else:
        user_sessions.update_one(
            {"user_id": client.me.id},
            {"$set": {f"users.{target_id}": 0}},
            upsert=True
        )
        invalidate_session_cache(client.me.id)

    if message.chat.type == enums.ChatType.PRIVATE and message.chat.id == target_id and len(cmd_text(message).split()) == 1 and not message.reply_to_message:
        await edit_or_reply(message, "You have been approved and added to the whitelist.")
    else:
        label = target_name or f"<code>{target_id}</code>"
        await edit_or_reply(message, styled_success(f"User {label} approved and added to whitelist."))


@Client.on_message(filters.command("disapprove", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def disapprove_user(client, message):
    try:
        target_id, target_name = await _extract_target_user(client, message)
    except Exception as e:
        return await edit_or_reply(message, styled_error("Failed to find user", details=str(e)))

    if not target_id:
        return await edit_or_reply(message, styled_error("Reply to a user, provide user ID/username, or use in a private chat."))

    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    white_listed = user_data.get('white_listed', [])
    if target_id in white_listed:
        user_sessions.update_one(
            {"user_id": client.me.id},
            {
                "$pull": {"white_listed": target_id},
                "$set": {f"users.{target_id}": 0}
            }
        )
        invalidate_session_cache(client.me.id)
        logger.debug(f"User {target_id} removed from whitelist and user count reset.")
        if message.chat.type == enums.ChatType.PRIVATE and message.chat.id == target_id and len(cmd_text(message).split()) == 1 and not message.reply_to_message:
            await edit_or_reply(message, "You have been removed from the whitelist and your message count has been reset.")
        else:
            label = target_name or f"<code>{target_id}</code>"
            await edit_or_reply(message, styled_success(f"User {label} removed from whitelist."))
    else:
        label = target_name or f"<code>{target_id}</code>"
        await edit_or_reply(message, styled_error(f"User {label} is not in the whitelist."))


@Client.on_message(filters.command("rmall", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def remove_all_whitelisted_users(client, message):
    logger.debug("Removing all whitelisted users...")

    result = user_sessions.update_one(
        {"user_id": client.me.id},
        {"$set": {"white_listed": []}}
    )
    invalidate_session_cache(client.me.id)

    if result.modified_count > 0:
        logger.debug("All whitelisted users removed.")
        await edit_or_reply(message, styled_success("All whitelisted users have been removed."))
    else:
        logger.debug("No whitelisted users to remove.")
        await edit_or_reply(message, styled_error("There were no whitelisted users to remove."))


@Client.on_message(filters.command("rstall", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def reset_all_users_count(client, message):
    logger.debug("Resetting all users' counts to 0...")

    user_data = user_sessions.find_one({"user_id": client.me.id})
    if user_data:
        users = user_data.get('users', {})
        for user_id in users.keys():
            if user_id != "total_user_count":  # Ensure we don't reset the total_user_count field
                user_sessions.update_one(
                    {"user_id": client.me.id},
                    {"$set": {f"users.{user_id}": 0}}
                )
        invalidate_session_cache(client.me.id)
        logger.debug("All users' counts have been reset to 0.")
        await edit_or_reply(message, styled_success("All users' message counts have been reset to 0."))
    else:
        await edit_or_reply(message, styled_error("No data found for the bot user."))


@Client.on_message(filters.command("rst", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def reset_user_count(client, message):
    try:
        target_id, target_name = await _extract_target_user(client, message)
    except Exception as e:
        return await edit_or_reply(message, styled_error("User not found.", details=str(e)))

    if not target_id:
        return await edit_or_reply(message, styled_error("Reply to a user, provide a user ID/username, or run in a private chat."))

    chat_id = str(target_id)
    user_data = user_sessions.find_one({"user_id": client.me.id}) or {}
    users = user_data.get('users', {})
    if chat_id in users:
        user_sessions.update_one(
            {"user_id": client.me.id},
            {"$set": {f"users.{chat_id}": 0}}
        )
        invalidate_session_cache(client.me.id)
        logger.debug(f"User count for {chat_id} has been reset to 0.")
        await edit_or_reply(message, styled_success(f"Message count for `{chat_id}` has been reset to 0."))
    else:
        await edit_or_reply(message, styled_error(f"No message count found for `{chat_id}`."))


@Client.on_message(filters.command("addbl", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def add_to_blacklist(client, message):
    chat_id = message.chat.id
    chat = message.chat
    user_data = user_sessions.find_one({"user_id": client.me.id})

    if user_data:
        blocked_list = user_data.get('blocked_list', [])
        chat_label = html_esc(chat.title or chat.first_name)
        if chat_id in blocked_list:
            await edit_or_reply(message, f"{chat_label} is already in the blacklist.")
            return

        user_sessions.update_one(
            {"user_id": client.me.id},
            {"$push": {"blocked_list": chat_id}}
        )
        invalidate_session_cache(client.me.id)
        await edit_or_reply(message, styled_success(f"{chat_label} added to blacklist."))

    else:
        user_sessions.insert_one({
            "user_id": client.me.id,
            "blocked_list": [chat_id]
        })
        invalidate_session_cache(client.me.id)
        await edit_or_reply(message, styled_success(f"{html_esc(chat.title or chat.first_name)} added to blacklist (new entry)."))


@Client.on_message(filters.command("rmbl", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def remove_from_blacklist(client, message: Message):
    user_id = client.me.id
    user_data = user_sessions.find_one({"user_id": user_id}) or {}

    blocked_list = user_data.get("blocked_list", [])

    if len(message.command) > 1:  # Chat ID provided as argument
        target_chat_id_str = message.command[1]
        try:
            target_chat_id = int(target_chat_id_str)
        except ValueError:
            await edit_or_reply(message, styled_error("Invalid chat ID. Please provide a valid integer."))
            return
        try:
            target_chat = await client.get_chat(target_chat_id)
            chat_title_or_name = target_chat.title or target_chat.first_name
        except Exception:
            chat_title_or_name = None

        if target_chat_id in blocked_list:
            user_sessions.update_one({"user_id": user_id}, {"$pull": {"blocked_list": target_chat_id}})
            invalidate_session_cache(user_id)
            await edit_or_reply(message, styled_success(f"{chat_title_or_name or target_chat_id} removed from blacklist."))
        else:
            await edit_or_reply(message, styled_error(f"{target_chat_id} not found in blacklist."))

    else:  # Remove current chat from blacklist
        chat_id = message.chat.id
        try:
            chat = await client.get_chat(chat_id)
            chat_title_or_name = chat.title or chat.first_name
        except Exception as e:
            await edit_or_reply(message, styled_error(f"Error fetching chat information: {e}"))
            return

        if chat_id in blocked_list:
            user_sessions.update_one({"user_id": user_id}, {"$pull": {"blocked_list": chat_id}})
            invalidate_session_cache(user_id)
            await edit_or_reply(message, styled_success(f"{chat_title_or_name} removed from blacklist."))
        else:
            await edit_or_reply(message, styled_error(f"{chat_title_or_name} not found in blacklist."))


@Client.on_message(filters.command("block", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def block_user(client, message):
    try:
        user_id, target_name = await _extract_target_user(client, message)
    except Exception as e:
        return await edit_or_reply(message, styled_error("User not found.", details=str(e)))

    if not user_id:
        return await edit_or_reply(message, styled_error("Reply to a user, provide a user ID/username, or run in a private chat."))

    await client.block_user(user_id)
    await edit_or_reply(message, styled_success(f"Blocked `{user_id}`."))


@Client.on_message(filters.command("unblock", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def unblock_user(client, message):
    try:
        user_id, target_name = await _extract_target_user(client, message)
    except Exception as e:
        return await edit_or_reply(message, styled_error("User not found.", details=str(e)))

    if not user_id:
        return await edit_or_reply(message, styled_error("Reply to a user, provide a user ID/username, or run in a private chat."))

    await client.unblock_user(user_id)
    await edit_or_reply(message, styled_success(f"Unblocked `{user_id}`."))


@Client.on_message(filters.command("blist", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
@retry()
async def show_blacklist(client, message):
    user_data = user_sessions.find_one({"user_id": client.me.id})
    if user_data:
        blocked_list = user_data.get("blocked_list", [])
        if blocked_list:
            lines = []
            for idx, cid in enumerate(blocked_list, 1):
                lines.append(f"<b>{idx}.</b> <code>{cid}</code> (Blacklisted 🚫)")
            result_html = (
                f"<b>🚫 Blacklisted Chats ({len(blocked_list)})</b>\n\n"
                f"<blockquote>\n" + "\n".join(lines) + f"\n</blockquote>\n\n"
                f"💡 <i>Use <code>.rmbl &lt;chat_id&gt;</code> to remove a chat from this list.</i>"
            )
            await edit_or_reply(message, result_html, parse_mode=enums.ParseMode.HTML)
        else:
            await edit_or_reply(message, "<b>🚫 Blacklist Empty</b>\n\n<blockquote>No chats or users are currently blacklisted.</blockquote>", parse_mode=enums.ParseMode.HTML)
    else:
        await edit_or_reply(message, "No blacklist found for this bot.")
