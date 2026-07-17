import asyncio
import random
import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from tools import (
    HARDCODED_PREFIXES, edit_or_reply, sudoers_filter, retry,
    is_admin_user, get_args_from_caret, RAID
)
from utils.message import Msg

logger = logging.getLogger("userbot")


async def _dm_blast(client, message, *, verb, emoji, needs_text, make_provider, done_msg, sent_emoji):
    """Shared DM flood loop for dmspam/dmraid.

    make_provider(args) -> callable returning the text to send on each iteration.
    """
    try:
        args = get_args_from_caret(message)

        # Get target user
        if message.reply_to_message and message.reply_to_message.from_user:
            target_user = message.reply_to_message.from_user
            if needs_text:
                if not args or len(args) < 2:
                    await edit_or_reply(message, f"Usage: reply + [prefix]dm{verb} <count> <msg>")
                    return
            else:
                if not args:
                    await edit_or_reply(message, f"Usage: reply + [prefix]dm{verb} <count>")
                    return
            try:
                count = int(args[0])
            except ValueError:
                await edit_or_reply(message, Msg.ERR_INVALID_COUNT_NUMBER)
                return
        else:
            await edit_or_reply(message, Msg.ERR_REPLY_USER_MSG)
            return

        if count < 1 or count > 100:
            await edit_or_reply(message, Msg.ERR_COUNT_1_100)
            return

        provider = make_provider(args)

        if needs_text:
            preview = provider()
            if not preview or len(preview.strip()) == 0:
                await edit_or_reply(message, "Provide a message to spam")
                return

        if is_admin_user(target_user.id):
            return await edit_or_reply(message, f"Cannot DM {verb} the owner")

        status = await edit_or_reply(message, f"{emoji} DM {verb}ing {target_user.mention}...")

        success_count = 0
        failed_count = 0

        for i in range(count):
            try:
                await client.send_message(target_user.id, provider())
                success_count += 1
                await asyncio.sleep(0.15)  # Delay to avoid flood
            except FloodWait as e:
                await asyncio.sleep(e.value)
                await client.send_message(target_user.id, provider())
                success_count += 1
            except Exception as e:
                failed_count += 1
                if "blocked" in str(e).lower() or "user_is_blocked" in str(e).lower():
                    await status.edit(f"❌ **User has blocked the bot!**\n✅ Sent: {success_count}/{count}")
                    return

        await status.edit(
            f"{done_msg}\n\n"
            f"┃ {sent_emoji} Sent: {success_count}/{count}\n"
            f"┃ ❌ Failed: {failed_count}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯"
        )

    except Exception as e:
        await edit_or_reply(message, f"❌ **Error:** {str(e)}")


@Client.on_message(filters.command("dmspam", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()) & filters.group)
async def dmspam(client: Client, message: Message):
    """Spam a user in their DM - works only in groups when replying to a user"""
    await _dm_blast(
        client, message,
        verb="spam", emoji="📨", needs_text=True,
        make_provider=lambda args: (lambda: " ".join(args[1:])),
        done_msg=Msg.OK_DM_SPAM_DONE, sent_emoji="📨",
    )


@Client.on_message(filters.command("dmraid", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()) & filters.group)
async def dmraid(client: Client, message: Message):
    """Raid a user in their DM with random messages - works only in groups when replying to a user"""
    await _dm_blast(
        client, message,
        verb="raid", emoji="💥", needs_text=False,
        make_provider=lambda args: (lambda: random.choice(RAID)),
        done_msg=Msg.OK_DM_RAID_DONE, sent_emoji="💥",
    )
