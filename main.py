import os
import asyncio
import logging

from pyrogram import Client, idle
from convopyro import Conversation
from config import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

logger = logging.getLogger("userbot")

print("Starting Userbot...")

async def main():
    # Get session string from environment or user input
    session_string = SESSION_STR if SESSION_STR else input("Enter your Pyrogram session string: ")

    # Initialize bot client with bot-specific plugins only. The bot is optional —
    # it only powers inline/special-group features. Skip it entirely when no
    # BOT_TOKEN is configured so nothing registers a dead client in apps["app"].
    app = None
    if BOT_TOKEN:
        app = Client(
            "main_bot",
            api_id=API_ID,
            api_hash=API_HASH,
            bot_token=BOT_TOKEN,
            in_memory=True,
            sleep_threshold=30,
            plugins=dict(
                root="plugins",
                include=["inline", "botcmds"]  # Bot-specific plugins: inline queries and the /start-/commands-/settings control surface
            )
        )
        apps["app"] = app

        # Initialize conversation for the bot
        Conversation(app)

    # Initialize userbot client with userbot-specific plugins
    userbot = Client(
        "userbot_session",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_string,
        plugins=dict(
            root="plugins",
            include=[
                "account",      # Profile management, clone/revert
                "admin",        # Group admin commands (ban/kick/mute/promote/pin)
                "afk",          # AFK system with mentions
                "ai",           # AI chat and commands
                "antyspam",     # Spam control and protection
                "clone",        # Profile cloning functionality
                "dmtools",      # DM spam and raid commands
                "eval",         # Code evaluation
                "font",         # Text formatting styles
                "forward",      # Message forwarding automation
                "gcast",        # Global broadcast messaging
                "game_solver",  # Game solving functionality
                "group_tools",  # Group management tools
                "info",         # User and chat information
                "music",        # Music related commands
                "nettools",     # Network tools (ping/tcp/speed/calc)
                "ocr",          # Optical character recognition
                "purge",        # Message deletion and purging
                "react",        # Reaction handling
                "schedule",     # Scheduled message sending
                "spam",         # Spam commands
                "status",       # Status and alive commands
                "stickers",     # Sticker management and creation
                "sudo",         # Sudo commands
                "userbot",      # Core userbot functionality
                "vctools",      # Voice chat tools
                "welcome",      # Welcome messages
                "wordchain",    # Word chain game
                "wordgrider",   # Word grider game
                "wordseek_auto" # Word seek automation
            ]
        )
    )
    
    # Initialize conversation for userbot
    Conversation(userbot)

    bot_started = False
    userbot_started = False
    try:
        # Start bot client if it was created. A bot failure (e.g. FLOOD_WAIT
        # on auth.ImportBotAuthorization) must NOT take down the userbot — the
        # bot client only powers inline/special-group features.
        if app is not None:
            try:
                await app.start()
                bot_started = True
                bot_me = await app.get_me()
                print(f"Bot started successfully!")
                print(f"Bot logged in as: {bot_me.first_name} (@{bot_me.username})")
            except Exception as e:
                print(f"Bot client failed to start (continuing without it): {e}")

        # Start userbot client
        await userbot.start()
        userbot_started = True
        me = await userbot.get_me()
        print(f"Userbot started successfully!")
        print(f"Userbot logged in as: {me.first_name} (@{me.username})")

        # Add to clients dict for compatibility
        clients[me.id] = userbot

        # Load sudo users from database
        user_data = user_sessions.find_one({"user_id": me.id})
        if user_data and "sudoers" in user_data:
            SUDO[me.id] = user_data["sudoers"]

        # Keep both clients running
        await idle()

    except Exception as e:
        print(f"Error starting clients: {e}")
    finally:
        if bot_started:
            await app.stop()
        if userbot_started:
            await userbot.stop()

if __name__ == "__main__":
    asyncio.run(main())