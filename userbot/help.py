import logging

from pyrogram import Client, filters

from tools import *
from utils.message import Msg

logger = logging.getLogger("userbot.help")


def _parse_help_entry(raw_text):
    """Parse a raw help entry into structured fields."""
    desc = usage = example = note = warning = flags = ""
    lines = raw_text.strip().split("\n")
    for line in lines:
        line = line.strip()
        ll = line.lower()
        if ll.startswith("**usage:**"):
            usage = line.split("**Usage:**", 1)[-1].strip()
        elif ll.startswith("**example:**"):
            example = line.split("**Example:**", 1)[-1].strip()
        elif ll.startswith("**examples:**"):
            example = line.split("**Examples:**", 1)[-1].strip()
        elif ll.startswith("**flags:**"):
            flags = line.split("**Flags:**", 1)[-1].strip()
        elif ll.startswith("**note:**"):
            note = line.split("**Note:**", 1)[-1].strip()
        elif ll.startswith("**warning:**"):
            warning = line.split("**Warning:**", 1)[-1].strip()
        elif ll.startswith("**features:**"):
            note = line.split("**Features:**", 1)[-1].strip()
        elif ll.startswith("**options:**"):
            flags = line.split("**Options:**", 1)[-1].strip()
        elif ll.startswith("**supported:**"):
            note = line.split("**Supported:**", 1)[-1].strip()
        elif " - " in line and not desc:
            desc = line.split(" - ", 1)[-1].strip()
    if not desc and lines:
        first = lines[0].strip().strip("*")
        if " - " in first:
            desc = first.split(" - ", 1)[-1].strip()
        else:
            desc = first
    return desc, usage, example, note, warning, flags


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
            desc, usage, example, note, warning, flags = _parse_help_entry(raw)

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
