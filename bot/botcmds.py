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

from utils.custom_emojis import (
    ICON_SUCCESS,
    ICON_CANCEL,
    ICON_SETTINGS,
    ICON_ROCKET,
    ICON_BACK,
    ICON_DOWNLOAD,
)

logger = logging.getLogger("userbot")


brief_explanation = f"""<h1>{Msg.EMOJI_ROCKET} NUB USERBOT</h1>

<p><b>Ultimate Telegram Automation &amp; Multi-tool System</b></p>

<table border="1">
<tr><th>Feature</th><th>Description</th></tr>
<tr><td>{Msg.EMOJI_MUSIC} Voice Player</td><td>Stream YouTube audio/video in calls with full queue control</td></tr>
<tr><td>{Msg.EMOJI_NOTE} Media Saver</td><td>Automatically save disappearing &amp; restricted media</td></tr>
<tr><td>{Msg.EMOJI_SHIELD} Restricted Chats</td><td>Download content from private channels &amp; groups</td></tr>
<tr><td>{Msg.EMOJI_DOWNLOAD} Downloader</td><td>Fast multi-link Telegram &amp; HTTP media downloader</td></tr>
<tr><td>{Msg.EMOJI_GEAR} AI &amp; Tools</td><td>Agentic AI search, anti-spam, auto-reactions &amp; custom prefixes</td></tr>
</table>

<details>
<summary>⚡ Quick Navigation Guide</summary>

<p><code>/commands</code> — Browse all commands by category</p>
<p><code>/settings</code> — Customize preferences &amp; toggle modes</p>
<p><code>/status</code> — Inspect live bot metrics &amp; session status</p>
<p><code>/ping</code> — Test server latency &amp; system health</p>

</details>

<blockquote>
{Msg.EMOJI_STAR} Community: @{GROUP} | {Msg.EMOJI_ROCKET} Updates: @{CHANNEL}
</blockquote>"""


def build_settings_ui(user_data: dict):
    """Build the settings message text and keyboard from user_data using native tables and ButtonStyle."""
    spam_control  = user_data.get('Spam_control', True)
    game_control  = user_data.get('game', False)
    music_control = user_data.get('music', False)
    react_control = user_data.get('react_control', False)
    delete_count  = user_data.get('delete_count', 0)
    block_count   = user_data.get('block_count', 0)
    react_emojis  = ['👍', '♥️', '🔥', '🎉']

    ON, OFF = '✅ Enabled', '❌ Disabled'

    # --- message with native HTML table ---
    text = (
        f"<h1>{Msg.EMOJI_GEAR} Userbot Settings</h1>\n\n"
        f'<table border="1">\n'
        f'<tr><th>Setting</th><th>Status</th></tr>\n'
        f'<tr><td>DM Welcome</td><td>{ON if spam_control else OFF}</td></tr>\n'
        f'<tr><td>Auto-delete</td><td>{str(delete_count) + " msgs" if (spam_control and delete_count > 0) else "Off"}</td></tr>\n'
        f'<tr><td>Auto-block</td><td>{str(block_count) + " msgs" if (spam_control and block_count > 0) else "Off"}</td></tr>\n'
        f'<tr><td>Word Chain Bot</td><td>{ON if game_control else OFF}</td></tr>\n'
        f'<tr><td>Music Plugin</td><td>{ON if music_control else OFF}</td></tr>\n'
        f'<tr><td>Auto Reaction</td><td>{react_emojis[react_control - 1] if react_control else "Off"}</td></tr>\n'
        f'</table>\n\n'
        f'<blockquote>Tap the buttons below to toggle options, then click Done to save.</blockquote>'
    )

    # --- keyboard with ButtonStyle ---
    welcome_mode = [
        InlineKeyboardButton(
            f"Auto-delete: {'['+str(delete_count)+']' if delete_count else 'Off'}",
            callback_data="toggle_delete_count",
            style=ButtonStyle.DANGER if delete_count else ButtonStyle.DEFAULT
        ),
        InlineKeyboardButton(
            f"Auto-block: {'['+str(block_count)+']' if block_count else 'Off'}",
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
            InlineKeyboardButton(
                f"Game: {'ON' if game_control else 'OFF'}",
                callback_data="toggle_game",
                style=ButtonStyle.SUCCESS if game_control else ButtonStyle.DANGER,
            ),
            InlineKeyboardButton(
                f"Music: {'ON' if music_control else 'OFF'}",
                callback_data="toggle_music",
                style=ButtonStyle.SUCCESS if music_control else ButtonStyle.DANGER,
            ),
        ],
        [
            InlineKeyboardButton(
                f"DM Welcome: {'ON' if spam_control else 'OFF'}",
                callback_data="toggle_Spam_control",
                style=ButtonStyle.SUCCESS if spam_control else ButtonStyle.DANGER,
            )
        ],
        *([welcome_mode] if spam_control else []),
        [
            InlineKeyboardButton(
                f"Auto React: {'ON' if react_control else 'OFF'}",
                callback_data="toggle_react_control",
                style=ButtonStyle.SUCCESS if react_control else ButtonStyle.DANGER,
            )
        ],
        *([react_mode] if react_control else []),
        [
            InlineKeyboardButton(
                "Save Preferences",
                callback_data="save_settings",
                style=ButtonStyle.SUCCESS,
                icon_custom_emoji_id=ICON_SUCCESS,
            )
        ],
    ]
    return text, InlineKeyboardMarkup(buttons)


def _commands_keyboard():
    """Build the category-picker keyboard used by /commands and the Back button."""
    keyboard_rows, row = [], []
    for category in categories.keys():
        row.append(
            InlineKeyboardButton(
                str(category),
                callback_data=f'category_{category}',
                style=ButtonStyle.PRIMARY,
            )
        )
        if len(row) == 2:
            keyboard_rows.append(row)
            row = []
    if row:
        keyboard_rows.append(row)
    return InlineKeyboardMarkup(keyboard_rows) if keyboard_rows else None


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
        if hasattr(message, "reply_rich"):
            try:
                from pyrogram.types import InputRichMessage
                await message.reply_rich(InputRichMessage(html=brief_explanation))
                return
            except Exception:
                pass
        await message.reply(brief_explanation, parse_mode=ParseMode.HTML)



# ─────────────────────────── authorization ─────────────────────────────────
# This is the *bot* client, not the userbot: anyone who finds the bot on Telegram
# can message it, so `filters.private` says where a message came from, not who is
# allowed. Handlers that report host telemetry, resolve arbitrary users, or write
# to the shared `user_sessions` store carry this filter; /start and the static
# command browser stay public because they disclose nothing. `_is_owner` is
# defined further down and looked up when the filter runs, not when it is built.
def _owner_filter():
    """Filter matching only the owner, for messages and callback queries alike."""
    async def func(_, __, update):
        user = getattr(update, "from_user", None)
        return bool(user and _is_owner(user.id))
    return filters.create(func)


# ─────────────────────────── /ping ─────────────────────────────────────────
@Client.on_message(filters.command("ping") & filters.private & _owner_filter())
async def ping_command(client, message: Message):
    uptime = await get_readable_time((time.time() - StartTime))
    start = datetime.datetime.now()
    xx = await message.reply("⏳ <b>Testing latency...</b>", parse_mode=ParseMode.HTML)
    end = datetime.datetime.now()
    delta_ping = round((end - start).microseconds / 1000, 3)

    cpu = psutil.cpu_percent()
    mem = psutil.virtual_memory().percent
    disk = psutil.disk_usage("/").percent
    process = psutil.Process()
    _ping = (
        f"<h1>{Msg.EMOJI_PONG} Pong! <code>{str(delta_ping).replace('.', ',')} ms</code></h1>\n\n"
        f'<table border="1">\n'
        f'<tr><th>Metric</th><th>Value</th></tr>\n'
        f'<tr><td>Ping Latency</td><td><code>{delta_ping} ms</code></td></tr>\n'
        f'<tr><td>System Uptime</td><td><code>{uptime}</code></td></tr>\n'
        f'<tr><td>CPU Usage</td><td><code>{cpu}%</code></td></tr>\n'
        f'<tr><td>RAM Usage</td><td><code>{mem}%</code></td></tr>\n'
        f'<tr><td>Disk Usage</td><td><code>{disk}%</code></td></tr>\n'
        f'<tr><td>Process Memory</td><td><code>{round(process.memory_info()[0] / 1024 ** 2)} MB</code></td></tr>\n'
        f'</table>'
    )
    await xx.edit(_ping, parse_mode=ParseMode.HTML)


# ─────────────────────────── /commands ─────────────────────────────────────
@Client.on_message(filters.command("commands") & filters.private)
async def commands_handler(client, message: Message):
    markup = _commands_keyboard()
    if markup is None:
        await message.reply(
            f"<h1>{Msg.EMOJI_PIN} Categories Unavailable</h1><p>No categories are currently loaded.</p>",
            parse_mode=ParseMode.HTML,
        )
        return
    await message.reply(
        f"<h1>{Msg.EMOJI_PIN} Command Browser</h1>\n\n"
        f"<p>Select a category below to explore its available commands and usages:</p>",
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )


@Client.on_callback_query(filters.regex(r'^category_'))
async def category_handler(client, callback_query: CallbackQuery):
    # Join back since category names may contain '_'
    category = '_'.join(callback_query.data.split('_')[1:])

    category_commands = categories.get(category, [])
    if category_commands:
        items = []
        for cmd in category_commands:
            raw = commands.get(cmd, 'Description not available')
            desc, usage, example, note, warning, flags = parse_help_entry(raw)
            clean_cmd = str(cmd).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            clean_desc = str(desc).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            clean_usage = str(usage).replace("[prefix]", ".").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;") if usage else f".{clean_cmd}"
            items.append(
                f"<details>\n"
                f"<summary><b>{clean_cmd}</b> — {clean_desc}</summary>\n\n"
                f"<p><b>Usage:</b> <code>{clean_usage}</code></p>\n"
                f"</details>"
            )
        category_description = "\n".join(items)
    else:
        category_description = "<p><i>No commands in this category yet.</i></p>"

    prefix_list = ", ".join(f"<code>{p}</code>" for p in HARDCODED_PREFIXES)
    prefix_info = f"<blockquote><b>Available Prefixes:</b> {prefix_list}</blockquote>"

    text = f"<h1>{Msg.EMOJI_ROCKET} {category} Commands</h1>\n\n{category_description}\n\n{prefix_info}"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("« Back to Categories", callback_data='back', style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ICON_BACK)]
    ])
    await callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r'^back$'))
async def back_handler(client, callback_query: CallbackQuery):
    markup = _commands_keyboard()
    if markup is None:
        await callback_query.edit_message_text(
            f"<h1>{Msg.EMOJI_PIN} Categories Unavailable</h1><p>No categories are currently loaded.</p>",
            parse_mode=ParseMode.HTML,
        )
        return
    await callback_query.edit_message_text(
        f"<h1>{Msg.EMOJI_PIN} Command Browser</h1>\n\n"
        f"<p>Select a category below to explore its available commands and usages:</p>",
        reply_markup=markup,
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────── /settings ─────────────────────────────────────
@Client.on_message(filters.command("settings") & filters.private & _owner_filter())
async def settings_handler(client, message: Message):
    sender_id = message.from_user.id
    user_data = user_sessions.find_one({"user_id": sender_id}) or {"user_id": sender_id}
    text, markup = build_settings_ui(user_data)
    await message.reply(text, reply_markup=markup, parse_mode=ParseMode.HTML)


@Client.on_callback_query(filters.regex(r"^toggle_") & _owner_filter())
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


@Client.on_callback_query(filters.regex(r"^save_settings$") & _owner_filter())
async def save_settings(client, callback_query: CallbackQuery):
    sender_id = callback_query.from_user.id
    user_data = user_sessions.find_one({"user_id": sender_id}) or {"user_id": sender_id}
    spam_control  = "Enabled" if user_data.get('Spam_control', True) else "Disabled"
    game_control  = "Enabled" if user_data.get('game', False) else "Disabled"
    music_control = "Enabled" if user_data.get('music', False) else "Disabled"

    success_html = (
        f"<h1>{Msg.EMOJI_SUCCESS} Settings Saved</h1>\n\n"
        f"<p>Your preferences have been successfully updated and applied:</p>\n\n"
        f'<table border="1">\n'
        f'<tr><th>Setting</th><th>Status</th></tr>\n'
        f'<tr><td>DM Welcome</td><td>{spam_control}</td></tr>\n'
        f'<tr><td>Word Chain Bot</td><td>{game_control}</td></tr>\n'
        f'<tr><td>Music Plugin</td><td>{music_control}</td></tr>\n'
        f'</table>'
    )
    await callback_query.edit_message_text(
        success_html,
        parse_mode=ParseMode.HTML,
    )


# ─────────────────────────── /status ───────────────────────────────────────
@Client.on_message(filters.command("status") & filters.private & _owner_filter())
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
    spam_control = "✅ Enabled" if app_data.get('Spam_control', True) else "❌ Disabled"
    game = "✅ Enabled" if app_data.get('game', False) else "❌ Disabled"
    music = "✅ Enabled" if app_data.get('music', False) else "❌ Disabled"

    status_message = (
        f"<h1>{Msg.EMOJI_CROWN} User Status</h1>\n\n"
        f'<table border="1">\n'
        f'<tr><th>User Attribute</th><th>Value</th></tr>\n'
        f'<tr><td>Name</td><td>{user_name}</td></tr>\n'
        f'<tr><td>Username</td><td>{username_str}</td></tr>\n'
        f'<tr><td>User ID</td><td><code>{user_id}</code></td></tr>\n'
        f'<tr><td>Userbot Status</td><td>{userbot_status}</td></tr>\n'
        f'<tr><td>Uptime</td><td>{uptime}</td></tr>\n'
        f'<tr><th>Bot Plugin</th><th>Status</th></tr>\n'
        f'<tr><td>DM Welcome</td><td>{spam_control}</td></tr>\n'
        f'<tr><td>Word Chain Bot</td><td>{game}</td></tr>\n'
        f'<tr><td>Music Player</td><td>{music}</td></tr>\n'
        f'</table>'
    )

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
                f"<h1>⚠️ Confirm Ban All Users</h1>\n\n"
                f'<table border="1">\n'
                f'<tr><th>Target Group</th><td>{chat.title}</td></tr>\n'
                f'<tr><th>Total Members</th><td>{members_count}</td></tr>\n'
                f'</table>\n\n'
                f"<blockquote>Please confirm if you want to ban all members in this group.</blockquote>"
            )
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton("❌ Cancel", callback_data=f"banall_cancel_{chat_id}", style=ButtonStyle.DANGER, icon_custom_emoji_id=ICON_CANCEL),
                InlineKeyboardButton("✅ Confirm Ban", callback_data=f"banall_confirm_{chat_id}", style=ButtonStyle.SUCCESS, icon_custom_emoji_id=ICON_SUCCESS),
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
        f"<h1>{Msg.EMOJI_STAR} NUB Userbot</h1>\n\n"
        f'<table border="1">\n'
        f'<tr><th>User</th><td>{name}</td></tr>\n'
        f'<tr><th>Username</th><td>{username}</td></tr>\n'
        f'<tr><th>User ID</th><td><code>{user_id}</code></td></tr>\n'
        f'<tr><th>Status</th><td>{"Connected 🟢" if connected else "Disconnected 🔴"}</td></tr>\n'
        f'</table>'
    )
    buttons = InlineKeyboardMarkup([[InlineKeyboardButton("COMMANDS", callback_data="back", style=ButtonStyle.PRIMARY, icon_custom_emoji_id=ICON_ROCKET)]])
    result = InlineQueryResultArticle(
        id=str(user_id),
        title="STATUS",
        description="Check your userbot status",
        input_message_content=InputTextMessageContent(status_message, parse_mode=ParseMode.HTML),
        reply_markup=buttons,
    )
    await query.answer(results=[result], cache_time=0)


# ─────────────────────────── banall callbacks ──────────────────────────────
@Client.on_callback_query(filters.regex(r"^banall_(cancel|confirm)_(-?\d+)") & _owner_filter())
async def banall_callback_handler(client, callback_query: CallbackQuery):
    match = callback_query.matches[0]
    action = match.group(1)
    chat_id = int(match.group(2))
    sender = callback_query.from_user.id

    if action != "confirm":
        return await callback_query.edit_message_text(
            f"<h1>❌ Action Cancelled</h1><p>The ban-all operation has been safely aborted.</p>",
            parse_mode=ParseMode.HTML,
        )

    userbot = clients.get(sender)
    if not userbot:
        return await callback_query.edit_message_text(
            f"<h1>❌ Userbot Unavailable</h1><p>Your userbot is not currently connected. Use <code>/restart</code> to reconnect.</p>",
            parse_mode=ParseMode.HTML,
        )

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
                                f"<h1>🔨 Banning in Progress</h1>\n\n"
                                f'<table border="1">\n'
                                f'<tr><th>Group</th><td>{chat.title}</td></tr>\n'
                                f'<tr><th>Banned</th><td>{banned_count} / {total_users}</td></tr>\n'
                                f'</table>',
                                parse_mode=ParseMode.HTML,
                            )
                        except Exception:
                            pass
            except Exception:
                continue
        rate = (banned_count / total_users * 100) if total_users else 0
        await callback_query.edit_message_text(
            f"<h1>✅ Ban All Completed</h1>\n\n"
            f'<table border="1">\n'
            f'<tr><th>Group</th><td>{chat.title}</td></tr>\n'
            f'<tr><th>Total Members</th><td>{total_users}</td></tr>\n'
            f'<tr><th>Successfully Banned</th><td>{banned_count}</td></tr>\n'
            f'<tr><th>Success Rate</th><td>{rate:.1f}%</td></tr>\n'
            f'</table>',
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        await callback_query.edit_message_text(
            f"<h1>❌ Error</h1><blockquote>{e}</blockquote>",
            parse_mode=ParseMode.HTML,
        )


# ─────────────────────────── /stop & /restart ──────────────────────────────
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
            f"<h1>{Msg.EMOJI_LOCK} Access Denied</h1>\n\n"
            f"<blockquote>This command is restricted to the userbot owner.</blockquote>",
            parse_mode=ParseMode.HTML,
        )

    userbot = clients.get(sender)
    if userbot is None:
        return await message.reply(
            f"<h1>{Msg.EMOJI_INFO} Userbot Already Stopped</h1>\n\n"
            f"<blockquote>Use <code>/restart</code> to bring it back online.</blockquote>",
            parse_mode=ParseMode.HTML,
        )
    await message.reply(
        f"<h1>{Msg.EMOJI_WARNING} Stopping Userbot</h1>\n\n"
        f"<blockquote>Use <code>/restart</code> to relaunch your session at any time.</blockquote>",
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
            f"<h1>{Msg.EMOJI_LOCK} Access Denied</h1>\n\n"
            f"<blockquote>This command is restricted to the userbot owner.</blockquote>",
            parse_mode=ParseMode.HTML,
        )

    await message.reply(
        f"<h1>{Msg.EMOJI_LOADING} Restarting Process</h1>\n\n"
        f"<blockquote>Relaunching userbot instance. Please stand by...</blockquote>",
        parse_mode=ParseMode.HTML,
    )
    # Give the reply a moment to flush before we replace the process image.
    await asyncio.sleep(1)
    logger.info("[BOT] Restart requested by owner %s; re-executing process.", sender)
    os.execv(sys.executable, [sys.executable, *sys.argv])

