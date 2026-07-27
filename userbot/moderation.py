import asyncio
import logging

from pyrogram import Client, filters, enums
from pyrogram.enums import ChatMemberStatus

from tools import *
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
                        progress_message = f"""🔄 Unban in progress...

📊 Processed: {total_processed}
✅ Unbanned: {unbanned_count}
❌ Failed: {failed_count}
📈 Success Rate: {(unbanned_count/total_processed)*100:.1f}%"""

                        try:
                            await status_msg.edit(progress_message)
                        except Exception as e:
                            logger.debug(f"Unban-all progress edit failed: {e}")  # usually rate limits

                    # Small delay to avoid rate limits
                    await asyncio.sleep(0.1)

                except Exception as e:
                    failed_count += 1
                    logger.error(f"Failed to unban user {member.user.id}: {e}")
                    continue

            if total_processed == 0:
                await status_msg.edit(Msg.INFO_NO_BANNED_USERS)
                return

            # Final result
            final_message = f"""✅ Unban All Completed

📊 **Results:**
👥 Total Processed: {total_processed}
✅ Successfully Unbanned: {unbanned_count}
❌ Failed to Unban: {failed_count}
📈 Success Rate: {(unbanned_count/total_processed)*100:.1f}%

🎉 All eligible users have been unbanned from {chat.title}"""

            await status_msg.edit(final_message)

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
