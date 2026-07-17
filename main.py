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
            plugins=dict(root="bot")
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
        plugins=dict(root="userbot")
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
                print(f"Bot started successfully!")
                print(f"Bot logged in as: {app.me.first_name} (@{app.me.username})")
            except Exception as e:
                print(f"Bot client failed to start (continuing without it): {e}")

        # Start userbot client
        await userbot.start()
        userbot_started = True
        print(f"Userbot started successfully!")
        print(f"Userbot logged in as: {userbot.me.first_name} (@{userbot.me.username})")

        # Add to clients dict for compatibility
        clients[userbot.me.id] = userbot

        # Load sudo users from database
        user_data = user_sessions.find_one({"user_id": userbot.me.id})
        if user_data and "sudoers" in user_data:
            SUDO[userbot.me.id] = user_data["sudoers"]

    except Exception as e:
        print(f"Error starting clients: {e}")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())