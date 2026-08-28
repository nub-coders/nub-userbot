import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.enums import ChatMemberStatus

from tools import *
from userbot.admin import is_user_admin
from utils.message import Msg

logger = logging.getLogger("userbot.moderation")


@Client.on_message(filters.command("banall", prefixes=HARDCODED_PREFIXES) & filters.me)
async def inline_handler_ban(client, message):
    if apps.get("app") is None:
        await message.edit_text("❌ Companion bot is not configured/started. Cannot run inline command.")
        return
    try:
        # Get inline bot results
        results = await client.get_inline_bot_results(apps.get("app").me.username, query=f"banall {message.chat.id}")

        if results.results:
            # Get the first result ID
            first_result_id = results.results[0].id

            # Send the first inline result
            await client.send_inline_bot_result(
                chat_id=message.chat.id,
                query_id=results.query_id,
                result_id=first_result_id
            )
        else:
            await message.reply(Msg.ERR_NO_INLINE_RESULTS)
    except Exception as e:
        await message.reply(styled_error(f"Error: {e}"))


@Client.on_message(filters.command("unbanall", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def unban_all_users(client, message):
    """Unban all users from the chat without confirmation"""
    try:
        # The command is open to sudo users, so the *sender* has to be authorized
        # too. The check below only asks whether the account has the right to
        # unban, which any sudo user could borrow: an ordinary member could
        # otherwise wipe the whole ban list of any group the operator moderates.
        # Nine sibling commands in admin.py already gate on this.
        if not message.from_user or not await is_user_admin(client, message.chat.id, message.from_user.id):
            await message.reply(Msg.ERR_ADMIN_REQUIRED)
            return

        await delete_if_self(message)

        chat_id = message.chat.id

        # Check if user has admin permissions
        try:

            member = await client.get_chat_member(chat_id, client.me.id)
            if member.status == ChatMemberStatus.ADMINISTRATOR and not member.privileges.can_restrict_members:
                await client.send_message(
                    chat_id,
                    Msg.ERR_UNBAN_PERMISSION
                )
                return

        except Exception as e:
            await client.send_message(chat_id, styled_error(f"Permission check failed: {str(e)}"))
            return

        # Get chat info
        chat = await client.get_chat(chat_id)

        # Send initial status message
        status_msg = await client.send_message(
            chat_id,
            f"🔄 {f'Starting unban for {chat.title}...'}"
        )

        unbanned_count = 0
        failed_count = 0

        try:
            await status_msg.edit(f"🔄 Unbanning users...")

            total_processed = 0

            # Unban users directly during iteration
            async for member in client.get_chat_members(chat_id, filter=enums.ChatMembersFilter.BANNED):
                if not member.user:
                  continue
                total_processed += 1

                try:
                    await client.unban_chat_member(chat_id, member.user.id)
                    unbanned_count += 1

                    # Update progress every 10 unbans
                    if total_processed % 10 == 0:
                        progress_block = (
                            f"<b>🔄 Unban in Progress</b>\n\n"
                            f"<blockquote>\n"
                            f"<b>• Processed:</b> {total_processed}\n"
                            f"<b>• Unbanned:</b> {unbanned_count}\n"
                            f"<b>• Failed:</b> {failed_count}\n"
                            f"</blockquote>"
                        )

                        try:
                            await status_msg.edit(progress_block, parse_mode=enums.ParseMode.HTML)
                        except Exception as e:
                            logger.debug(f"Unban-all progress edit failed: {e}")

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to unban user {member.user.id}: {e}")
                    continue

            if total_processed == 0:
                await status_msg.edit(f"<b>{Msg.EMOJI_INFO} No Banned Users</b>\n\n<blockquote>No banned members found in this chat.</blockquote>", parse_mode=enums.ParseMode.HTML)
                return

            rate = (unbanned_count / total_processed * 100) if total_processed else 0
            final_block = (
                f"<b>✅ Unban All Completed</b>\n\n"
                f"<blockquote>\n"
                f"<b>• Chat:</b> {chat.title}\n"
                f"<b>• Total Processed:</b> {total_processed}\n"
                f"<b>• Successfully Unbanned:</b> {unbanned_count}\n"
                f"<b>• Failed:</b> {failed_count}\n"
                f"<b>• Success Rate:</b> {rate:.1f}%\n"
                f"</blockquote>\n\n"
                f"<i>🎉 All eligible banned members have been unrestricted.</i>"
            )

            await status_msg.edit(final_block, parse_mode=enums.ParseMode.HTML)


        except Exception as e:
            await status_msg.edit(styled_error(f"Unban error: {str(e)}"))


    except Exception as e:
        try:
            await client.send_message(
                message.chat.id,
                styled_error(f"Unban all failed: {str(e)}")
            )
        except Exception as inner:
            logger.debug(f"Unban-all error report failed: {inner}")
