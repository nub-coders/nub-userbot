"""
Bot-side command handlers (the `app` client, not the userbot).

The bot client only powers the inline/control surface: a /start intro, the
/commands browser, a /settings toggle panel, /status, /ping and the inline
`banall` confirmation flow. It is loaded only when a BOT_TOKEN is configured
(see main.py), so every handler here assumes the bot is optional.

Adapted from the multi-tenant deployer for this self-hosted single-session
build: the deployer's premium/points/referral/payment/login/deployment
handlers have no backing store here and are intentionally dropped.
"""
import os
import sys
import time
import asyncio
import datetime
import logging

import psutil
from pyrogram import Client, filters
from pyrogram.types import (
    Message,
    CallbackQuery,
    InlineQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQueryResultArticle,
    InputTextMessageContent,
)
from pyrogram.enums import ParseMode, ChatMemberStatus, ButtonStyle

from config import *
from tools import *
from utils.message import Msg, plain_text

logger = logging.getLogger("userbot")


brief_explanation = f"""╭━━━ {Msg.EMOJI_ROCKET} <b>NUB USERBOT</b> ━━━╮
┃ Ultimate Telegram Automation
╰━━━━━━━━━━━━━━━━━━━━━━━━━╯

{Msg.EMOJI_DRAGON} <b>Features</b>

{Msg.EMOJI_MUSIC} <b>Voice Chat Player</b>
    {Msg.EMOJI_SPARK} Stream YouTube audio/video in calls
    {Msg.EMOJI_LOADING} Queue, skip, pause &amp; resume

{Msg.EMOJI_NOTE} <b>Self-Destruct Saver</b>
    {Msg.EMOJI_LOCK} Save disappearing photos &amp; videos
    {Msg.EMOJI_SUCCESS} Works automatically in private chats

{Msg.EMOJI_SHIELD} <b>Private Chat Access</b>
    {Msg.EMOJI_LINK} Download from private channels/groups
    {Msg.EMOJI_SUCCESS} No admin permissions needed

{Msg.EMOJI_DOWNLOAD} <b>Download Manager</b>
    {Msg.EMOJI_LINK} Telegram links &amp; HTTP/HTTPS URLs
    {Msg.EMOJI_STAR} Progress tracking &amp; auto-upload

{Msg.EMOJI_GEAR} <b>Automation Tools</b>
    {Msg.EMOJI_PUZZLE} AI chat, spam protection, sudo users
    {Msg.EMOJI_FIRE} Custom prefixes &amp; auto-reactions

────────────────────

{Msg.EMOJI_STAR} <b>Getting Started</b>
{Msg.EMOJI_PUZZLE} /commands — explore all features
{Msg.EMOJI_GEAR} /settings — customize your bot
{Msg.EMOJI_PIN} /status — check your userbot status

────────────────────
{Msg.EMOJI_STAR} Community: @{GROUP}
{Msg.EMOJI_ROCKET} Updates: @{CHANNEL}"""


def build_settings_ui(user_data: dict):
    """Build the settings message text and keyboard from user_data.

    Returns (text, InlineKeyboardMarkup). Mirrors the toggle keys read by the
    userbot plugins: Spam_control, game, raiding, music, react_control, and the
    delete_count/block_count welcome-mode counters."""
    spam_control  = user_data.get('Spam_control', True)
    game_control  = user_data.get('game', False)
    raid_control  = user_data.get('raiding', False)
    music_control = user_data.get('music', False)
    react_control = user_data.get('react_control', False)
    delete_count  = user_data.get('delete_count', 0)
    block_count   = user_data.get('block_count', 0)
    react_emojis  = ['👍', '♥️', '🔥', '🎉']

    ON, OFF = '✅', '❌'

    # --- message ---
    text = f"{Msg.EMOJI_GEAR} <b>Userbot Settings</b> {Msg.EMOJI_GEAR}\n\n"
    text += f"<blockquote>{Msg.EMOJI_WAVE} Welcome new users in DMs: {ON if spam_control else OFF}</blockquote>\n"
    if spam_control and delete_count > 0:
        text += f"<blockquote>{Msg.EMOJI_NOTE} Auto-delete after: {delete_count} msgs</blockquote>\n"
    if spam_control and block_count > 0:
        text += f"<blockquote>{Msg.EMOJI_SHIELD} Auto-block after: {block_count} msgs</blockquote>\n"
    text += f"<blockquote>{Msg.EMOJI_PUZZLE} Word chain game autoplay: {ON if game_control else OFF}</blockquote>\n"
    text += f"<blockquote>{Msg.EMOJI_SPARK} Replyraid plugin: {ON if raid_control else OFF}</blockquote>\n"
    text += f"<blockquote>{Msg.EMOJI_MUSIC} Music plugin: {ON if music_control else OFF}</blockquote>\n"
    text += f"<blockquote>{Msg.EMOJI_THUMBS_UP} Auto react: {ON if react_control else OFF}</blockquote>\n"
    if react_control:
        text += f"<blockquote>🎯 Reaction: {react_emojis[react_control - 1]}</blockquote>\n"

    # --- keyboard ---
    welcome_mode = [
        InlineKeyboardButton(
            f"Auto-delete {'['+str(delete_count)+']' if delete_count else OFF}",
            callback_data="toggle_delete_count",
            style=ButtonStyle.DANGER if delete_count else ButtonStyle.DEFAULT
        ),
        InlineKeyboardButton(
            f"Auto-block {'['+str(block_count)+']' if block_count else OFF}",
            callback_data="toggle_block_count",
            style=ButtonStyle.DANGER if block_count else ButtonStyle.DEFAULT
        ),
    ]
    react_mode = [
        InlineKeyboardButton(
            f"[{emoji}]" if react_control == i else emoji,
            callback_data=f"toggle_react_{i}",
            style=ButtonStyle.PRIMARY if react_control == i else ButtonStyle.DEFAULT
        )
        for i, emoji in enumerate(react_emojis, 1)
    ]
    buttons = [
        [
            InlineKeyboardButton(f"Game {ON if game_control else OFF}",      callback_data="toggle_game",         style=ButtonStyle.SUCCESS if game_control  else ButtonStyle.DANGER),
            InlineKeyboardButton(f"Replyraid {ON if raid_control else OFF}", callback_data="toggle_raiding",      style=ButtonStyle.SUCCESS if raid_control  else ButtonStyle.DANGER),
            InlineKeyboardButton(f"Music {ON if music_control else OFF}",    callback_data="toggle_music",        style=ButtonStyle.SUCCESS if music_control else ButtonStyle.DANGER),
        ],
        [InlineKeyboardButton(f"Welcome {'⬇️' if spam_control else OFF}", callback_data="toggle_Spam_control", style=ButtonStyle.SUCCESS if spam_control else ButtonStyle.DANGER)],
        *([welcome_mode] if spam_control else []),
        [InlineKeyboardButton(f"Auto react {'⬇️' if react_control else OFF}", callback_data="toggle_react_control", style=ButtonStyle.SUCCESS if react_control else ButtonStyle.DANGER)],
        *([react_mode] if react_control else []),
        [InlineKeyboardButton("✅ Done", callback_data="save_settings", style=ButtonStyle.SUCCESS)],
    ]
    return text, InlineKeyboardMarkup(buttons)


def _commands_keyboard():
    """Build the category-picker keyboard used by /commands and the Back button."""
    keyboard_rows, row = [], []
    for category in categories.keys():
        row.append(InlineKeyboardButton(str(category), callback_data=f'category_{category}', style=ButtonStyle.PRIMARY))
        if len(row) == 3:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)
    return InlineKeyboardMarkup(keyboard_rows)


# ─────────────────────────── /start ────────────────────────────────────────
@Client.on_message(filters.command("start") & filters.private)
async def start_handler(client, message: Message):
    try:
        await client.send_photo(
            chat_id=message.chat.id,
            photo="userbot.jpg",
            caption=brief_explanation,
            parse_mode=ParseMode.HTML,
            reply_to_message_id=message.id,
        )
    except Exception as e:
        logger.error(f"[BOT] Error sending start photo: {e}")
        await message.reply(brief_explanation, parse_mode=ParseMode.HTML)


# ─────────────────────────── /ping ─────────────────────────────────────────
@Client.on_message(filters.command("ping") & filters.private)
async def ping_command(client, message: Message):
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()
    xx = await message.reply("**Pinging...**")
    end = datetime.datetime.now()
    delta_ping = round((end - start).microseconds / 1000, 3)

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process()
    _ping = (
        f"╭━━━ {Msg.EMOJI_PONG} <b>PONG</b> ━━━╮\n"
        f"┃\n"
        f"┃ {Msg.EMOJI_ROCKET} Ping: {str(delta_ping).replace('.', ',')} ms\n"
        f"┃ {Msg.EMOJI_LOADING} Uptime: {uptime}\n"
        f"┃\n"
        f"┃ {Msg.EMOJI_FOLDER} Server Stats\n"
        f"┃ ▸ CPU: {cpu}%\n"
        f"┃ ▸ RAM: {mem}%\n"
        f"┃ ▸ Disk: {disk}%\n"
        f"┃ ▸ Memory: {round(process.memory_info()[0] / 1024 ** 2)} MB\n"
        f"╰━━━━━━━━━━━━━━━━━━╯"
    )
    await xx.edit(_ping, parse_mode=ParseMode.HTML)


# ─────────────────────────── /commands ─────────────────────────────────────
@Client.on_message(filters.command("commands") & filters.private)
async def commands_handler(client, message: Message):
    await message.reply(
        f"{Msg.EMOJI_PIN} <b>Please choose a category to see its commands:</b>",
        reply_markup=_commands_keyboard(),
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r'^category_'))
async def category_handler(client, callback_query: CallbackQuery):
    # Join back since category names may contain '_'
    category = '_'.join(callback_query.data.split('_')[1:])

    category_commands = categories.get(category, [])
    if category_commands:
        category_description = "\n\n".join(
            f"<b>{cmd}</b> - {commands.get(cmd, 'Description not available')}"
            for cmd in category_commands
        )
    else:
        category_description = "<i>No commands in this category yet.</i>"

    prefix_list = ", ".join(f"<code>{p}</code>" for p in HARDCODED_PREFIXES)
    prefix_info = f"\n\n<b>Available Prefixes:</b> {prefix_list}"

    text = f"{Msg.EMOJI_ROCKET} <b>{category} COMMANDS:</b>\n\n{category_description}{prefix_info}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back", callback_data='back', style=ButtonStyle.PRIMARY)]
    ])
    await callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r'^back$'))
async def back_handler(client, callback_query: CallbackQuery):
    await callback_query.edit_message_text(
        f"{Msg.EMOJI_PIN} <b>Please choose a category to see its commands:</b>",
        reply_markup=_commands_keyboard(),
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────── /settings ─────────────────────────────────────
@Client.on_message(filters.command("settings") & filters.private)
async def settings_handler(client, message: Message):
    sender_id = message.from_user.id
    user_data = user_sessions.find_one({"user_id": sender_id}) or {"user_id": sender_id}
    text, markup = build_settings_ui(user_data)
    await message.reply(text, reply_markup=markup, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^toggle_"))
async def toggle_setting(client, callback_query: CallbackQuery):
    sender_id = callback_query.from_user.id
    user_data = user_sessions.find_one({"user_id": sender_id}) or {"user_id": sender_id}

    setting = callback_query.data.split("_", 1)[1]
    allowed_counts = [0, 3, 5, 10]

    if setting in ('delete_count', 'block_count'):
        v = user_data.get(setting, 0) + 1
        while v not in allowed_counts:
            v += 1
            if v > 10:
                v = 0
        new_value = v
    elif setting == 'react_control':
        new_value = False if user_data.get('react_control') else 3
    elif setting.startswith('react_'):
        new_value = int(setting.split('_')[1])
        setting = 'react_control'
    else:
        new_value = not user_data.get(setting, False)

    user_sessions.update_one({"user_id": sender_id}, {"$set": {setting: new_value}}, upsert=True)

    if setting == 'game':
        games[sender_id] = new_value

    user_data = user_sessions.find_one({"user_id": sender_id}) or {"user_id": sender_id}
    text, markup = build_settings_ui(user_data)
    await callback_query.edit_message_text(text, reply_markup=markup, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^save_settings$"))
async def save_settings(client, callback_query: CallbackQuery):
    await callback_query.edit_message_text(
        f"{Msg.EMOJI_SUCCESS} <b>Settings Saved</b>\n\n"
        f"┃ Your preferences have been applied.",
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────── /status ───────────────────────────────────────
@Client.on_message(filters.command("status") & filters.private)
async def status_handler(client, message: Message):
    command_args = message.text.split()
    if message.reply_to_message and message.reply_to_message.from_user:
        user_id = message.reply_to_message.from_user.id
    elif len(command_args) > 1:
        arg = command_args[1]
        if arg.isdigit():
            user_id = int(arg)
        else:
            try:
                user_id = (await client.get_users(arg)).id
            except Exception:
                return await message.reply("Cannot find user with the provided username.")
    else:
        user_id = message.from_user.id

    try:
        tg_user = await client.get_users(user_id)
        user_name = f"{tg_user.first_name or ''} {tg_user.last_name or ''}".strip() or "Unknown"
        username_str = f"@{tg_user.username}" if tg_user.username else "None"
    except Exception:
        user_name, username_str = "Unknown", "None"

    userbot_status = "Connected 🟢" if clients.get(user_id) is not None else "Disconnected 🔴"
    uptime = await get_readable_time((time.time() - StartTime))

    app_data = user_sessions.find_one({"user_id": user_id}) or {}
    spam_control = "✅" if app_data.get('Spam_control', True) else "❌"
    game = "✅" if app_data.get('game', False) else "❌"
    music = "✅" if app_data.get('music', False) else "❌"

    status_message = f"""┏━━━ {Msg.EMOJI_CROWN} <b>USER STATUS</b> ━━━

👤 <b>User Details:</b>
• <b>Name:</b> {user_name}
• <b>Username:</b> {username_str}
• <b>User ID:</b> <code>{user_id}</code>
• <b>Userbot Status:</b> {userbot_status}
• <b>Uptime:</b> {uptime}

{Msg.EMOJI_GEAR} <b>Userbot settings:</b>
• Welcome message: {spam_control}
• Word chain bot: {game}
• Music bot: {music}
┗━━━━━━━━━━━━━━━━━━"""

    await message.reply(status_message, parse_mode=ParseMode.HTML)


# ─────────────────────────── inline query ──────────────────────────────────
@Client.on_inline_query()
async def inline_query_handler(client, query: InlineQuery):
    user_id = query.from_user.id
    command_args = query.query.split()

    # `banall <chat_id>` — build a confirmation card driven by the owner's userbot
    if len(command_args) == 2 and command_args[0].lower() == 'banall':
        try:
            chat_id = int(command_args[1])
        except ValueError:
            result = InlineQueryResultArticle(
                id="banall_invalid_id",
                title="BANALL - Invalid ID",
                description="Invalid chat ID format",
                input_message_content=InputTextMessageContent(plain_text("❌ Invalid chat ID format")),
            )
            return await query.answer(results=[result], cache_time=0)

        userbot = clients.get(user_id)
        if not userbot:
            result = InlineQueryResultArticle(
                id="banall_no_client",
                title="BANALL - No Client",
                description="Userbot not active",
                input_message_content=InputTextMessageContent(plain_text("❌ Your userbot is not active")),
            )
            return await query.answer(results=[result], cache_time=0)

        try:
            member = await userbot.get_chat_member(chat_id, user_id)
            is_owner = member.status == ChatMemberStatus.OWNER
            is_admin_ok = (
                member.status == ChatMemberStatus.ADMINISTRATOR
                and member.privileges and member.privileges.can_restrict_members
            )
            if not (is_owner or is_admin_ok):
                result = InlineQueryResultArticle(
                    id="banall_no_perms",
                    title="BANALL - No Permission",
                    description="You need admin + ban-users permission",
                    input_message_content=InputTextMessageContent(
                        plain_text("❌ You need admin rights with 'ban users' permission in this group.")
                    ),
                )
                return await query.answer(results=[result], cache_time=0)

            chat = await userbot.get_chat(chat_id)
            members_count = await userbot.get_chat_members_count(chat_id)
            banall_message = (
                f"⚠️ <b>Confirm Ban All Users</b> ⚠️\n\n"
                f"<b>Group:</b> {chat.title}\n"
                f"<b>Total Members:</b> {members_count}\n\n"
                f"Please confirm if you want to ban all users of this group."
            )
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"banall_cancel_{chat_id}", style=ButtonStyle.DANGER),
                InlineKeyboardButton("✅ Confirm", callback_data=f"banall_confirm_{chat_id}", style=ButtonStyle.SUCCESS),
            ]])
            result = InlineQueryResultArticle(
                id=f"banall_{chat_id}",
                title="BANALL - Confirm",
                description=f"Ban all users in {chat.title}",
                input_message_content=InputTextMessageContent(banall_message, parse_mode=ParseMode.HTML),
                reply_markup=buttons,
            )
            return await query.answer(results=[result], cache_time=0)
        except Exception as e:
            result = InlineQueryResultArticle(
                id="banall_error",
                title="BANALL - Error",
                description="Failed to check permissions",
                input_message_content=InputTextMessageContent(plain_text(f"❌ Error: {e}")),
            )
            return await query.answer(results=[result], cache_time=0)

    # Default: a status card
    info = query.from_user
    name = (info.first_name or "") + (f" {info.last_name}" if info.last_name else "")
    username = f"@{info.username}" if info.username else "No username"
    connected = clients.get(user_id) is not None
    status_message = (
        f"<blockquote>{Msg.EMOJI_STAR} <b>NUB Userbot</b></blockquote>\n"
        f"<b>Name:</b> {name}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>User ID:</b> <code>{user_id}</code>\n"
        f"<blockquote><i>Userbot status: {'Connected 🟢' if connected else 'Disconnected 🔴'}</i></blockquote>"
    )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("COMMANDS", callback_data="back", style=ButtonStyle.PRIMARY)]])
    result = InlineQueryResultArticle(
        id=str(user_id),
        title="STATUS",
        description="Check your userbot status",
        input_message_content=InputTextMessageContent(status_message, parse_mode=ParseMode.HTML),
        reply_markup=buttons,
    )
    await query.answer(results=[result], cache_time=0)


# ─────────────────────────── banall callbacks ──────────────────────────────
@Client.on_callback_query(filters.regex(r"^banall_(cancel|confirm)_(-?\d+)"))
async def banall_callback_handler(client, callback_query: CallbackQuery):
    match = callback_query.matches[0]
    action = match.group(1)
    chat_id = int(match.group(2))
    sender = callback_query.from_user.id

    if action != "confirm":
        return await callback_query.edit_message_text("❌ Command cancelled")

    userbot = clients.get(sender)
    if not userbot:
        return await callback_query.edit_message_text("❌ Userbot not available")

    try:
        chat = await userbot.get_chat(chat_id)
        banned_count = 0
        total_users = 0
        async for member in userbot.get_chat_members(chat_id):
            total_users += 1
            try:
                if member.user.id != sender:
                    await userbot.ban_chat_member(chat_id, member.user.id)
                    banned_count += 1
                    if banned_count % 10 == 0:
                        try:
                            await callback_query.edit_message_text(
                                f"🔨 <b>Banning in progress...</b>\n\n"
                                f"<b>Group:</b> {chat.title}\n"
                                f"<b>Banned:</b> {banned_count}/{total_users}",
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
            except Exception:
                continue
        rate = (banned_count / total_users * 100) if total_users else 0
        await callback_query.edit_message_text(
            f"✅ <b>Ban All Completed</b>\n\n"
            f"<b>Group:</b> {chat.title}\n"
            f"<b>Total Members:</b> {total_users}\n"
            f"<b>Successfully Banned:</b> {banned_count}\n"
            f"<b>Success Rate:</b> {rate:.1f}%",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await callback_query.edit_message_text(f"❌ Error during ban process: {e}")


# ─────────────────────────── /stop & /restart ──────────────────────────────
# These control the single running userbot process, so they are owner-only.
# is_admin() is true for the account whose session this bot pairs with
# (main.py registers clients[me.id] = userbot at startup). We also snapshot
# every confirmed owner into _known_owners so /restart still recognizes the
# owner after /stop has removed them from `clients`. Without this gate any
# stranger who DMs the bot could pause your userbot.
_known_owners = set()


def _is_owner(user_id):
    """Owner check that survives /stop. Live `clients` membership is the source
    of truth; once seen, an owner is remembered so they can /restart afterwards."""
    if is_admin(user_id):
        _known_owners.add(user_id)
        return True
    return user_id in _known_owners


@Client.on_message(filters.command("stop") & filters.private)
async def stop_handler(client, message: Message):
    sender = message.from_user.id
    if not _is_owner(sender):
        return await message.reply(
            f"{Msg.EMOJI_LOCK} <b>Owner only.</b> This command is restricted to the userbot owner.",
            parse_mode=ParseMode.HTML,
        )

    userbot = clients.get(sender)
    if userbot is None:
        return await message.reply(
            f"{Msg.EMOJI_INFO} <b>Userbot is already stopped.</b>\n"
            f"╰▸ Use /restart to bring it back online.",
            parse_mode=ParseMode.HTML,
        )
    await message.reply(
        f"{Msg.EMOJI_WARNING} <b>Stopping userbot...</b>\n"
        f"╰▸ Use /restart to bring it back online.",
        parse_mode=ParseMode.HTML,
    )
    try:
        await userbot.stop()
    except Exception as e:
        logger.warning(f"[BOT] Error stopping userbot: {e}")
    clients.pop(sender, None)


@Client.on_message(filters.command("restart") & filters.private)
async def restart_handler(client, message: Message):
    sender = message.from_user.id
    if not _is_owner(sender):
        return await message.reply(
            f"{Msg.EMOJI_LOCK} <b>Owner only.</b> This command is restricted to the userbot owner.",
            parse_mode=ParseMode.HTML,
        )

    await message.reply(
        f"{Msg.EMOJI_LOADING} <b>Restarting...</b>\n"
        f"╰▸ The process will relaunch in a moment.",
        parse_mode=ParseMode.HTML,
    )
    # Give the reply a moment to flush before we replace the process image.
    await asyncio.sleep(1)
    logger.info("[BOT] Restart requested by owner %s; re-executing process.", sender)
    os.execv(sys.executable, [sys.executable, *sys.argv])
