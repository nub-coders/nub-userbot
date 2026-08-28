import os
import asyncio
import logging
import sys

from pyrogram import Client, idle
from convopyro import Conversation
from config import *
from plugin_loader import load_extra_plugins
from userbot.game_solver import warm_solver

# Strong references to fire-and-forget tasks; asyncio only holds weak ones.
background_tasks = set()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s - [%(filename)s:%(lineno)d]'
)

logger = logging.getLogger("userbot")

print("Starting Userbot...")

async def main():
    # Get session string from environment, or prompt when a human is attached.
    # `input()` unconditionally was a trap under Docker or a service manager:
    # stdin is not a tty there, and the os.execv restarts in userbot/update.py
    # and bot/botcmds.py re-enter this line, where a prompt either raises
    # EOFError or blocks forever on a pipe. Say what is missing instead.
    if SESSION_STR:
        session_string = SESSION_STR
    elif sys.stdin.isatty():
        session_string = input("Enter your Pyrogram session string: ")
    else:
        print("SESSION_STR is not set and stdin is not a terminal -- set it in .env.")
        raise SystemExit(1)

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

    try:
        # Start bot client if it was created. A bot failure (e.g. FLOOD_WAIT
        # on auth.ImportBotAuthorization) must NOT take down the userbot — the
        # bot client only powers inline/special-group features. Only a client
        # that actually connected goes into apps["app"]: tools._BotProxy falls
        # back to the userbot when it's absent, but a dead client parked there
        # would defeat that fallback and raise ConnectionError instead.
        if app is not None:
            try:
                await app.start()
                apps["app"] = app
                print(f"Bot started successfully!")
                print(f"Bot logged in as: {app.me.first_name} (@{app.me.username})")
            except Exception as e:
                print(f"Bot client failed to start (continuing without it): {e}")

        # Start userbot client. Unlike the bot above, this client is the whole
        # point of the process, so a failure here has to end it: exit non-zero
        # rather than fall through to idle(). Idling with zero handlers looks
        # perfectly healthy from outside -- the process is up and never exits --
        # so compose's `restart: unless-stopped` never fires and the userbot
        # stays silently down until somebody notices by hand.
        try:
            await userbot.start()
        except Exception as e:
            print(f"Userbot client failed to start: {e}")
            raise SystemExit(1)

        print(f"Userbot started successfully!")
        print(f"Userbot logged in as: {userbot.me.first_name} (@{userbot.me.username})")

        # Add to clients dict for compatibility
        clients[userbot.me.id] = userbot

        # Load sudo users from database
        user_data = user_sessions.find_one({"user_id": userbot.me.id})
        if user_data and "sudoers" in user_data:
            SUDO[userbot.me.id] = user_data["sudoers"]

        # Load external community plugins (no repo fork needed)
        loaded_extra_plugins.extend(load_extra_plugins(userbot, EXTRA_PLUGINS_DIR))
        if loaded_extra_plugins:
            print(f"Loaded {len(loaded_extra_plugins)} extra plugin(s): {', '.join(loaded_extra_plugins)}")

        # Build the WordSeek solver in a worker thread now, so no message
        # handler has to. It indexes the whole word list (~0.3s of CPU), and it
        # used to be built lazily inside auto_play_handler -- which runs for
        # every outgoing group message -- stalling the event loop there.
        # Referenced so the task is not garbage collected mid-flight.
        warmup_task = asyncio.create_task(warm_solver())
        background_tasks.add(warmup_task)
        warmup_task.add_done_callback(background_tasks.discard)

    except Exception as e:
        # Reached only for the bookkeeping after a successful start (sudo list,
        # extra plugins). Those are not worth refusing to run over -- the client
        # is connected and its handlers are registered. SystemExit is a
        # BaseException, so a failed start above passes straight through.
        print(f"Error after starting clients: {e}")
    await idle()

if __name__ == "__main__":
    asyncio.run(main())