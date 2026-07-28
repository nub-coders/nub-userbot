import logging

from pyrogram import Client, filters

from tools import *
from utils.message import Msg

logger = logging.getLogger("userbot.help")


@Client.on_message(filters.command("help", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def help_handler(client, message):
    """Shows detailed command usage — .help <command> or .help for categories overview"""
    try:
        # Detect user's prefix from the message
        prefix = message.text[0] if message.text else "."

        raw_args = get_args(message)

        # get_args returns list, False, or string
        if isinstance(raw_args, list):
            args = " ".join(raw_args).strip().lower()
        elif isinstance(raw_args, str):
            args = raw_args.strip().lower()
        else:
            args = ""

        # No arguments → show categories overview
        if not args:
            await edit_or_reply(message, styled_help_categories(categories, prefix))
            return

        # Search for the command in the global commands dict
        cmd_name = args.split()[0].lstrip("".join(HARDCODED_PREFIXES))

        if cmd_name in commands:
            raw = commands[cmd_name]
            desc, usage, example, note, warning, flags = parse_help_entry(raw)

            # Replace [prefix] placeholder with user's actual prefix
            usage = usage.replace("[prefix]", prefix)
            example = example.replace("[prefix]", prefix)
            flags = flags.replace("[prefix]", prefix)

            card = styled_help_card(
                cmd_name, desc, usage,
                example=example, note=note, flags=flags, warning=warning
            )
            await edit_or_reply(message, card)
            return

        # Fuzzy search — check if it's a partial match
        matches = [c for c in commands if cmd_name in c or c in cmd_name]
        if matches:
            match_list = ", ".join(f"`{prefix}{m}`" for m in matches[:10])
            await edit_or_reply(
                message,
                f"{Msg.WARN_CMD_NOT_FOUND}\n\n"
                f"┃ 🔍 Did you mean?\n"
                f"┃  {match_list}\n"
                f"╰━━━━━━━━━━━━━━━━━━━━╯"
            )
            return

        # Nothing found at all
        await edit_or_reply(
            message,
            f"Unknown Command\n\n"
            f"┃ {f'No help found for: {cmd_name}'}\n"
            f"┃ 💡 {f'Use {prefix}help to see all categories'}\n"
            f"╰━━━━━━━━━━━━━━━━━━━━╯"
        )

    except Exception as e:
        logger.error(f"[HELP] Error: {e}")
        await edit_or_reply(message, styled_error(f"Help error: {str(e)[:50]}"))
