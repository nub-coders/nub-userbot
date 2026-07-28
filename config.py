import os
import time
import logging
import pymongo
import certifi
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Telegram API credentials
# Required: Get these from https://my.telegram.org
raw_api_id = os.getenv('API_ID', '').strip()
API_ID = int(raw_api_id) if raw_api_id.isdigit() else 0
API_HASH = os.getenv('API_HASH', '')

# Gemini API configuration
# Optional: Get from https://aistudio.google.com/app/apikey (needed for AI features)
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY', '')

# Optional: YT_DLP API Key for YouTube downloads
YT_DLP_API_KEY = os.getenv('YT_DLP_API_KEY', '')

# YT_DLP Base URL configuration
YT_DLP_BASE_URL = os.getenv('YT_DLP_BASE_URL', 'https://api.nubcoders.com')

# MongoDB connection (optional)
# Leave MONGO_URI empty to run fully in-memory (data is lost on restart).
MONGO_URI = os.getenv('MONGO_URI', '')
DB_NAME = os.getenv('DB_NAME', 'userbot')

from storage import MemoryCollection, SqliteCollection

# Backend selection: STORAGE_BACKEND=mongo|sqlite|memory. When unset, keep the
# original behavior — mongo if MONGO_URI is set, else memory.
STORAGE_BACKEND = os.getenv('STORAGE_BACKEND', '').strip().lower()
SQLITE_PATH = os.getenv('SQLITE_PATH', os.path.join(os.getcwd(), 'data', 'sessions.db'))


def _init_storage():
    backend = STORAGE_BACKEND or ('mongo' if MONGO_URI else 'memory')
    if backend == 'mongo':
        try:
            client = pymongo.MongoClient(
                MONGO_URI, tlsCAFile=certifi.where(), serverSelectionTimeoutMS=5000
            )
            # Force an actual connection so a bad URI/unreachable host fails fast here
            client.admin.command("ping")
            logger.info("Connected to MongoDB (database: %s)", DB_NAME)
            return client, client[DB_NAME]["user_sessions"]
        except Exception as e:
            logger.warning(
                "MongoDB connection failed (%s); falling back to in-memory storage. "
                "Data will not persist across restarts.", e
            )
            return None, MemoryCollection()
    if backend == 'sqlite':
        logger.info("Using SQLite storage at %s", SQLITE_PATH)
        return None, SqliteCollection(SQLITE_PATH)
    logger.info("Using in-memory storage. Data will not persist across restarts.")
    return None, MemoryCollection()


mongo_client, user_sessions = _init_storage()
db = mongo_client[DB_NAME] if mongo_client else None

# Command prefixes recognized by the userbot
HARDCODED_PREFIXES = ["!", ".", "?", "^", "_"]

# File-based admin list (legacy)
admin_file = os.path.join(os.getcwd(), "data", "admins.txt")

# Global variables
clients = {}
conversations = {}
chat_queues = {}
active_streams = {}
last_response_time = {}
used_words = {}
active = {}
songs_client = {}
IGNORE_DURATION = 5
StartTime = time.time()

# Sudo users cache: {owner_id: [sudo_user_id, ...]}
from collections import defaultdict
SUDO = defaultdict(list)

from fonts import *
from pyrogram import Client, filters
from convopyro import Conversation

# Optional: Your support group username (without @)
GROUP = os.getenv('GROUP', 'nub_coder_s')

# Optional: Your updates channel username (without @)
CHANNEL = os.getenv('CHANNEL', 'nub_coders')

# Optional: Get from @BotFather on Telegram (used for inline bot features)
BOT_TOKEN = os.getenv('BOT_TOKEN', '')

# Required: Your Pyrogram String Session
SESSION_STR = os.getenv('SESSION_STR', '')

apps= {}

# External community plugins (Phase 5): drop *.py files in EXTRA_PLUGINS_DIR and
# they load at startup. loaded_extra_plugins is populated by main.py and read by
# the .plugins command.
EXTRA_PLUGINS_DIR = os.getenv('EXTRA_PLUGINS_DIR', os.path.join(os.getcwd(), 'plugins'))
loaded_extra_plugins = []
