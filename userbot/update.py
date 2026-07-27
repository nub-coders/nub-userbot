import hashlib
import logging
import os
import sys

from pyrogram import Client, filters

from tools import *

logger = logging.getLogger("userbot.update")

REQUIREMENTS = os.path.join(os.getcwd(), "requirements.txt")


def _requirements_hash():
    try:
        with open(REQUIREMENTS, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except FileNotFoundError:
        return None


@Client.on_message(filters.command("update", prefixes=HARDCODED_PREFIXES) & filters.me)
async def update_handler(client, message):
    """Pull latest code, reinstall deps if requirements.txt changed, then restart."""
    status = await edit_or_reply(message, "🔄 **Updating...**\n┃ Pulling latest code...")

    before = _requirements_hash()
    out, err, code, _ = await run_cmd("git pull --ff-only")
    if code != 0:
        await status.edit_text(styled_error(f"git pull failed:\n{err or out}"))
        return

    if "Already up to date" in out:
        await status.edit_text("✅ **Already up to date.**")
        return

    # Reinstall only when requirements.txt actually changed — avoids a slow
    # pip run on every code-only update.
    if _requirements_hash() != before:
        await status.edit_text("📦 **Dependencies changed — reinstalling...**")
        _, pip_err, pip_code, _ = await run_cmd(
            f"{sys.executable} -m pip install -r {REQUIREMENTS}"
        )
        if pip_code != 0:
            await status.edit_text(styled_error(f"pip install failed:\n{pip_err[-500:]}"))
            return

    await status.edit_text("♻️ **Update applied. Restarting...**")
    logger.info("[UPDATE] Update pulled; re-executing process.")
    # Replace the process image so the new code takes effect. Matches the
    # bot-side /restart handler.
    os.execv(sys.executable, [sys.executable, *sys.argv])
