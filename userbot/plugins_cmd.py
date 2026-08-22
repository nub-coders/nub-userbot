import logging

from pyrogram import Client, filters

from tools import *
from config import EXTRA_PLUGINS_DIR, loaded_extra_plugins

logger = logging.getLogger("userbot.plugins")


@Client.on_message(filters.command("plugins", prefixes=HARDCODED_PREFIXES) & (filters.me | sudoers_filter()))
async def plugins_handler(client, message):
    """Lists community plugins loaded from EXTRA_PLUGINS_DIR."""
    if loaded_extra_plugins:
        lines = []
        for idx, name in enumerate(loaded_extra_plugins, 1):
            lines.append(f"<b>{idx}.</b> <code>{name}</code> (Active 🟢)")
        text = (
            f"<b>🧩 Loaded Extra Plugins ({len(loaded_extra_plugins)})</b>\n\n"
            f"<blockquote>\n" + "\n".join(lines) + f"\n</blockquote>\n\n"
            f"📂 <b>Directory:</b> <code>{EXTRA_PLUGINS_DIR}</code>"
        )
    else:
        text = (
            f"<b>🧩 External Plugins</b>\n\n"
            f"<blockquote>No external plugins loaded. Drop <code>.py</code> plugin files into <code>{EXTRA_PLUGINS_DIR}</code> and restart.</blockquote>"
        )
    await edit_or_reply(message, text, parse_mode=enums.ParseMode.HTML)


